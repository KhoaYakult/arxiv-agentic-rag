"""
eval/followup_eval.py
======================
Do retrieval cho CAU HOI NOI TIEP ("no train tren dataset nao?") va thu cach sua.

Du lieu: eval/golden_set_followup.jsonl - moi cau co 1 luot hoi-dap truoc do (history) va
source_id tro ve cau TU DU NGHIA trong golden_set.jsonl (dung evidence cua cau do).

Cau hinh (deu: hybrid top-20 -> Cohere rerank, cham lenient tren top-20):
  last-turn  : cau noi tiep nhu production hien tai (khong doc lich su; cau VI dich EN cho tu khoa)
  oracle     : cau tu du nghia do NGUOI viet (cau goc trong golden set) - can tren
  cond-split : qwen viet lai thanh cau tu du nghia (CONDENSE_QUERY_TEMPLATE); dense + rerank dung
               ban cung ngon ngu, nhanh tu khoa dung ban tieng Anh
  cond-en    : nhu tren nhung ban tieng Anh dung cho CA dense, tu khoa lan rerank

Khong goi LLM sinh cau tra loi. Ton: ~60 Gemini embed (cache), ~56 Cohere rerank, ~25 Groq qwen ngan.
Chay: EVAL_DATABASE_URL=postgresql://postgres:postgres@localhost:55434/postgres python eval/followup_eval.py
"""

import asyncio
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.crosslingual_eval import score, translate  # noqa: E402
from eval.run_eval import (  # noqa: E402
    RERANK_SLEEP_SEC,
    TOP_K,
    _get_eval_db_url,
    _git_commit,
    get_query_embeddings,
    load_golden,
)

FOLLOWUP_PATH = ROOT / "eval" / "golden_set_followup.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
CONFIGS = ["last-turn", "oracle", "cond-split", "cond-en"]


def load_followups() -> list[dict]:
    gold = {it["id"]: it for it in load_golden()}
    items = []
    for line in FOLLOWUP_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            it = json.loads(line)
            src = gold[it["source_id"]]
            items.append({**it, "paper_id": src["paper_id"], "evidence": src["evidence"],
                          "oracle": src["question"], "oracle_lang": src["lang"]})
    return items


def format_history(history: list[dict]) -> str:
    return "\n".join(f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in history)


