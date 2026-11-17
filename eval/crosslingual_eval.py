"""
eval/crosslingual_eval.py
==========================
Do thiet hai do NGON NGU cau hoi (Viet hoi bai bao Anh) tren retrieval, va thu cach sua.

Du lieu: 21 cap cau song song = 21 cau answerable cua golden_set.jsonl + ban dich trong
eval/golden_set_parallel.jsonl (cung evidence). Moi cap co 1 cau EN va 1 cau VI.

Cau hinh (deu: hybrid top-20 -> Cohere rerank, cham lenient tren top-20):
  en            : cau EN, nhu production (moc tham chieu)
  vi            : cau VI, nhu production hien tai
  vi-dense      : cau VI, bo nhanh tu khoa (chi dense -> rerank)
  vi-sparse-en* : nhanh tu khoa dung ban EN do NGUOI dich (can tren cua cach "dich cau hoi"),
                  dense + rerank van dung cau VI
  vi-sparse-mt  : nhu tren nhung ban EN do qwen3.8-27b (Groq) dich
  vi-all-mt     : ban EN do qwen dich cho CA dense, sparse lan rerank (cau tra loi van theo cau goc)

Khong goi LLM sinh cau tra loi. Ton: ~21 Gemini embed (cache), ~105 Cohere rerank, ~21 Groq qwen ngan.
Chay: EVAL_DATABASE_URL=postgresql://postgres:postgres@localhost:55434/postgres python eval/crosslingual_eval.py
"""

import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval import metrics  # noqa: E402
from eval.run_eval import (  # noqa: E402
    TOP_K,
    _get_eval_db_url,
    _git_commit,
    get_query_embeddings,
    load_golden,
)

PARALLEL_PATH = ROOT / "eval" / "golden_set_parallel.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
CONFIGS = ["en", "vi", "vi-dense", "vi-sparse-en*", "vi-sparse-mt", "vi-all-mt"]
RERANK_SLEEP = 6.5  # Cohere trial ~10 call/phut

TRANSLATE_PROMPT = (
    "Translate this question about a scientific paper into English, for keyword search over the "
    "English paper. Keep technical terms, model names, dataset names and numbers exactly. "
    "Output only the English question.\n\nQuestion: {q}"
)


def load_pairs() -> list[dict]:
    """[{source_id, paper_id, evidence, en, vi}] cho 21 cau answerable."""
    gold = {it["id"]: it for it in load_golden() if it["type"] != "unanswerable"}
    pairs = []
    for line in PARALLEL_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        p = json.loads(line)
        src = gold[p["source_id"]]
        texts = {src["lang"]: src["question"], p["lang"]: p["question"]}
        pairs.append({"source_id": src["id"], "paper_id": src["paper_id"], "evidence": src["evidence"],
                      "orig_lang": src["lang"], "en": texts["en"], "vi": texts["vi"]})
    return pairs


def translate(client, question: str) -> str:
    r = client.chat.completions.create(
        model="qwen/qwen3.8-27b", reasoning_effort="none", temperature=0, max_tokens=120,
        messages=[{"role": "user", "content": TRANSLATE_PROMPT.format(q=question)}],
    )
    return (r.choices[0].message.content or "").strip()


async def run_config(config: str, pair: dict, embs: dict, mt: dict) -> list[dict]:
    from app.indexing.reranker import get_reranker
    from app.storage import repository

    pid = pair["paper_id"]
    if config == "en":
        q_dense = q_sparse = q_rerank = pair["en"]
    elif config == "vi-all-mt":
        q_dense = q_sparse = q_rerank = mt[pair["source_id"]]
    else:
        q_dense = q_rerank = pair["vi"]
        q_sparse = {"vi": pair["vi"], "vi-dense": None, "vi-sparse-en*": pair["en"],
                    "vi-sparse-mt": mt.get(pair["source_id"])}[config]
    dense = await repository.dense_search(pid, embs[q_dense], TOP_K)
    if q_sparse is None:
        candidates = dense
    else:
        sparse = await repository.sparse_search(pid, q_sparse, TOP_K)
        candidates = repository.reciprocal_rank_fusion(dense, sparse)[:TOP_K]
    return await asyncio.to_thread(get_reranker().rerank, q_rerank, candidates, TOP_K)


def score(chunks: list[dict], evidence: list[dict]) -> dict:
    quotes = [e["quote"] for e in evidence]
    rels = [metrics.is_relevant(c["text"], quotes, "lenient") for c in chunks]
    return {"h1": metrics.hit_at_k(rels, 1), "h5": metrics.hit_at_k(rels, 5), "mrr": metrics.mrr_at_k(rels),
            "rank": metrics.first_relevant_rank(rels)}


async def main() -> None:
    _get_eval_db_url()
    from groq import Groq

    from app.config import settings
    from app.storage import repository

    pairs = load_pairs()
    embs, err = await get_query_embeddings([p[lang] for p in pairs for lang in ("en", "vi")])
    if err:
        print("[STOP] embed error:", err)
        return
    client = Groq(api_key=settings.groq_api_key)
    mt = {}
    for p in pairs:
        mt[p["source_id"]] = translate(client, p["vi"])
        print(f"[mt] {p['source_id']}: {mt[p['source_id']]}", flush=True)
        time.sleep(2)
    mt_embs, err = await get_query_embeddings(list(mt.values()))
    if err:
        print("[STOP] embed error (ban dich):", err)
        return
    embs.update(mt_embs)

    results: dict[str, dict[str, dict]] = {c: {} for c in CONFIGS}
    try:
        for p in pairs:
            for c in CONFIGS:
                results[c][p["source_id"]] = score(await run_config(c, p, embs, mt), p["evidence"])
                await asyncio.sleep(RERANK_SLEEP)
            print(f"[{p['source_id']}] " + " ".join(f"{c}={results[c][p['source_id']]['rank']}" for c in CONFIGS),
                  flush=True)
    finally:
        await repository.close_pool()

    n = len(pairs)
    avg = lambda c, k: sum(r[k] for r in results[c].values()) / n  # noqa: E731
    lines = [
        "# Cross-lingual retrieval (Viet hoi bai Anh)",
        "",
        f"- Ngay: {date.today().isoformat()}; git: {_git_commit()}; {n} cap cau song song (lenient, top-20 sau rerank)",
        "- `vi-sparse-en*` = ban dich cua nguoi (can tren); `vi-sparse-mt` = qwen3.8-27b dich (se dua vao production)",
        "",
        "| Cau hinh | Hit@1 | Hit@5 | MRR@20 |",
        "|---|---|---|---|",
    ]
    for c in CONFIGS:
        lines.append(f"| {c} | {avg(c, 'h1'):.3f} | {avg(c, 'h5'):.3f} | {avg(c, 'mrr'):.3f} |")
    lines += ["", "## Hang cua doan dung theo cau (None = khong co trong top-20)", "",
              "| cau | ngon ngu goc | " + " | ".join(CONFIGS) + " | ban dich qwen |",
              "|---|---|" + "---|" * len(CONFIGS) + "---|"]
    for p in pairs:
        sid = p["source_id"]
        lines.append(f"| {sid} | {p['orig_lang']} | " + " | ".join(str(results[c][sid]["rank"]) for c in CONFIGS)
                     + f" | {mt[sid].replace('|', '/')} |")
    out = RESULTS_DIR / f"{date.today().isoformat()}_crosslingual.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] Ghi {out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
