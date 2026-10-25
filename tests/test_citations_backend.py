"""Test danh so context [n] va loc marker khoi lich su chat (app/agent/rag_graph.py)."""

from app.agent.rag_graph import format_context, strip_citation_markers
from app.llm.prompt_templates import RAG_ANSWER_TEMPLATE


class TestFormatContext:
    def test_numbers_in_list_order_with_section_and_page(self):
        chunks = [
            {"parent_section_name": "6 Results", "text": "BLEU 38.1", "page_num": 8},
            {"parent_section_name": "Intro", "text": "We propose", "page_num": None},
        ]
        assert format_context(chunks) == (
            "[1] (Section: 6 Results, page 8)\nBLEU 38.1\n\n---\n\n[2] (Section: Intro)\nWe propose"
        )

    def test_missing_section_name_falls_back(self):
        assert format_context([{"text": "t", "page_num": 1}]).startswith("[1] (Section: Unknown section, page 1)")

    def test_empty(self):
        assert format_context([]) == ""


class TestStripCitationMarkers:
    def test_removes_all_marker_forms(self):
        text = "BLEU 38.1 [1]. Cost [2, 3] and [4-5] or [6–7]."
        assert strip_citation_markers(text) == "BLEU 38.1. Cost and or."

    def test_keeps_non_marker_brackets(self):
        assert strip_citation_markers("array a[i] and [x]") == "array a[i] and [x]"


class TestPromptAsksForMarkers:
    def test_template_mentions_bracket_citations(self):
        assert "[1, 3]" in RAG_ANSWER_TEMPLATE
        assert "Never invent" in RAG_ANSWER_TEMPLATE
