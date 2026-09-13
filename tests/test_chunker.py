"""
Test cac ham thuan (khong goi network/API) trong app/ingestion/chunker.py.
"""

from app.ingestion.chunker import _find_split_point, split_parent_sections


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
