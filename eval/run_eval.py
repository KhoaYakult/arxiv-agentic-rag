"""
eval/run_eval.py
=================
Đánh giá retrieval (Phase 3) trên golden set, chạy với DB eval RIÊNG (xem index_papers.py).

Cấu hình so sánh (mỗi cấu hình trả tối đa 20 chunk của paper_id câu hỏi):
  - sparse     : Postgres full-text search
  - dense      : pgvector cosine (cần query embedding)
  - rrf        : hybrid_search = dense + sparse fuse bằng RRF (cần embedding)
  - rrf+rerank : hybrid top 20 -> reranker (cần embedding + reranker thật)

Chỉ đánh giá câu answerable (type != unanswerable). Relevance + metric: eval/metrics.py,
báo cả 2 chế độ strict/lenient.

Query embedding được cache ở eval/cache/query_embeddings.json (key = sha256(model + câu hỏi))
vì quota embed free-tier Gemini rất hẹp. Lỗi embed (429...) -> in cảnh báo, giữ phần đã cache,
BỎ QUA các cấu hình cần embedding thay vì crash.

Cohere trial key: 10 call/phút -> ngủ ~6.5s giữa 2 lần rerank.

Chạy từ thư mục gốc repo (EVAL_DATABASE_URL bắt buộc, từ chối URL chứa "supabase"):
    EVAL_DATABASE_URL=postgresql://postgres:postgres@localhost:55434/postgres \\
        python eval/run_eval.py --label baseline [--configs sparse,dense]
"""

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from eval import metrics

GOLDEN_PATH = BASE_DIR / "eval" / "golden_set.jsonl"
CACHE_PATH = BASE_DIR / "eval" / "cache" / "query_embeddings.json"
RESULTS_DIR = BASE_DIR / "eval" / "results"

ALL_CONFIGS = ["sparse", "dense", "rrf", "rrf+rerank"]
NEEDS_EMBEDDING = {"dense", "rrf", "rrf+rerank"}
TOP_K = 20
RERANK_SLEEP_SEC = 6.5  # Cohere trial: 10 call/phút


def _get_eval_db_url() -> str:
    """Đọc + kiểm tra URL; ghi đè settings.database_url TRƯỚC khi repository tạo pool."""
    url = os.environ.get("EVAL_DATABASE_URL", "").strip()
    if not url:
        sys.exit("[LOI] Chua dat EVAL_DATABASE_URL (Postgres+pgvector rieng cho eval).")
    if "supabase" in url.lower():
        sys.exit("[LOI] EVAL_DATABASE_URL tro vao Supabase - tu choi chay (DB eval phai tach rieng production).")
    settings.database_url = url
    return url


def load_golden(path: Path = GOLDEN_PATH) -> list[dict]:
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=BASE_DIR, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# QUERY EMBEDDING CACHE
# ──────────────────────────────────────────────────────────────────────────────

def _cache_key(model_name: str, question: str) -> str:
    return hashlib.sha256((model_name + question).encode("utf-8")).hexdigest()


def _load_cache() -> dict[str, list[float]]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict[str, list[float]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache), encoding="utf-8")
    tmp.replace(CACHE_PATH)


async def get_query_embeddings(questions: list[str]) -> tuple[dict[str, list[float]], str | None]:
    """
    Trả ({câu hỏi: embedding} cho những câu có sẵn, lỗi hoặc None).
    Chỉ embed các câu chưa cache; lỗi đầu tiên -> dừng ngay (không gọi tiếp để khỏi phí
    retry/quota), lưu phần đã có.
    """
    from app.indexing.embeddings import GeminiEmbeddingProvider

    model_name = GeminiEmbeddingProvider.MODEL_NAME
    cache = _load_cache()
    result = {q: cache[_cache_key(model_name, q)] for q in questions if _cache_key(model_name, q) in cache}
    missing = [q for q in questions if q not in result]
    if not missing:
        return result, None

    print(f"[INFO] Query embedding: {len(result)} cached, {len(missing)} can embed.", flush=True)
    error = None
    try:
        from app.indexing.embeddings import get_embedding_provider

        provider = get_embedding_provider()
        for q in missing:
            vec = await asyncio.to_thread(provider.embed_query, q)
            result[q] = vec
            cache[_cache_key(model_name, q)] = vec
            _save_cache(cache)
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:200]}"
        print(
            f"[WARN] Embed query that bai ({error}). Giu {len(result)}/{len(questions)} embedding da cache; "
            "cac config can embedding se bi BO QUA.",
            flush=True,
        )
    return result, error


