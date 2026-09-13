"""
Test ham tokenize() trong app/indexing/bm25_store.py.
"""

from app.indexing.bm25_store import tokenize


class TestTokenize:
    def test_lowercases_input(self):
        assert tokenize("CortexODE") == ["cortexode"]

    def test_drops_single_character_tokens(self):
        assert tokenize("a big I x model") == ["big", "model"]

    def test_keeps_decimal_numbers_as_one_token(self):
        assert tokenize("accuracy 0.939 on the test set") == [
            "accuracy",
            "0.939",
            "on",
            "the",
            "test",
            "set",
        ]

    def test_keeps_hyphenated_scientific_terms_as_one_token(self):
        assert tokenize("a state-of-the-art model") == ["state-of-the-art", "model"]

    def test_splits_on_punctuation_not_in_pattern(self):
        assert tokenize("MRI, CT; PET.") == ["mri", "ct", "pet"]

    def test_empty_string_returns_empty_list(self):
        assert tokenize("") == []
