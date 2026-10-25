"""
eval/check_citations.py
========================
Do chat luong trich dan [n] cua CAU TRA LOI (khac run_eval.py chi do retrieval).
Chay 21 cau answerable cua eval/golden_set.jsonl qua rag_graph.ask() tren DB eval RIENG
roi bao cao:
  (a) ti le cau tra loi co >= 1 marker hop le (trong pham vi so doan),
  (b) so marker tro ngoai pham vi (UI se bo, nhung LLM khong nen viet),
  (c) citation precision: ti le cau tra loi co >= 1 marker tro vao chunk chua evidence
      (so khop lenient cua eval/metrics.py).

Chay (ton ~21 lan goi Gemini embed + 40-80 lan goi LLM Groq/Gemini):
    EVAL_DATABASE_URL=postgresql://postgres:postgres@localhost:55434/postgres make eval-citations
Checkpointer (lich su chat) cung ghi vao DB eval nay (bang checkpoints cua LangGraph) -
khong dung toi bang papers/chunks.
"""

import argparse
import asyncio
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval import metrics  # noqa: E402
from eval.run_eval import _get_eval_db_url, _git_commit, load_golden  # noqa: E402

RESULTS_DIR = ROOT / "eval" / "results"


def score_answer(answer: str, chunks: list[dict], quotes: list[str]) -> dict:
    nums = metrics.citation_markers(answer)
    valid = [n for n in nums if 1 <= n <= len(chunks)]
    precise = any(metrics.is_relevant(chunks[n - 1]["text"], quotes, mode="lenient") for n in valid)
    return {"markers": nums, "valid": valid, "out_of_range": len(nums) - len(valid), "precise": precise}


def is_quota_error(e: Exception) -> bool:
    """Loi het quota Gemini/Groq (429 / RESOURCE_EXHAUSTED) -> dung vong lap, khong dap tiep."""
    text = str(e)
    return "RESOURCE_EXHAUSTED" in text or "429" in text


def error_row(it: dict, e: Exception, secs: float) -> dict:
    """Dong ket qua cho cau hoi bi loi (khong phai quota): tinh nhu khong co marker."""
    msg = f"{type(e).__name__}: {e}".replace("|", "/").replace("\n", " ")[:120]
    return {"markers": [], "valid": [], "out_of_range": 0, "precise": False, "id": it["id"],
            "lang": it["lang"], "grade": None, "secs": round(secs, 1), "error": msg}


async def main(args: argparse.Namespace) -> None:
    _get_eval_db_url()
    from app.agent.rag_graph import ask, close_checkpointer
    from app.storage import repository

    items = [it for it in load_golden() if it["type"] != "unanswerable"]
    rows = []
    stop_note = ""  # khac rong neu vong lap dung som vi het quota
    run_id = int(time.time())
    try:
        for i, it in enumerate(items):
            t0 = time.time()
            try:
                result = await ask(it["question"], it["paper_id"], thread_id=f"citecheck_{run_id}_{it['id']}")
            except Exception as e:
                if is_quota_error(e):
                    remaining = len(items) - i
                    stop_note = (f"dung som vi het quota ({type(e).__name__}) o cau {it['id']}; "
                                 f"{remaining} cau chua chay")
                    print(f"[STOP] {stop_note}", flush=True)
                    break
                rows.append(error_row(it, e, time.time() - t0))
                print(f"[{it['id']}] ERROR {type(e).__name__}", flush=True)
                continue
            messages = result.get("messages", [])
            answer = messages[-1].content if messages else ""
            if isinstance(answer, list):
                answer = " ".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in answer)
            chunks = result.get("retrieved_chunks", [])
            s = score_answer(answer, chunks, [e["quote"] for e in it["evidence"]])
            rows.append({**s, "id": it["id"], "lang": it["lang"], "grade": result.get("grade"),
                         "secs": round(time.time() - t0, 1), "error": ""})
            print(f"[{it['id']}] markers={s['markers']} precise={s['precise']}", flush=True)
    finally:
        # close_pool van phai chay du close_checkpointer nem loi
        try:
            await close_checkpointer()
        finally:
            await repository.close_pool()

    n = len(rows)
    n_err = sum(1 for r in rows if r["error"])
    n_skipped = len(items) - n
    has_valid = sum(1 for r in rows if r["valid"])
    precise = sum(1 for r in rows if r["precise"])
    oor = sum(r["out_of_range"] for r in rows)
    pct = lambda x: f"{x / n:.0%}" if n else "n/a"  # noqa: E731
    lines = [
        f"# Citation eval - {args.label}",
        "",
        f"- Ngay: {date.today().isoformat()}",
        f"- Git commit: {_git_commit()}",
        f"- So cau hoi (answerable): {len(items)}; da chay: {n}; loi: {n_err}; chua chay: {n_skipped}",
    ]
    if stop_note:
        lines.append(f"- LUU Y: {stop_note}. Mau so ben duoi la so cau da chay ({n}), khong phai {len(items)}.")
    lines += [
        "",
        "| Chi so | Gia tri |",
        "|---|---|",
        f"| (a) Cau tra loi co >= 1 marker hop le | {has_valid}/{n} ({pct(has_valid)}) |",
        f"| (b) Marker ngoai pham vi (tong) | {oor} |",
        f"| (c) Citation precision (lenient) | {precise}/{n} ({pct(precise)}) |",
        "",
        "| id | lang | grade | markers | hop le | trung evidence | giay | error |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['id']} | {r['lang']} | {r['grade']} | {r['markers']} | {r['valid']} | "
                     f"{'co' if r['precise'] else '-'} | {r['secs']} | {r['error']} |")
    out = RESULTS_DIR / f"{date.today().isoformat()}_{args.label}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] Ghi {out}", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--label", default="citations")
    asyncio.run(main(p.parse_args()))
