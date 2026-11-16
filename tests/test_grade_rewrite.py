"""Test context cua grade_node va prompt rewrite (app/agent/rag_graph.py, app/llm/prompt_templates.py)."""

from app.agent.rag_graph import format_grade_context
from app.llm.prompt_templates import REWRITE_QUERY_TEMPLATE


class TestFormatGradeContext:
    def test_keeps_full_chunk_text(self):
        # Evidence nam sau ky tu 400 phai van con (truoc day bi cat [:400]).
        text = "a" * 500 + " Transformer (base model) 38.1"
        out = format_grade_context([{"parent_section_name": "6 Results", "text": text}])
        assert out == f"[Chunk 1] Section: 6 Results\n{text}"

    def test_numbers_chunks_and_joins_with_separator(self):
        chunks = [
            {"parent_section_name": "Intro", "text": "x"},
            {"parent_section_name": "Method", "text": "y"},
        ]
        assert format_grade_context(chunks) == (
            "[Chunk 1] Section: Intro\nx\n\n---\n\n[Chunk 2] Section: Method\ny"
        )

    def test_empty(self):
        assert format_grade_context([]) == ""


class TestRewriteTemplate:
    def test_does_not_ask_to_expand_abbreviations(self):
        assert "Expand abbreviations" not in REWRITE_QUERY_TEMPLATE
        assert "do NOT expand" in REWRITE_QUERY_TEMPLATE

    def test_forbids_adding_details(self):
        assert "Do NOT add facts" in REWRITE_QUERY_TEMPLATE

    def test_only_input_is_question(self):
        from langchain_core.prompts import ChatPromptTemplate

        assert ChatPromptTemplate.from_template(REWRITE_QUERY_TEMPLATE).input_variables == ["question"]


class TestParseGrade:
    def test_yes_only_at_start(self):
        from app.agent.rag_graph import parse_grade

        assert parse_grade("yes") == "yes"
        assert parse_grade("  Yes.") == "yes"
        assert parse_grade('"yes"') == "yes"
        assert parse_grade("**Yes**") == "yes"

    def test_no_and_mentions_of_yes_are_no(self):
        from app.agent.rag_graph import parse_grade

        assert parse_grade("no") == "no"
        assert parse_grade("No, not yes") == "no"  # kieu cu `"yes" in text` hieu nham thanh yes
        assert parse_grade("") == "no"


class TestGetGraderLlm:
    """Khong goi mang: get_llm() bi thay bang Runnable gia."""

    def _setup(self, monkeypatch, groq_key: str, grader_model: str):
        from langchain_core.runnables import RunnableLambda

        from app.config import settings
        from app.llm import llm_factory

        fake = RunnableLambda(lambda _: "fallback")
        monkeypatch.setattr(llm_factory, "get_llm", lambda *a, **kw: fake)
        monkeypatch.setattr(settings, "groq_api_key", groq_key)
        monkeypatch.setattr(settings, "grader_model", grader_model)
        llm_factory.get_grader_llm.cache_clear()
        return llm_factory, fake

    def test_uses_groq_grader_model_with_fallback(self, monkeypatch):
        llm_factory, fake = self._setup(monkeypatch, "gsk_test", "qwen/qwen3.8-27b")
        llm = llm_factory.get_grader_llm()
        assert llm.runnable.model_name == "qwen/qwen3.8-27b"
        assert llm.runnable.reasoning_effort == "none"
        assert llm.fallbacks == [fake]
        llm_factory.get_grader_llm.cache_clear()

    def test_empty_grader_model_uses_get_llm(self, monkeypatch):
        llm_factory, fake = self._setup(monkeypatch, "gsk_test", "")
        assert llm_factory.get_grader_llm() is fake
        llm_factory.get_grader_llm.cache_clear()

    def test_no_groq_key_uses_get_llm(self, monkeypatch):
        llm_factory, fake = self._setup(monkeypatch, "", "qwen/qwen3.8-27b")
        assert llm_factory.get_grader_llm() is fake
        llm_factory.get_grader_llm.cache_clear()
