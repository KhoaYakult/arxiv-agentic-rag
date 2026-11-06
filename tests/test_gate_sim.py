"""Test mo phong cong 3 tang (eval/gate_sim.py) - khong goi API."""

from eval.gate_sim import INF, best_safe, simulate

ROWS = [
    {"id": "a1", "answerable": True, "top1": 0.95, "grade": "yes"},
    {"id": "a2", "answerable": True, "top1": 0.70, "grade": "no"},  # grader cham oan
    {"id": "u1", "answerable": False, "top1": 0.80, "grade": "no"},
    {"id": "u2", "answerable": False, "top1": 0.20, "grade": "no"},
]


class TestSimulate:
    def test_baseline_always_grades(self):
        assert simulate(ROWS, 0.0, INF) == {"lo": 0.0, "hi": INF, "leak": 0, "false_no": 1, "skipped": 0}

    def test_high_threshold_skips_confident_answerable(self):
        r = simulate(ROWS, 0.0, 0.9)
        assert (r["leak"], r["false_no"], r["skipped"]) == (0, 1, 1)

    def test_threshold_below_unanswerable_score_leaks(self):
        r = simulate(ROWS, 0.0, 0.75)
        assert r["leak"] == 1  # u1 (0.80) bi tra loi thang

    def test_low_threshold_sends_to_rewrite_without_grader(self):
        r = simulate(ROWS, 0.3, 0.9)
        assert (r["leak"], r["false_no"], r["skipped"]) == (0, 1, 2)


class TestBestSafe:
    def test_keeps_only_no_worse_than_baseline_and_ranks_by_savings(self):
        results = [simulate(ROWS, lo, hi) for lo, hi in [(0.0, INF), (0.0, 0.75), (0.3, 0.9), (0.0, 0.9)]]
        base = results[0]
        safe = best_safe(results, base)
        assert all(r["leak"] <= base["leak"] and r["false_no"] <= base["false_no"] for r in safe)
        assert (safe[0]["lo"], safe[0]["hi"]) == (0.3, 0.9)