# ──────────────────────────────────────────────────────────────────────────────
# RETRIEVAL
# ──────────────────────────────────────────────────────────────────────────────

async def retrieve(config: str, item: dict, embedding: list[float] | None) -> list[dict]:
    from app.indexing.reranker import get_reranker
    from app.storage import repository

    pid, q = item["paper_id"], item["question"]
    if config == "sparse":
        return await repository.sparse_search(pid, q, top_k=TOP_K)
    if config == "dense":
        return await repository.dense_search(pid, embedding, top_k=TOP_K)
    if config == "rrf":
        return await repository.hybrid_search(pid, q, embedding, top_k=TOP_K)
    if config == "rrf+rerank":
        candidates = await repository.hybrid_search(pid, q, embedding, top_k=TOP_K)
        return await asyncio.to_thread(get_reranker().rerank, q, candidates, TOP_K)
    raise ValueError(config)


async def run_configs(
    configs: list[str], items: list[dict], embeddings: dict[str, list[float]], embed_error: str | None
) -> tuple[dict[str, dict[str, list[dict]]], dict[str, str]]:
    """Trả (runs[config][qid] = list chunk, skipped[config] = lý do)."""
    runs: dict[str, dict[str, list[dict]]] = {}
    skipped: dict[str, str] = {}
    missing_emb = [it for it in items if it["question"] not in embeddings]

    for config in configs:
        if config in NEEDS_EMBEDDING and missing_emb:
            reason = f"thieu query embedding ({len(missing_emb)}/{len(items)} cau)"
            skipped[config] = reason + (f"; loi embed: {embed_error}" if embed_error else "")
            continue
        if config == "rrf+rerank":
            from app.indexing.reranker import get_reranker

            if get_reranker().mode == "disabled":
                skipped[config] = "reranker disabled (khong co COHERE_API_KEY va khong co sentence-transformers)"
                continue
            use_sleep = get_reranker().mode == "cohere"
        else:
            use_sleep = False

        print(f"[RUN] {config} ({len(items)} cau)...", flush=True)
        per_q: dict[str, list[dict]] = {}
        try:
            for i, it in enumerate(items):
                if use_sleep and i > 0:
                    await asyncio.sleep(RERANK_SLEEP_SEC)
                per_q[it["id"]] = await retrieve(config, it, embeddings.get(it["question"]))
        except Exception as e:
            skipped[config] = f"loi khi chay: {type(e).__name__}: {str(e)[:200]}"
            print(f"[WARN] {config} that bai: {skipped[config]}", flush=True)
            continue
        runs[config] = per_q
    return runs, skipped


# ──────────────────────────────────────────────────────────────────────────────
# BAO CAO
# ──────────────────────────────────────────────────────────────────────────────

def _fmt(x: float) -> str:
    return f"{x:.3f}"


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def compute(
    runs: dict[str, dict[str, list[dict]]], items: list[dict]
) -> dict[str, dict[str, dict]]:
    """out[config][mode] = {'per_q': [metrics...], 'ranks': {qid: rank|None}, 'empty': int}."""
    out: dict[str, dict[str, dict]] = {}
    for config, per_q in runs.items():
        out[config] = {}
        for mode in metrics.MODES:
            qm, ranks = [], {}
            for it in items:
                quotes = [e["quote"] for e in it["evidence"]]
                rels = [metrics.is_relevant(c["text"], quotes, mode) for c in per_q[it["id"]]]
                qm.append(metrics.question_metrics(rels))
                ranks[it["id"]] = metrics.first_relevant_rank(rels)
            out[config][mode] = {
                "per_q": qm,
                "ranks": ranks,
                "empty": sum(1 for it in items if not per_q[it["id"]]),
            }
    return out


