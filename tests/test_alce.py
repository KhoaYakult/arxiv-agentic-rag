"""Cham trich dan kieu ALCE (eval/alce.py) - khong goi LLM."""

from eval.alce import build_items, build_prompt, parse_judgment, score, split_sentences

CHUNKS = [{"text": "Encoder has N = 6 layers."}, {"text": "Base model reaches 27.3 BLEU on EN-DE."},
          {"text": "We use Adam with warmup."}]


class TestSplitSentences:
    def test_sentences_bullets_and_trailing_markers(self):
        ans = "- The encoder has 6 layers [1].\n- The base model gets 27.3 BLEU. [2]\nIt trains very fast!"
        assert split_sentences(ans) == ["The encoder has 6 layers [1].", "The base model gets 27.3 BLEU. [2]",
                                        "It trains very fast!"]

    def test_drops_short_fragments_and_headings(self):
        assert split_sentences("**Tóm lại:**\n\nMô hình có 6 tầng encoder [1].") == [
            "Mô hình có 6 tầng encoder [1]."]


class TestBuildItems:
    def test_keeps_only_in_range_markers_and_strips_them(self):
        items = build_items("The encoder has 6 layers [1][9]. The paper does not say more.", CHUNKS)
        assert items[0] == {"i": 1, "sentence": "The encoder has 6 layers.", "cited": [1]}
        assert items[1]["cited"] == []

    def test_prompt_lists_only_cited_passages(self):
        items = build_items("The encoder has 6 layers [1]. It reaches 27.3 BLEU [2].", CHUNKS)
        p = build_prompt(items, CHUNKS)
        assert "[1] Encoder has N = 6 layers." in p and "[2] Base model" in p and "Adam" not in p
        assert "1. (cited: [1]) The encoder has 6 layers." in p


class TestParseJudgment:
    def test_fenced_json_and_noise(self):
        text = 'Sure:\n```json\n{"results": [{"i": 1, "combined": "yes", "each": {"1": "yes"}}]}\n```'
        assert parse_judgment(text) == {1: {"i": 1, "combined": "yes", "each": {"1": "yes"}}}

    def test_string_index_is_accepted(self):
        assert parse_judgment('{"results": [{"i": "2", "claim": true}]}') == {2: {"i": "2", "claim": True}}

    def test_garbage_is_empty(self):
        assert parse_judgment("no json here") == {}
        assert parse_judgment("{not json}") == {}


class TestScore:
    def test_recall_precision_and_uncited_claims(self):
        items = [
            {"i": 1, "sentence": "a", "cited": [1, 3]},   # day du, [3] thua
            {"i": 2, "sentence": "b", "cited": [2]},      # mot phan
            {"i": 3, "sentence": "c", "cited": []},       # khang dinh thieu trich dan
            {"i": 4, "sentence": "d", "cited": []},       # cau "khong co thong tin"
        ]
        judged = {
            1: {"combined": "yes", "each": {"1": "yes", "3": "no"}},
            2: {"combined": "partial", "each": {"2": "partial"}},
            3: {"claim": True},
            4: {"claim": False},
        }
        s = score(items, judged)
        assert (s["claims"], s["supported"], s["partial"], s["uncited_claims"]) == (3, 1, 1, 1)
        assert (s["citations"], s["useful_citations"]) == (3, 2)

    def test_missing_judgment_counts_as_unsupported(self):
        s = score([{"i": 1, "sentence": "a", "cited": [1]}], {})
        assert (s["claims"], s["supported"], s["useful_citations"]) == (1, 0, 0)
        assert s["sentences"][0]["combined"] == "no"

    def test_unknown_label_is_no(self):
        s = score([{"i": 1, "sentence": "a", "cited": [1]}], {1: {"combined": "maybe", "each": {"1": "YES"}}})
        assert s["supported"] == 0 and s["useful_citations"] == 1


class FakeClient:
    """groq.Groq gia: tra lan luot cac chuoi trong `replies`."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        outer = self

        class _Completions:
            def create(self, **kw):
                outer.calls += 1
                text = outer.replies.pop(0)
                msg = type("M", (), {"content": text})
                return type("R", (), {"choices": [type("C", (), {"message": msg})]})

        self.chat = type("Chat", (), {"completions": _Completions()})()


class TestJudgeAnswer:
    ANSWER = "The encoder has 6 layers [1]. It reaches 27.3 BLEU [2]."

    def test_retries_once_when_json_unreadable(self):
        from eval.alce import judge_answer

        good = '{"results": [{"i": 1, "combined": "yes", "each": {"1": "yes"}}, {"i": 2, "combined": "yes", "each": {"2": "yes"}}]}'
        client = FakeClient(["oops not json", good])
        out = judge_answer(client, "m", self.ANSWER, CHUNKS)
        assert client.calls == 2 and out["judge_ok"] and out["supported"] == 2

    def test_unreadable_twice_is_marked_not_ok(self):
        from eval.alce import judge_answer

        out = judge_answer(FakeClient(["bad", "still bad"]), "m", self.ANSWER, CHUNKS)
        assert out["judge_ok"] is False

    def test_no_sentences_needs_no_call(self):
        from eval.alce import judge_answer

        client = FakeClient([])
        assert judge_answer(client, "m", "", CHUNKS)["judge_ok"] and client.calls == 0
