"""
eval/gate_sim.py
=================
Mo phong OFFLINE (khong goi API) cong 3 tang kieu CRAG truoc grade_node, tren du lieu
eval/check_citations.py da ghi (*.answers.jsonl: first_scores = diem rerank top-5 cua luot
retrieve dau, first_grade = ket qua LLM grader luot dau, type).

Cong voi nguong (lo, hi) tren diem rerank cao nhat (top1):
  top1 >= hi       -> tra loi luon, KHONG goi grader
  top1 <  lo       -> viet lai cau hoi luon, KHONG goi grader
  lo <= top1 < hi  -> goi LLM grader (dung first_grade da ghi lam ket qua)
Cham:
  - "lot": cau unanswerable bi dua thang toi buoc tra loi (cong bo qua, hoac grader noi yes)
    -> model co nguy co bia. Day la loi NANG nhat.
  - "cham oan": cau answerable bi dua di viet lai (cong ep, hoac grader noi no).
  - "tiet kiem": ti le cau KHONG phai goi grader.
Moc so sanh: luon goi grader (lo=0, hi=inf) = hanh vi hien tai.

Chay:
    python eval/gate_sim.py eval/results/<ngay>_<label>.answers.jsonl [them file...] --label X
Ghi eval/results/<ngay>_gate-sim-<label>.md.
"""

import argparse
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "eval" / "results"
INF = float("inf")


def load_rows(paths: list[Path]) -> list[dict]:
    rows = []
    for p in paths:
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            scores = [s for s in r.get("first_scores") or [] if s is not None]
            if not scores or r.get("first_grade") not in ("yes", "no"):
                continue  # dong cu (chua co first_*) hoac loi
            rows.append({"id": r["id"], "answerable": r["type"] != "unanswerable",
                         "top1": scores[0], "grade": r["first_grade"], "src": p.name})
    return rows


def simulate(rows: list[dict], lo: float, hi: float) -> dict:
    leak = false_no = skipped = 0
    for r in rows:
        if r["top1"] >= hi:
            answers, skipped = True, skipped + 1
        elif r["top1"] < lo:
            answers, skipped = False, skipped + 1
        else:
            answers = r["grade"] == "yes"
        if r["answerable"] and not answers:
            false_no += 1
        if not r["answerable"] and answers:
            leak += 1
    return {"lo": lo, "hi": hi, "leak": leak, "false_no": false_no, "skipped": skipped}


def sweep(rows: list[dict], step: float = 0.01) -> list[dict]:
    """Moi cap (lo, hi) tren luoi; hi = INF nghia la khong bao gio bo qua grader o phia tren."""
    grid = [round(k * step, 4) for k in range(int(1 / step) + 1)]
    out = []
    for hi in grid + [INF]:
        for lo in [0.0] + [g for g in grid if g <= min(hi, 1.0)]:
            out.append(simulate(rows, lo, hi))
    return out


def best_safe(results: list[dict], base: dict) -> list[dict]:
    """Cap nguong KHONG te hon moc (lot <= moc, cham oan <= moc), xep theo tiet kiem nhieu nhat."""
    ok = [r for r in results if r["leak"] <= base["leak"] and r["false_no"] <= base["false_no"]]
    # Cung muc tiet kiem: uu tien vung bo qua hep nhat (hi cao, lo thap) cho an toan.
    return sorted(ok, key=lambda r: (-r["skipped"], -r["hi"], r["lo"]))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--label", default="gate")
    args = p.parse_args()
    rows = load_rows(args.files)
    n_ans = sum(r["answerable"] for r in rows)
    n_una = len(rows) - n_ans
    base = simulate(rows, 0.0, INF)
    results = sweep(rows)
    safe = best_safe(results, base)
    fmt = lambda x: "inf" if x == INF else f"{x:.2f}"  # noqa: E731

    lines = [
        f"# Gate simulation - {args.label}",
        "",
        f"- Ngay: {date.today().isoformat()}; nguon: {', '.join(f.name for f in args.files)}",
        f"- Mau: {len(rows)} dong ({n_ans} answerable, {n_una} unanswerable)",
        f"- Moc (luon goi grader): lot {base['leak']}/{n_una}, cham oan {base['false_no']}/{n_ans}, "
        f"tiet kiem 0/{len(rows)}",
        "",
        "## Phan bo diem rerank top1 (luot dau)",
        "",
        "| Nhom | Diem top1 (tang dan) |",
        "|---|---|",
    ]
    for name, flag in (("answerable", True), ("unanswerable", False)):
        vals = sorted(r["top1"] for r in rows if r["answerable"] == flag)
        lines.append(f"| {name} | {', '.join(f'{v:.3f}' for v in vals)} |")
    una_max = max((r["top1"] for r in rows if not r["answerable"]), default=None)
    if una_max is not None:
        above = sum(1 for r in rows if r["answerable"] and r["top1"] > una_max)
        lines += ["", f"Diem top1 cao nhat cua cau unanswerable: **{una_max:.3f}**. "
                      f"So cau answerable co top1 cao hon muc do: **{above}/{n_ans}**."]
    lines += [
        "",
        "## Cap nguong khong te hon moc, tiet kiem nhieu nhat (top 10)",
        "",
        "| lo | hi | lot (unanswerable) | cham oan (answerable) | khong goi grader |",
        "|---|---|---|---|---|",
    ]
    for r in safe[:10]:
        lines.append(f"| {fmt(r['lo'])} | {fmt(r['hi'])} | {r['leak']}/{n_una} | {r['false_no']}/{n_ans} | "
                     f"{r['skipped']}/{len(rows)} ({r['skipped'] / len(rows):.0%}) |")
    lines += [
        "",
        "## Chi bo qua o phia tren (lo = 0): tung muc hi",
        "",
        "| hi | lot | cham oan | khong goi grader |",
        "|---|---|---|---|",
    ]
    for r in results:
        if r["lo"] == 0.0 and r["hi"] != INF and round(r["hi"] * 100) % 5 == 0 and r["hi"] >= 0.5:
            lines.append(f"| {fmt(r['hi'])} | {r['leak']}/{n_una} | {r['false_no']}/{n_ans} | "
                         f"{r['skipped']}/{len(rows)} |")
    out = RESULTS_DIR / f"{date.today().isoformat()}_gate-sim-{args.label}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] Ghi {out}")


if __name__ == "__main__":
    main()
