"""Test danh so context [n] va loc marker khoi lich su chat (app/agent/rag_graph.py)."""

from app.agent.rag_graph import (
    CITATION_MARKER_RE,
    format_context,
    normalize_citation_markers,
    strip_citation_markers,
)
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


class TestNormalizeCitationMarkers:
    """gpt-oss hay trich dan kieu harmony 【1】 / 【1†L4-L5】 -> phai thanh [n] truoc khi ra API."""

    def test_harmony_style_becomes_brackets(self):
        text = "70.9 %【1†L4-L5】【2†L3-L5】. Base model 38.1【5】."
        assert normalize_citation_markers(text) == "70.9 %[1][2]. Base model 38.1[5]."

    def test_lists_and_ranges_inside_lenticular_brackets(self):
        assert normalize_citation_markers("a【1, 3】 b【2-4†L1】") == "a[1, 3] b[2-4]"

    def test_result_matches_shared_marker_grammar(self):
        out = normalize_citation_markers("x【12†L1-L2】")
        assert CITATION_MARKER_RE.fullmatch(out[1:])

    def test_leaves_normal_markers_and_other_text_alone(self):
        text = "BLEU 38.1 [1]. array a[i], 【note】 and code `【1】`"
        assert normalize_citation_markers(text) == "BLEU 38.1 [1]. array a[i], 【note】 and code `【1】`"

    def test_does_not_touch_fenced_code(self):
        text = "Ket qua【1】\n```\nprint('【2】')\n```"
        assert normalize_citation_markers(text) == "Ket qua[1]\n```\nprint('【2】')\n```"


class TestPromptAsksForMarkers:
    def test_template_mentions_bracket_citations(self):
        assert "[1, 3]" in RAG_ANSWER_TEMPLATE
        assert "Never invent" in RAG_ANSWER_TEMPLATE

    def test_template_forbids_lenticular_brackets(self):
        assert "【" in RAG_ANSWER_TEMPLATE
