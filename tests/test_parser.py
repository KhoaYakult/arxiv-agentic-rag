"""
Test parser.py: ghép trang -> Markdown có marker, và đường dự phòng fitz cũng có marker trang.
Không cần mạng/API key: tự tạo PDF nhỏ bằng fitz trong thư mục tạm.
"""

import fitz
import pytest

from app.ingestion import parser
from app.ingestion.parser import PageText, pages_to_markdown, parse_pdf_to_pages


def _make_pdf(path, page_texts):
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


class TestPagesToMarkdown:
    def test_marker_precedes_each_page(self):
        md = pages_to_markdown([PageText(1, "aaa"), PageText(2, "bbb")])
        assert md == "<!-- page:1 -->\naaa\n\n<!-- page:2 -->\nbbb"

    def test_blank_pages_are_skipped_but_numbers_are_kept(self):
        md = pages_to_markdown([PageText(1, "aaa"), PageText(2, "  \n"), PageText(3, "ccc")])
        assert "page:2" not in md
        assert "<!-- page:3 -->\nccc" in md

    def test_no_pages_gives_empty_string(self):
        assert pages_to_markdown([]) == ""


class TestFitzFallbackKeepsPageNumbers:
    def test_fallback_emits_page_markers(self, tmp_path, monkeypatch):
        pdf = tmp_path / "two_pages.pdf"
        _make_pdf(pdf, ["First page text", "Second page text"])

        def boom(*args, **kwargs):
            raise MemoryError("gia lap het RAM")

        monkeypatch.setattr(parser.pymupdf4llm, "to_markdown", boom)

        pages = parse_pdf_to_pages(pdf)
        assert [p.page_num for p in pages] == [1, 2]
        md = pages_to_markdown(pages)
        assert "<!-- page:1 -->" in md and "<!-- page:2 -->" in md
        assert "Second page text" in md

    def test_all_blank_pdf_raises(self, tmp_path, monkeypatch):
        pdf = tmp_path / "blank.pdf"
        _make_pdf(pdf, [""])
        monkeypatch.setattr(parser.pymupdf4llm, "to_markdown", lambda *a, **k: [{"text": "", "metadata": {"page": 1}}])
        with pytest.raises(RuntimeError):
            parse_pdf_to_pages(pdf)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_pdf_to_pages(tmp_path / "nope.pdf")
