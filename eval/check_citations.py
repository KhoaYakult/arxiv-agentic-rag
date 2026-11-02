"""
eval/check_citations.py
========================
Do chat luong trich dan [n] cua CAU TRA LOI (khac run_eval.py chi do retrieval).
Chay 21 cau answerable cua eval/golden_set.jsonl qua rag_graph.ask() tren DB eval RIENG
roi bao cao:
  (a) ti le cau tra loi co >= 1 marker hop le (trong pham vi so doan),
  (b) so marker tro ngoai pham vi (UI se bo, nhung LLM khong nen viet),
  (c) citation precision: ti le cau tra loi co >= 1 marker tro vao chunk chua evidence
      (so khop lenient cua eval/metrics.py),
  (d) so cau co kieu trich dan KHAC grammar [n] (vd 【1†L1】, [^1], "(Source 2)") - de
      biet thieu marker la do model quen hay do viet sai dinh dang.

Mac dinh KHOA CUNG 1 provider (--provider groq): get_llm(provider=...) tuong minh khong
gan fallback, nen ca lan do chi 1 model tra loi (fallback Groq -> Gemini giua chung lam
so do tron 2 model). Groq free chi 8K token/phut: giua 2 cau nghi --sleep giay; gap 429
thi cho 65 s roi thu lai cau do (toi da 2 lan) truoc khi dung han.

Ngoai bang .md con ghi <ngay>_<label>.answers.jsonl: nguyen van cau tra loi + model +
cac chunk (so thu tu, trang, 200 ky tu dau) de doc lai vi sao thieu marker.

Chay (ton ~21 lan goi Gemini embed + 40-80 lan goi LLM):
    EVAL_DATABASE_URL=postgresql://postgres:postgres@localhost:55434/postgres make eval-citations
Checkpointer (lich su chat) cung ghi vao DB eval nay (bang checkpoints cua LangGraph) -
khong dung toi bang papers/chunks.
"""

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval import metrics  # noqa: E402
from eval.run_eval import _get_eval_db_url, _git_commit, load_golden  # noqa: E402

RESULTS_DIR = ROOT / "eval" / "results"
QUOTA_RETRIES = 2
QUOTA_WAIT_SEC = 65

# Kieu trich dan KHONG nam trong grammar [n] (chi de chan doan, khong tinh la marker hop le).
ALT_CITATION_RE = re.compile(
    r"【[^】]{0,40}】|\[\^\d{1,3}\]|\((?:source|sources|chunk|passage|đoạn|nguồn)\s*\d",
    re.IGNORECASE,
)


def score_answer(answer: str, chunks: list[dict], quotes: list[str]) -> dict:
    nums = metrics.citation_markers(answer)
    valid = [n for n in nums if 1 <= n <= len(chunks)]
    precise = any(metrics.is_relevant(chunks[n - 1]["text"], quotes, mode="lenient") for n in valid)
    alt = ALT_CITATION_RE.findall(answer)
    return {"markers": nums, "valid": valid, "out_of_range": len(nums) - len(valid), "precise": precise,
            "alt": alt}


def is_quota_error(e: Exception) -> bool:
    """Loi het quota Gemini/Groq (429 / RESOURCE_EXHAUSTED) -> dung vong lap, khong dap tiep."""
    text = str(e)
    return "RESOURCE_EXHAUSTED" in text or "429" in text


def error_row(it: dict, e: Exception, secs: float) -> dict:
    """Dong ket qua cho cau hoi bi loi (khong phai quota): tinh nhu khong co marker."""
    msg = f"{type(e).__name__}: {e}".replace("|", "/").replace("\n", " ")[:120]
    return {"markers": [], "valid": [], "out_of_range": 0, "precise": False, "alt": [], "id": it["id"],
            "lang": it["lang"], "grade": None, "rewrites": None, "secs": round(secs, 1), "error": msg}


def pin_provider(provider: str) -> str:
    """
    Ep moi node cua agent dung DUNG 1 provider (khong fallback). Cac node import get_llm
    ngay luc chay (`from app.llm.llm_factory import get_llm` trong ham) nen thay thuoc
    tinh cua module la du. Tra ve ten model de ghi vao bao cao.
    """
    from app.config import settings
    from app.llm import llm_factory

    if provider == "auto":
        return "auto (Groq, fallback Gemini)"
    original = llm_factory.get_llm
    llm_factory.get_llm = lambda provider_=None, **kw: original(provider, **kw)
    if provider == "groq":
        return f"groq/{llm_factory._pick_best_groq_model(settings.groq_api_key)}"
    if provider == "gemini":
        return f"gemini/{settings.gemini_model_name}"
    return f"ollama/{settings.ollama_llm_model}"


