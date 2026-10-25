"""Test thuần (không mạng/DB) cho eval/metrics.py - ví dụ nhỏ tính tay."""

import math

import pytest

from eval import metrics as m


def test_norm_ligatures_case_and_punctuation():
    assert m.norm("eﬃcient ﬁnal ﬂow diﬀer baﬄe") == "efficientfinalflowdifferbaffle"
    assert m.norm("BLEU: 38.1 (x10^18)!") == "bleu381x1018"
    assert m.norm("Chỉ ASCII") == "chascii"  # ký tự có dấu bị bỏ


def test_shingles():
    assert m.shingles("abcdefghij") == {"abcdefgh", "bcdefghi", "cdefghij"}
    assert m.shingles("abc") == {"abc"}  # ngắn hơn 8 -> 1 shingle
    assert m.shingles("") == set()


def test_strict_relevance():
    chunk = "The Trans-former reaches 38.1 BLEU on WMT."
    assert m.is_relevant(chunk, ["transformer reaches 38.1 bleu"], "strict")
    assert not m.is_relevant(chunk, ["transformer reaches 41.8 bleu"], "strict")
    # nhiều quote: chỉ cần 1 quote khớp
    assert m.is_relevant(chunk, ["khong co", "38.1 BLEU"], "strict")
    assert not m.is_relevant(chunk, [""], "strict")  # quote rỗng không khớp


def test_strict_handles_ligature_in_chunk():
    assert m.is_relevant("an eﬃcient method", ["efficient method"], "strict")


def test_lenient_relevance_threshold():
    quote = "abcdefghijklmnopqrstuvwxyz"  # 26 ký tự -> 19 shingle
    assert m.is_relevant("abcdefghijklmnopqrstuvwxy", [quote], "lenient")  # 18/19
    assert not m.is_relevant("abcdefghijklmnopq", [quote], "lenient")  # 10/19
    # lenient bắt được ô bảng bị đảo thứ tự mà strict bỏ lỡ
    # quote 60 ký tự (53 shingle); chuyển từ cuối lên đầu -> mất 7 shingle (~87% còn lại)
    row_quote = "alpha1 bravo2 charl3 delta4 echoo5 foxtr6 golfa7 hotel8 india9 julie0"
    reordered = "julie0 alpha1 bravo2 charl3 delta4 echoo5 foxtr6 golfa7 hotel8 india9"
    assert not m.is_relevant(reordered, [row_quote], "strict")
    assert m.is_relevant(reordered, [row_quote], "lenient")
    assert not m.is_relevant("zzzz", [row_quote], "lenient")
    # Đúng 80%: quote 12 ký tự -> 5 shingle; chunk chứa 4 shingle đầu -> 4/5 = 0.8
    q12 = "abcdefghijkl"
    assert m.is_relevant("abcdefghijk", [q12], "lenient")  # 4/5
    assert not m.is_relevant("abcdefghij", [q12], "lenient")  # 3/5


def test_relevance_invalid_mode():
    with pytest.raises(ValueError):
        m.is_relevant("a", ["a"], "fuzzy")


def test_hit_at_k():
    rels = [False, False, True, False, True]
    assert m.hit_at_k(rels, 1) == 0.0
    assert m.hit_at_k(rels, 2) == 0.0
    assert m.hit_at_k(rels, 3) == 1.0
    assert m.hit_at_k(rels, 20) == 1.0
    assert m.hit_at_k([], 5) == 0.0


def test_first_relevant_rank_and_mrr():
    assert m.first_relevant_rank([False, True, True]) == 2
    assert m.first_relevant_rank([False, False]) is None
    assert m.mrr_at_k([False, True, True]) == pytest.approx(0.5)
    assert m.mrr_at_k([True]) == 1.0
    assert m.mrr_at_k([False] * 3) == 0.0
    # chunk liên quan nằm ngoài top k thì không tính
    assert m.mrr_at_k([False] * 5 + [True], k=5) == 0.0
    assert m.mrr_at_k([False] * 5 + [True], k=6) == pytest.approx(1 / 6)


def test_ndcg():
    # 1 chunk liên quan ở rank 1 -> hoàn hảo
    assert m.ndcg_at_k([True, False, False]) == pytest.approx(1.0)
    # 1 chunk liên quan ở rank 3: DCG = 1/log2(4) = 0.5; ideal = 1 -> 0.5
    assert m.ndcg_at_k([False, False, True]) == pytest.approx(0.5)
    # 2 chunk liên quan ở rank 2 và 4: DCG = 1/log2(3) + 1/log2(5)
    # ideal = 1/log2(2) + 1/log2(3) = 1 + 0.6309
    expected = (1 / math.log2(3) + 1 / math.log2(5)) / (1 + 1 / math.log2(3))
    assert m.ndcg_at_k([False, True, False, True]) == pytest.approx(expected)
    # không có chunk nào -> 0 (ideal = 1, tránh chia 0)
    assert m.ndcg_at_k([False] * 5) == 0.0
    assert m.ndcg_at_k([]) == 0.0


def test_ndcg_cutoff_and_ideal_cap():
    # Chunk liên quan ở rank 11 nằm ngoài k=10: DCG = 0 dù có trong top 20
    rels = [False] * 10 + [True]
    assert m.ndcg_at_k(rels, k=10) == 0.0
    # 12 chunk liên quan liên tiếp: ideal chặn ở 10 -> nDCG = 1
    assert m.ndcg_at_k([True] * 12, k=10) == pytest.approx(1.0)


def test_question_metrics_and_aggregate():
    q1 = m.question_metrics([True, False])  # hit@1=1, mrr=1
    q2 = m.question_metrics([False, False, True])  # hit@1=0, hit@3=1, mrr=1/3
    assert q1["hit@1"] == 1.0 and q2["hit@1"] == 0.0
    assert q2["hit@3"] == 1.0 and q2["hit@5"] == 1.0
    agg = m.aggregate([q1, q2])
    assert agg["hit@1"] == pytest.approx(0.5)
    assert agg["hit@3"] == pytest.approx(1.0)
    assert agg["mrr@20"] == pytest.approx((1 + 1 / 3) / 2)
    assert m.aggregate([]) == {}


def test_group_mean():
    per_q = [{"hit@5": 1.0}, {"hit@5": 0.0}, {"hit@5": 1.0}]
    out = m.group_mean(per_q, ["en", "vi", "en"], "hit@5")
    assert out == {"en": (1.0, 2), "vi": (0.0, 1)}


class TestCitationMarkers:
    def test_forms(self):
        from eval.metrics import citation_markers

        assert citation_markers("a [2]. b [1, 3]. c [4-6] d [2]") == [2, 1, 3, 4, 5, 6]
        assert citation_markers("en dash [7–8]") == [7, 8]

    def test_ignores_non_markers_and_huge_ranges(self):
        from eval.metrics import citation_markers

        assert citation_markers("a[i] [x] [1-500]") == []
        assert citation_markers("no markers") == []


class TestScoreAnswer:
    def test_valid_out_of_range_and_precision(self):
        from eval.check_citations import score_answer

        chunks = [{"text": "Transformer (base model) 27.3 38.1"}, {"text": "unrelated"}]
        s = score_answer("BLEU 38.1 [1] and [9]", chunks, ["Transformer (base model) 27.3 38.1"])
        assert s == {"markers": [1, 9], "valid": [1], "out_of_range": 1, "precise": True}
        assert score_answer("no cite", chunks, ["x"])["precise"] is False
