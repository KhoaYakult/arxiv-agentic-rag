"""A/B grader tren 36 cau golden voi retrieval THAT (hybrid top20 -> Cohere top5, cau hoi goc),
cung prompt GRADE_DOCS_TEMPLATE + format_grade_context (du text). So gpt-oss-120b (cau hinh hien tai)
voi qwen3.8-27b tat suy luan. Ghi raw output + token + thoi gian."""

import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path("/Users/khoa/Developer Project/arxiv-agentic-rag")
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).with_name("grader_ab.jsonl")

CONFIGS = {
    "gpt-oss-120b": dict(model="openai/gpt-oss-120b", max_tokens=5096, temperature=0.2),
    "qwen3.8-27b": dict(model="qwen/qwen3.8-27b", max_tokens=16, temperature=0.2, reasoning_effort="none"),
}


def call(client, cfg, prompt):
    for attempt in range(4):
        t0 = time.time()
        try:
            r = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], **cfg)
            raw = (r.choices[0].message.content or "").strip()
            return {"raw": raw[:60], "loose": "yes" if "yes" in raw.lower() else "no",
                    "strict": "yes" if raw.lower().lstrip("\"' *").startswith("yes") else "no",
                    "p": r.usage.prompt_tokens, "c": r.usage.completion_tokens, "secs": round(time.time() - t0, 2)}
        except Exception as e:
            msg = re.sub(r"org_\w+", "org", str(e))[:200]
            if "per day" in msg or "TPD" in msg:
                return {"err": msg}
            time.sleep(20 * (attempt + 1))
            last = msg
    return {"err": last}


async def main():
    from groq import Groq

    from app.agent.rag_graph import format_grade_context
    from app.config import settings
    from app.indexing.reranker import get_reranker
    from app.llm.prompt_templates import GRADE_DOCS_TEMPLATE
    from app.storage import repository
    from eval import metrics
    from eval.run_eval import _get_eval_db_url, get_query_embeddings, load_golden

    _get_eval_db_url()
    client = Groq(api_key=settings.groq_api_key)
    items = load_golden()
    embs, err = await get_query_embeddings([it["question"] for it in items])
    if err:
        print("embed error:", err)
    rows = []
    try:
        for i, it in enumerate(items):
            if i:
                await asyncio.sleep(8)  # Cohere trial 10/phut + Groq 8K TPM moi model
            q = it["question"]
            cands = await repository.hybrid_search(it["paper_id"], q, embs[q], top_k=20)
            chunks = await asyncio.to_thread(get_reranker().rerank, q, cands, 5)
            quotes = [e["quote"] for e in it.get("evidence", [])]
            ev = [k + 1 for k, c in enumerate(chunks) if quotes and metrics.is_relevant(c["text"], quotes)]
            prompt = GRADE_DOCS_TEMPLATE.format(context=format_grade_context(chunks), question=q)
            row = {"id": it["id"], "type": it["type"], "lang": it["lang"], "evidence_in_top5": ev,
                   "top1": round(chunks[0]["rerank_score"], 3)}
            for name, cfg in CONFIGS.items():
                row[name] = await asyncio.to_thread(call, client, cfg, prompt)
            rows.append(row)
            print(it["id"], it["type"], it["lang"], "ev", ev, {n: row[n].get("strict", row[n].get("err", "")[:60]) for n in CONFIGS},
                  flush=True)
    finally:
        await repository.close_pool()
        OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


asyncio.run(main())
