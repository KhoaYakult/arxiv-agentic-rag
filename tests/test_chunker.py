"""
Test cac ham thuan (khong goi network/API) trong app/ingestion/chunker.py.
"""

from app.ingestion.chunker import (
    ChildChunk,
    ParentSection,
    _find_split_point,
    _page_at,
    _strip_page_markers,
    create_child_chunks,
    split_parent_sections,
)


class TestFindSplitPoint:
    def test_target_beyond_text_length_returns_full_length(self):
        text = "short text"
        assert _find_split_point(text, target=1000) == len(text)

    def test_prefers_paragraph_boundary(self):
        # "\n\n" nam trong vung [target*0.25, target]
        text = "A" * 40 + "\n\n" + "B" * 60
        target = 42  # ngay sau doan "\n\n" dau tien
        pos = _find_split_point(text, target)
        assert text[:pos].endswith("\n\n")

    def test_falls_back_to_sentence_boundary_when_no_paragraph(self):
        # Khong co "\n\n", nhung co dau cham + khoang trang trong vung sentence-window
        text = "A" * 30 + ". " + "B" * 70
        target = 60
        pos = _find_split_point(text, target)
        # Vi tri cat phai ngay sau dau "." + khoang trang
        assert text[:pos].rstrip().endswith(".")

    def test_fallback_space_is_near_target_not_near_start(self):
        """
        Regression test cho bug: fallback #3 tung tra ve mot vi tri gan DAU
        chuoi (~50 ky tu) thay vi tim khoang trang gan `target`.
        """
        text = "a" * 40 + " " + "b" * 400  # 1 khoang trang duy nhat, o vi tri 40
        target = 100
        pos = _find_split_point(text, target)
        assert pos == 41  # ngay sau khoang trang duy nhat trong vung tim kiem
        assert pos <= target

    def test_hard_cut_when_nothing_found(self):
        # Khong khoang trang, khong dau cau, khong doan van -> cat cung tai target
        text = "a" * 500
        target = 100
        assert _find_split_point(text, target) == target


class TestSplitParentSections:
    def test_no_headings_falls_back_to_single_section(self):
        text = "Just a plain paragraph with no markdown headings at all, long enough."
        sections = split_parent_sections(text)
        assert len(sections) == 1
        assert sections[0].section_id == "sec_0"
        assert sections[0].section_name == "Full_Document"
        assert sections[0].text == text

    def test_markdown_headings_split_into_sections(self):
        text = (
            "# Abstract\n"
            "This is the abstract of the paper with enough characters to survive the min-length filter.\n\n"
            "# Introduction\n"
            "This is the introduction section with enough characters to survive the min-length filter.\n\n"
            "# Conclusion\n"
            "This is the conclusion section with enough characters to survive the min-length filter.\n"
        )
        sections = split_parent_sections(text)
        names = [s.section_name for s in sections]
        assert names == ["Abstract", "Introduction", "Conclusion"]

    def test_short_sections_are_dropped(self):
        text = (
            "# Real Section\n"
            "This section has plenty of content to pass the 30-character minimum length filter.\n\n"
            "# X\n"
            "short\n"  # ten qua ngan (< 3 ky tu) VA noi dung qua ngan (< 30 ky tu)
        )
        sections = split_parent_sections(text)
        names = [s.section_name for s in sections]
        assert "Real Section" in names
        assert "X" not in names

    def test_leading_text_before_first_heading_becomes_header_section(self):
        text = (
            "arXiv:2301.00001v1 [cs.CV] some journal header line\n\n"
            "# Abstract\n"
            "This is the abstract of the paper with enough characters to survive the filter.\n"
        )
        sections = split_parent_sections(text)
        assert sections[0].section_name == "Header"
        assert sections[1].section_name == "Abstract"


class TestStripPageMarkers:
    def test_no_markers_returns_text_unchanged_and_empty_breakpoints(self):
        text = "plain text without markers"
        cleaned, breakpoints = _strip_page_markers(text)
        assert cleaned == text
        assert breakpoints == []

    def test_single_marker_is_removed_and_recorded(self):
        text = "<!-- page:3 -->\nHello world"
        cleaned, breakpoints = _strip_page_markers(text)
        assert cleaned == "Hello world"
        assert breakpoints == [(0, 3)]

    def test_multiple_markers_recorded_at_correct_offsets(self):
        text = "<!-- page:1 -->\nAAAA<!-- page:2 -->\nBBBB"
        cleaned, breakpoints = _strip_page_markers(text)
        assert cleaned == "AAAABBBB"
        assert breakpoints == [(0, 1), (4, 2)]


class TestPageAt:
    def test_empty_breakpoints_returns_none(self):
        assert _page_at([], 10) is None

    def test_offset_before_first_breakpoint_returns_none(self):
        assert _page_at([(5, 2)], 0) is None

    def test_offset_at_breakpoint_returns_that_page(self):
        assert _page_at([(0, 1), (10, 2)], 10) == 2

    def test_offset_between_breakpoints_returns_earlier_page(self):
        assert _page_at([(0, 1), (10, 2)], 7) == 1


class TestCreateChildChunksPageAwareness:
    def test_short_section_gets_page_num_and_full_span_offsets(self):
        sections = [ParentSection(
            section_id="sec_0",
            section_name="Abstract",
            text="<!-- page:1 -->\nThis is a short abstract section.",
        )]
        chunks = create_child_chunks(sections, paper_id="p1", max_chars=800, overlap_chars=150)
        assert len(chunks) == 1
        assert isinstance(chunks[0], ChildChunk)
        assert chunks[0].page_num == 1
        assert chunks[0].char_start == 0
        assert chunks[0].char_end == len(chunks[0].text)
        assert "<!-- page:" not in chunks[0].text

    def test_section_spanning_two_pages_assigns_different_page_nums(self):
        text = (
            "<!-- page:1 -->\n" + ("A" * 40 + " ") * 5 +
            "<!-- page:2 -->\n" + ("B" * 40 + " ") * 30
        )
        sections = [ParentSection(section_id="sec_0", section_name="Method", text=text)]
        chunks = create_child_chunks(sections, paper_id="p1", max_chars=200, overlap_chars=20)
        pages = {c.page_num for c in chunks}
        assert pages == {1, 2}
        assert chunks[0].page_num == 1
        assert chunks[-1].page_num == 2

    def test_no_page_markers_leaves_page_num_none(self):
        sections = [ParentSection(
            section_id="sec_0",
            section_name="NoMarkers",
            text="Plain text with no page markers at all, long enough to survive filters.",
        )]
        chunks = create_child_chunks(sections, paper_id="p1", max_chars=800, overlap_chars=150)
        assert all(c.page_num is None for c in chunks)

    def test_char_offsets_span_exactly_the_chunk_text_length(self):
        text = "A" * 50 + " " + "B" * 400  # forces the sliding-window branch
        sections = [ParentSection(section_id="sec_0", section_name="Long", text=text)]
        chunks = create_child_chunks(sections, paper_id="p1", max_chars=100, overlap_chars=10)
        assert len(chunks) > 1
        for c in chunks:
            assert c.char_end - c.char_start == len(c.text)