def parse_condensed(text: str, fallback: str) -> dict:
    """JSON {question, english} -> dict; hong thi dung cau goc (giong hanh vi production du kien)."""
    m = re.search(r"\{.*\}", text, flags=re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        data = {}
    q = str(data.get("question") or "").strip() or fallback
    en = str(data.get("english") or "").strip() or q
    return {"question": q, "english": en, "ok": bool(data.get("question"))}


def condense(client, history: list[dict], question: str) -> dict:
    from app.llm.prompt_templates import CONDENSE_QUERY_TEMPLATE

    t0 = time.time()
    r = client.chat.completions.create(
        model="qwen/qwen3.8-27b", reasoning_effort="none", temperature=0, max_tokens=200,
        messages=[{"role": "user", "content": CONDENSE_QUERY_TEMPLATE.format(
            chat_history=format_history(history), question=question)}],
    )
    out = parse_condensed(r.choices[0].message.content or "", question)
    out["sec"] = round(time.time() - t0, 2)
    return out


def queries_for(config: str, it: dict, mt: dict, cond: dict) -> tuple[str, str, str]:
    """(cau cho dense, cau cho tu khoa, cau cho rerank)."""
    if config == "last-turn":
        q = it["question"]
        return q, mt.get(q, q), q
    if config == "oracle":
        q = it["oracle"]
        return q, mt.get(q, q), q
    c = cond[it["id"]]
    if config == "cond-split":
        return c["question"], c["english"], c["question"]
    return c["english"], c["english"], c["english"]  # cond-en


async def run_config(pid: str, q_dense: str, q_sparse: str, q_rerank: str, embs: dict) -> list[dict]:
    from app.indexing.reranker import get_reranker
    from app.storage import repository

    dense = await repository.dense_search(pid, embs[q_dense], TOP_K)
    sparse = await repository.sparse_search(pid, q_sparse, TOP_K)
    candidates = repository.reciprocal_rank_fusion(dense, sparse)[:TOP_K]
    return await asyncio.to_thread(get_reranker().rerank, q_rerank, candidates, TOP_K)


async def main() -> None:
    _get_eval_db_url()
    from groq import Groq

    from app.agent.rag_graph import is_vietnamese
    from app.config import settings
    from app.storage import repository

    items = load_followups()
    client = Groq(api_key=settings.groq_api_key)

    # Ban dich EN cho nhanh tu khoa cua cau VI (giong sparse_query_for o production).
    mt = {}
    for q in {q for it in items for q in (it["question"], it["oracle"])}:
        if is_vietnamese(q):
            mt[q] = translate(client, q)
            time.sleep(1)
    cond = {}
    for it in items:
        cond[it["id"]] = condense(client, it["history"], it["question"])
        print(f"[cond] {it['id']} ({cond[it['id']]['sec']}s): {cond[it['id']]['question']}"
              f"  ||  {cond[it['id']]['english']}", flush=True)
        time.sleep(1)

    texts = {q for it in items for c in CONFIGS for q in (queries_for(c, it, mt, cond)[0],)}
    embs, err = await get_query_embeddings(sorted(texts))
    if err:
        print("[STOP] embed error:", err)
        return

    results: dict[str, dict[str, dict]] = {c: {} for c in CONFIGS}
    try:
        for it in items:
            for c in CONFIGS:
                chunks = await run_config(it["paper_id"], *queries_for(c, it, mt, cond), embs)
                results[c][it["id"]] = score(chunks, it["evidence"])
                await asyncio.sleep(RERANK_SLEEP_SEC)
            print(f"[{it['id']}] " + " ".join(f"{c}={results[c][it['id']]['rank']}" for c in CONFIGS), flush=True)
    finally:
        await repository.close_pool()

    n = len(items)

    def avg(c: str, k: str, ids=None) -> float:
        rows = [r for i, r in results[c].items() if ids is None or i in ids]
        return sum(r[k] for r in rows) / max(len(rows), 1)

    by_lang = {lang: {it["id"] for it in items if it["lang"] == lang} for lang in ("en", "vi")}
    lines = [
        "# Cau hoi noi tiep (multi-turn retrieval)",
        "",
        f"- Ngay: {date.today().isoformat()}; git: {_git_commit()}; {n} cau noi tiep "
        f"({len(by_lang['en'])} EN, {len(by_lang['vi'])} VI); lenient, top-20 sau rerank",
        "- `oracle` = cau tu du nghia do nguoi viet (can tren); `cond-*` = qwen3.8-27b viet lai tu lich su",
        f"- Condense parse OK: {sum(c['ok'] for c in cond.values())}/{n}; "
        f"thoi gian trung binh {sum(c['sec'] for c in cond.values()) / n:.2f}s",
        "",
        "| Cau hinh | Hit@1 | Hit@5 | MRR@20 | Hit@5 EN | Hit@5 VI |",
        "|---|---|---|---|---|---|",
    ]
    for c in CONFIGS:
        lines.append(f"| {c} | {avg(c, 'h1'):.3f} | {avg(c, 'h5'):.3f} | {avg(c, 'mrr'):.3f} "
                     f"| {avg(c, 'h5', by_lang['en']):.3f} | {avg(c, 'h5', by_lang['vi']):.3f} |")
    lines += ["", "## Hang cua doan dung theo cau (None = khong co trong top-20)", "",
              "| cau | loai | lang | " + " | ".join(CONFIGS) + " | cau noi tiep | qwen viet lai |",
              "|---|---|---|" + "---|" * len(CONFIGS) + "---|---|"]
    for it in items:
        i = it["id"]
        lines.append(f"| {i} | {it['kind']} | {it['lang']} | "
                     + " | ".join(str(results[c][i]["rank"]) for c in CONFIGS)
                     + f" | {it['question'].replace('|', '/')} | {cond[i]['question'].replace('|', '/')} |")
    out = RESULTS_DIR / f"{date.today().isoformat()}_followup.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] Ghi {out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