def build_report(
    label: str,
    items: list[dict],
    configs_requested: list[str],
    results: dict[str, dict[str, dict]],
    skipped: dict[str, str],
) -> str:
    configs = [c for c in ALL_CONFIGS if c in results]
    md = [
        f"# Retrieval eval - {label}",
        "",
        f"- Ngay: {date.today().isoformat()}",
        f"- Git commit: {_git_commit()}",
        f"- So cau hoi (answerable): {len(items)}",
        f"- Configs yeu cau: {', '.join(configs_requested)}",
        f"- Configs da chay: {', '.join(configs) or '(khong co)'}",
    ]
    if skipped:
        md.append("- Configs bi bo qua:")
        md += [f"  - `{c}`: {why}" for c, why in skipped.items()]
    md.append("")

    if not results:
        md.append("Khong co config nao chay duoc - khong co so lieu.")
        return "\n".join(md)

    keys = [f"hit@{k}" for k in metrics.HIT_KS] + [f"mrr@{metrics.MRR_K}", f"ndcg@{metrics.NDCG_K}"]
    header = ["config"] + [k.replace("hit@", "Hit@").replace("mrr@", "MRR@").replace("ndcg@", "nDCG@") for k in keys]
    header.append("0 ket qua")
    for mode in metrics.MODES:
        md += [f"## Metrics ({mode})", ""]
        rows = []
        for c in configs:
            agg = metrics.aggregate(results[c][mode]["per_q"])
            rows.append([c] + [_fmt(agg[k]) for k in keys] + [f"{results[c][mode]['empty']}/{len(items)}"])
        md += [_table(header, rows), ""]
    md.append(
        "`0 ket qua` = so cau hoi ma config tra ve danh sach rong (vd sparse: "
        "`websearch_to_tsquery` AND tat ca tu khoa, cau hoi dai/tieng Viet de khong khop gi)."
    )
    md.append("")

    for title, field in (("type", "type"), ("lang", "lang")):
        groups = sorted({it[field] for it in items})
        counts = {g: sum(1 for it in items if it[field] == g) for g in groups}
        md += [f"## Hit@5 (lenient) theo {title}", ""]
        rows = []
        for c in configs:
            by = metrics.group_mean(results[c]["lenient"]["per_q"], [it[field] for it in items], "hit@5")
            rows.append([c] + [_fmt(by[g][0]) for g in groups])
        md += [_table(["config"] + [f"{g} (n={counts[g]})" for g in groups], rows), ""]

    md += [
        "## Rank cua chunk lien quan dau tien (lenient)",
        "",
        "`-` = khong co chunk lien quan trong top 20. Cot strict trong ngoac.",
        "",
    ]
    rows = []
    for it in items:
        row = [it["id"], it["paper_id"].replace("arxiv-", ""), it["lang"], it["type"]]
        for c in configs:
            ln = results[c]["lenient"]["ranks"][it["id"]]
            st = results[c]["strict"]["ranks"][it["id"]]
            row.append(f"{ln or '-'} ({st or '-'})")
        rows.append(row)
    md.append(_table(["id", "paper", "lang", "type"] + configs, rows))
    md.append("")
    return "\n".join(md)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

async def main(args: argparse.Namespace) -> None:
    _get_eval_db_url()
    requested = [c.strip() for c in args.configs.split(",") if c.strip()]
    unknown = [c for c in requested if c not in ALL_CONFIGS]
    if unknown:
        sys.exit(f"[LOI] Config khong hop le: {unknown}. Hop le: {ALL_CONFIGS}")

    items = [it for it in load_golden() if it["type"] != "unanswerable"]
    print(f"[INFO] {len(items)} cau answerable.", flush=True)

    from app.storage import repository

    try:
        embeddings: dict[str, list[float]] = {}
        embed_error = None
        if any(c in NEEDS_EMBEDDING for c in requested):
            embeddings, embed_error = await get_query_embeddings([it["question"] for it in items])

        runs, skipped = await run_configs(requested, items, embeddings, embed_error)
    finally:
        await repository.close_pool()

    results = compute(runs, items)
    report = build_report(args.label, items, requested, results, skipped)
    print("\n" + report)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{date.today().isoformat()}_{args.label}.md"
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"\n[OK] Da ghi {out_path}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--label", default="baseline", help="Nhan trong ten file ket qua (mac dinh: baseline)")
    parser.add_argument(
        "--configs", default=",".join(ALL_CONFIGS), help=f"Danh sach config, phan tach bang dau phay (mac dinh: tat ca = {','.join(ALL_CONFIGS)})"
    )
    asyncio.run(main(parser.parse_args()))