async def main(args: argparse.Namespace) -> None:
    _get_eval_db_url()
    from app.agent.rag_graph import ask, close_checkpointer
    from app.storage import repository

    model = pin_provider(args.provider)
    print(f"[INFO] Model: {model}", flush=True)

    items = [it for it in load_golden() if it["type"] != "unanswerable"]
    if args.only:
        wanted = set(args.only.split(","))
        items = [it for it in items if it["id"] in wanted]
    rows = []
    answers = []
    stop_note = ""  # khac rong neu vong lap dung som vi het quota
    run_id = int(time.time())
    try:
        for i, it in enumerate(items):
            if i and args.sleep:
                await asyncio.sleep(args.sleep)  # Groq free: 8K token/phut
            t0 = time.time()
            result = None
            for attempt in range(QUOTA_RETRIES + 1):
                try:
                    result = await ask(it["question"], it["paper_id"],
                                       thread_id=f"citecheck_{run_id}_{it['id']}_{attempt}")
                    break
                except Exception as e:
                    if not is_quota_error(e):
                        rows.append(error_row(it, e, time.time() - t0))
                        print(f"[{it['id']}] ERROR {type(e).__name__}", flush=True)
                        break
                    if attempt == QUOTA_RETRIES:
                        stop_note = (f"dung som vi het quota ({type(e).__name__}) o cau {it['id']}; "
                                     f"{len(items) - i} cau chua chay")
                        print(f"[STOP] {stop_note}", flush=True)
                        break
                    print(f"[{it['id']}] 429, cho {QUOTA_WAIT_SEC}s roi thu lai...", flush=True)
                    await asyncio.sleep(QUOTA_WAIT_SEC)
            if stop_note:
                break
            if result is None:
                continue
            messages = result.get("messages", [])
            answer = messages[-1].content if messages else ""
            if isinstance(answer, list):
                answer = " ".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in answer)
            chunks = result.get("retrieved_chunks", [])
            s = score_answer(answer, chunks, [e["quote"] for e in it["evidence"]])
            rows.append({**s, "id": it["id"], "lang": it["lang"], "grade": result.get("grade"),
                         "rewrites": result.get("rewrite_count"), "secs": round(time.time() - t0, 1),
                         "error": ""})
            answers.append({
                "id": it["id"], "model": model, "question": it["question"],
                "final_question": result.get("question"), "grade": result.get("grade"),
                "rewrites": result.get("rewrite_count"), "markers": s["markers"], "alt": s["alt"],
                "answer": answer,
                "chunks": [{"n": k, "page": c.get("page_num"), "section": c.get("parent_section_name"),
                            "head": c["text"][:200]} for k, c in enumerate(chunks, start=1)],
            })
            print(f"[{it['id']}] markers={s['markers']} alt={len(s['alt'])} precise={s['precise']}",
                  flush=True)
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
    has_alt = sum(1 for r in rows if r["alt"])
    pct = lambda x: f"{x / n:.0%}" if n else "n/a"  # noqa: E731
    stem = f"{date.today().isoformat()}_{args.label}"
    lines = [
        f"# Citation eval - {args.label}",
        "",
        f"- Ngay: {date.today().isoformat()}",
        f"- Git commit: {_git_commit()}",
        f"- Model: {model}; nghi giua cac cau: {args.sleep}s",
        f"- So cau hoi (answerable): {len(items)}; da chay: {n}; loi: {n_err}; chua chay: {n_skipped}",
        f"- Nguyen van cau tra loi: `{stem}.answers.jsonl`",
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
        f"| (d) Cau co kieu trich dan khac [n] | {has_alt}/{n} ({pct(has_alt)}) |",
        "",
        "| id | lang | grade | rewrite | markers | hop le | trung evidence | kieu khac | giay | error |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        alt = ", ".join(r["alt"][:3]).replace("|", "/")
        lines.append(f"| {r['id']} | {r['lang']} | {r['grade']} | {r['rewrites']} | {r['markers']} | "
                     f"{r['valid']} | {'co' if r['precise'] else '-'} | {alt} | {r['secs']} | {r['error']} |")
    out = RESULTS_DIR / f"{stem}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    jsonl = RESULTS_DIR / f"{stem}.answers.jsonl"
    jsonl.write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in answers), encoding="utf-8")
    print(f"[OK] Ghi {out} va {jsonl.name}", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--label", default="citations")
    p.add_argument("--provider", default="groq", choices=["groq", "gemini", "ollama", "auto"],
                   help="khoa 1 provider cho ca lan do (auto = hanh vi production: Groq + fallback Gemini)")
    p.add_argument("--sleep", type=float, default=20, help="giay nghi giua 2 cau (Groq free 8K token/phut)")
    p.add_argument("--only", default="", help="chi chay cac id nay, vd q15,q17")
    asyncio.run(main(p.parse_args()))
