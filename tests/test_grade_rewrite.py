"""Test context cua grade_node va prompt rewrite (app/agent/rag_graph.py, app/llm/prompt_templates.py)."""

from app.agent.rag_graph import format_grade_context


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
