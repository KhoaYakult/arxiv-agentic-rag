"""
eval/check_citations.py
========================
Do CAU TRA LOI cua agent (khac run_eval.py chi do retrieval). Chay moi cau cua
eval/golden_set.jsonl (ca cau answerable lan unanswerable) qua rag_graph.ask() tren DB
eval RIENG roi bao cao.

Cau answerable:
  (a) ti le cau tra loi co >= 1 marker hop le (trong pham vi so doan),
  (b) so marker tro ngoai pham vi (UI se bo, nhung LLM khong nen viet),
  (c) citation precision: ti le cau tra loi co >= 1 marker tro vao chunk chua evidence
      (so khop lenient cua eval/metrics.py),
  (d) so cau co kieu trich dan KHAC grammar [n] (vd 【1†L1】, [^1], "(Source 2)"),
  (e) grade "no" o LUOT CHAM DAU (cham oan, vi cau co dap an).
Cau unanswerable:
  (f) grade "yes" o luot cham dau (grader de lot),
  (g) cau tra loi co tu choi ("khong du thong tin") hay khong - heuristic
      looks_like_abstention(), doc lai answers.jsonl neu nghi ngo.
Moi cau: so lan goi LLM (grade + rewrite + generate) va diem rerank cua luot retrieve
DAU TIEN (top-5) - du lieu de chon nguong cho cong 3 tang (eval/gate_sim.py).

Luot dau lay tu lich su checkpoint cua LangGraph (aget_state_history), khong sua agent.

Mac dinh KHOA CUNG 1 provider (--provider groq): get_llm(provider=...) tuong minh khong
gan fallback, nen ca lan do chi 1 model tra loi (fallback Groq -> Gemini giua chung lam
so do tron 2 model). Groq free chi 8K token/phut: giua 2 cau nghi --sleep giay; gap 429
thi cho 65 s roi thu lai cau do (toi da 2 lan) truoc khi dung han.

Ngoai bang .md con ghi <ngay>_<label>.answers.jsonl: nguyen van cau tra loi + model +
cac chunk (so thu tu, trang, diem rerank, 200 ky tu dau).

Chay (ton ~1 lan goi Gemini embed + 2-6 lan goi LLM moi cau):
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

# Cau tra loi kieu "tai lieu khong co thong tin nay" (EN + VI). Heuristic: chi de dem, doc lai
# answers.jsonl khi so lieu bat thuong.
ABSTAIN_RE = re.compile(
    r"do(?:es)? not (?:contain|provide|report|mention|include|specify|state|give|present)"
    r"|not (?:enough|sufficient) information|(?:cannot|can't|unable to) (?:find|answer|determine)"
    r"|no (?:information|mention|details?) (?:about|on|of|regarding)"
    r"|(?:is|are) not (?:reported|mentioned|provided|specified|given|stated)"
    r"|không (?:chứa|có thông tin|đủ thông tin|nêu|đề cập|cung cấp|báo cáo)|chưa (?:nêu|đề cập)",
    re.IGNORECASE,
)


def score_answer(answer: str, chunks: list[dict], quotes: list[str]) -> dict:
    nums = metrics.citation_markers(answer)
    valid = [n for n in nums if 1 <= n <= len(chunks)]
    precise = any(metrics.is_relevant(chunks[n - 1]["text"], quotes, mode="lenient") for n in valid)
    alt = ALT_CITATION_RE.findall(answer)
    return {"markers": nums, "valid": valid, "out_of_range": len(nums) - len(valid), "precise": precise,
            "alt": alt}


def looks_like_abstention(answer: str) -> bool:
    return bool(ABSTAIN_RE.search(answer))


def summarize_trace(steps: list[tuple[tuple, dict]]) -> dict:
    """
    steps: lich su checkpoint theo thu tu thoi gian, moi phan tu (next, values).
    Tra ve diem rerank top-5 cua luot retrieve DAU (snapshot dau tien sap chay 'grade'),
    grade cua luot cham dau, so lan cham va so lan goi LLM (grade + rewrite + 1 generate).
    """
    first_scores: list[float] | None = None
    first_grade = None
    grade_calls = 0
    rewrites = 0
    for i, (nxt, values) in enumerate(steps):
        if "grade" in nxt and first_scores is None:
            first_scores = [c.get("rerank_score") for c in values.get("retrieved_chunks") or []]
        if "grade" in nxt:
            grade_calls += 1
            # Snapshot ngay sau node grade mang ket qua cham cua luot nay.
            if first_grade is None and i + 1 < len(steps):
                first_grade = steps[i + 1][1].get("grade") or None
        if "rewrite" in nxt:
            rewrites += 1
    return {"first_scores": first_scores or [], "first_grade": first_grade, "grade_calls": grade_calls,
            "llm_calls": grade_calls + rewrites + 1}


def is_quota_error(e: Exception) -> bool:
    """Loi het quota Gemini/Groq (429 / RESOURCE_EXHAUSTED) -> dung vong lap, khong dap tiep."""
    text = str(e)
    return "RESOURCE_EXHAUSTED" in text or "429" in text


def error_row(it: dict, e: Exception, secs: float) -> dict:
    """Dong ket qua cho cau hoi bi loi (khong phai quota): tinh nhu khong co marker."""
    msg = f"{type(e).__name__}: {e}".replace("|", "/").replace("\n", " ")[:120]
    return {"markers": [], "valid": [], "out_of_range": 0, "precise": False, "alt": [], "id": it["id"],
            "lang": it["lang"], "type": it.get("type"), "grade": None, "rewrites": None,
            "first_grade": None, "first_scores": [], "llm_calls": None, "abstained": False,
            "secs": round(secs, 1), "error": msg}


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


async def trace_of(thread_id: str) -> dict:
    """Doc lich su checkpoint cua 1 thread (rieng cho eval; production chi dung ask())."""
    from app.agent.rag_graph import _get_rag_app

    app = await _get_rag_app()
    hist = [s async for s in app.aget_state_history({"configurable": {"thread_id": thread_id}})]
    return summarize_trace([(s.next, s.values) for s in reversed(hist)])


async def main(args: argparse.Namespace) -> None:
    _get_eval_db_url()
    from app.agent.rag_graph import ask, close_checkpointer
    from app.storage import repository

    model = pin_provider(args.provider)
    print(f"[INFO] Model: {model}", flush=True)

    items = load_golden()
    if args.answerable_only:
        items = [it for it in items if it["type"] != "unanswerable"]
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
            thread_id = ""
            for attempt in range(QUOTA_RETRIES + 1):
                thread_id = f"citecheck_{run_id}_{it['id']}_{attempt}"
                try:
                    result = await ask(it["question"], it["paper_id"], thread_id=thread_id)
                    break
                except Exception as e:
                    if not is_quota_error(e):
                        rows.append(error_row(it, e, time.time() - t0))
                        print(f"[{it['id']}] ERROR {type(e).__name__}", flush=True)
                        break
                    if attempt == QUOTA_RETRIES:
                        # Giu 1 doan loi de biet het quota phut (TPM) hay ngay (TPD); bo ma org.
                        detail = re.sub(r"org_\w+", "org_***", str(e)).replace("|", "/").replace("\n", " ")[:200]
                        stop_note = (f"dung som vi het quota ({type(e).__name__}: {detail}) o cau {it['id']}; "
                                     f"{len(items) - i} cau chua chay")
                        print(f"[STOP] {stop_note}", flush=True)
                        break
                    print(f"[{it['id']}] 429, cho {QUOTA_WAIT_SEC}s roi thu lai...", flush=True)
                    await asyncio.sleep(QUOTA_WAIT_SEC)
            if stop_note:
                break
            if result is None:
                continue
            secs = round(time.time() - t0, 1)
            messages = result.get("messages", [])
            answer = messages[-1].content if messages else ""
            if isinstance(answer, list):
                answer = " ".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in answer)
            chunks = result.get("retrieved_chunks", [])
            s = score_answer(answer, chunks, [e["quote"] for e in it["evidence"]])
            tr = await trace_of(thread_id)
            abstained = looks_like_abstention(answer)
            rows.append({**s, **tr, "id": it["id"], "lang": it["lang"], "type": it["type"],
                         "grade": result.get("grade"), "rewrites": result.get("rewrite_count"),
                         "abstained": abstained, "secs": secs, "error": ""})
            answers.append({
                "id": it["id"], "type": it["type"], "model": model, "question": it["question"],
                "final_question": result.get("question"), "grade": result.get("grade"),
                "first_grade": tr["first_grade"], "first_scores": tr["first_scores"],
                "llm_calls": tr["llm_calls"], "rewrites": result.get("rewrite_count"),
                "abstained": abstained, "markers": s["markers"], "alt": s["alt"], "answer": answer,
                "chunks": [{"n": k, "page": c.get("page_num"), "section": c.get("parent_section_name"),
                            "rerank_score": c.get("rerank_score"), "head": c["text"][:200]}
                           for k, c in enumerate(chunks, start=1)],
            })
            top = tr["first_scores"][0] if tr["first_scores"] else None
            print(f"[{it['id']}] {it['type']} first_grade={tr['first_grade']} top1={top} "
                  f"markers={s['markers']} abstained={abstained} calls={tr['llm_calls']}", flush=True)
    finally:
        # close_pool van phai chay du close_checkpointer nem loi
        try:
            await close_checkpointer()
        finally:
            await repository.close_pool()

    write_report(args, model, items, rows, answers, stop_note)


def _fmt_score(scores: list, k: int) -> str:
    return f"{scores[k]:.3f}" if len(scores) > k and scores[k] is not None else "-"


def write_report(args, model, items, rows, answers, stop_note) -> None:
    ans = [r for r in rows if r["type"] != "unanswerable"]
    una = [r for r in rows if r["type"] == "unanswerable"]
    n, nu = len(ans), len(una)
    n_err = sum(1 for r in rows if r["error"])
    has_valid = sum(1 for r in ans if r["valid"])
    precise = sum(1 for r in ans if r["precise"])
    oor = sum(r["out_of_range"] for r in ans)
    has_alt = sum(1 for r in ans if r["alt"])
    false_no = sum(1 for r in ans if r["first_grade"] == "no")
    leak_yes = sum(1 for r in una if r["first_grade"] == "yes")
    abstained = sum(1 for r in una if r["abstained"])
    calls = [r["llm_calls"] for r in rows if r["llm_calls"]]
    frac = lambda x, d: f"{x}/{d} ({x / d:.0%})" if d else "n/a"  # noqa: E731
    stem = f"{date.today().isoformat()}_{args.label}"
    lines = [
        f"# Citation eval - {args.label}",
        "",
        f"- Ngay: {date.today().isoformat()}",
        f"- Git commit: {_git_commit()}",
        f"- Model: {model}; nghi giua cac cau: {args.sleep}s",
        f"- So cau: {len(items)} (answerable {sum(1 for it in items if it['type'] != 'unanswerable')}); "
        f"da chay: {len(rows)}; loi: {n_err}; chua chay: {len(items) - len(rows)}",
        f"- Nguyen van cau tra loi: `{stem}.answers.jsonl`",
    ]
    if stop_note:
        lines.append(f"- LUU Y: {stop_note}. Mau so ben duoi la so cau da chay.")
    lines += [
        "",
        "| Chi so | Gia tri |",
        "|---|---|",
        f"| (a) Answerable co >= 1 marker hop le | {frac(has_valid, n)} |",
        f"| (b) Marker ngoai pham vi (tong) | {oor} |",
        f"| (c) Citation precision (lenient) | {frac(precise, n)} |",
        f"| (d) Answerable co kieu trich dan khac [n] | {frac(has_alt, n)} |",
        f"| (e) Answerable bi grade 'no' o luot dau (cham oan) | {frac(false_no, n)} |",
        f"| (f) Unanswerable duoc grade 'yes' o luot dau (lot) | {frac(leak_yes, nu)} |",
        f"| (g) Unanswerable co cau tra loi tu choi (heuristic) | {frac(abstained, nu)} |",
        f"| So lan goi LLM trung binh / cau | {sum(calls) / len(calls):.2f} |" if calls else "| So lan goi LLM | n/a |",
        "",
        "| id | type | lang | grade dau | top1 | top2 | rewrite | LLM calls | markers | trung evidence "
        "| tu choi | kieu khac | giay | error |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        top1, top2 = (_fmt_score(r["first_scores"], k) for k in (0, 1))
        alt = ", ".join(r["alt"][:3]).replace("|", "/")
        lines.append(f"| {r['id']} | {r['type']} | {r['lang']} | {r['first_grade']} | {top1} | {top2} | "
                     f"{r['rewrites']} | {r['llm_calls']} | {r['markers']} | {'co' if r['precise'] else '-'} | "
                     f"{'co' if r['abstained'] else '-'} | {alt} | {r['secs']} | {r['error']} |")
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
    p.add_argument("--answerable-only", action="store_true", help="bo cau unanswerable (hanh vi cu)")
    asyncio.run(main(p.parse_args()))
