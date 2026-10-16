"""
app/ingestion/parser.py
========================
Module trích xuất file PDF bài báo khoa học (arXiv) sang định dạng Markdown có cấu trúc.
Giữ nguyên tiêu đề (Heading #, ##), công thức LaTeX ($...$) và bảng biểu HTML/Markdown.

Kết quả parse được biểu diễn THEO TỪNG TRANG (PageText) trước, rồi mới ghép thành 1
chuỗi Markdown có marker "<!-- page:N -->" (pages_to_markdown). Nhờ vậy cả đường chính
(pymupdf4llm) lẫn đường dự phòng (fitz) đều có số trang - trước đây đường dự phòng
không chèn marker nên page_num của chunk luôn là None.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

# Tự động thêm thư mục gốc dự án vào sys.path khi chạy file trực tiếp
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pymupdf4llm

from app.config import settings


@dataclass
class PageText:
    """Nội dung 1 trang PDF: page_num đánh số từ 1, text là Markdown (hoặc text thô) của trang."""
    page_num: int
    text: str


def pages_to_markdown(pages: list[PageText]) -> str:
    """
    Ghép các trang thành 1 chuỗi Markdown, chèn marker "<!-- page:N -->" trước nội dung
    mỗi trang (bỏ qua trang trống). chunker.py đọc marker này để gán page_num cho
    section/chunk (xem split_parent_sections và create_child_chunks).
    """
    parts = [
        f"<!-- page:{p.page_num} -->\n{p.text}"
        for p in pages
        if p.text.strip()
    ]
    return "\n\n".join(parts)


def parse_pdf_to_pages(pdf_path: str | Path) -> list[PageText]:
    """
    Trích xuất PDF thành danh sách PageText (theo từng trang).

    Đường chính: pymupdf4llm (giữ bảng, công thức, đa cột). Nếu lỗi (vd hết RAM trên
    server miễn phí) chuyển sang fitz thuần (rất nhẹ, text thô từng trang).

    Raises:
        FileNotFoundError: Nếu không tìm thấy file PDF.
        RuntimeError: Nếu cả 2 đường đều lỗi, hoặc kết quả rỗng.
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"[ERROR] Khong tim thay file PDF tai: {pdf_path}")

    print(f"[INFO] Bat dau parse file: {pdf_path.name} ...")

    try:
        result = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
        if not isinstance(result, list):
            raise TypeError(
                f"pymupdf4llm(page_chunks=True) tra ve {type(result).__name__}, can list[dict]"
            )
        # page_chunks=True tra ve list[dict], moi phan tu la 1 trang:
        # {"text": ..., "metadata": {"page": ...}, "toc_items": [...], ...}
        pages = [
            PageText(
                page_num=page.get("metadata", {}).get("page", i + 1),
                text=page.get("text", ""),
            )
            for i, page in enumerate(result)
        ]
    except Exception as e:
        print(f"[WARN] pymupdf4llm loi hoac het RAM tren Server: {e}", flush=True)
        print("[INFO] Chuyen sang che do fallback PyMuPDF (fitz) sieu nhe (15MB RAM)...", flush=True)
        try:
            import fitz
            doc = fitz.open(pdf_path)
            pages = [
                PageText(page_num=i + 1, text=page.get_text())
                for i, page in enumerate(doc)
            ]
        except Exception as e2:
            raise RuntimeError(
                f"[ERROR] Parse PDF thất bại hoàn toàn.\nLỗi 1: {e}\nLỗi 2: {e2}"
            ) from e2

    if not any(p.text.strip() for p in pages):
        raise RuntimeError(
            f"[ERROR] Parse thanh cong nhung ket qua trong rong. "
            f"Kiem tra lai file PDF: {pdf_path.name}"
        )

    return pages


def parse_pdf_to_markdown(pdf_path: str | Path) -> str:
    """
    Chuyển đổi file PDF bài báo khoa học thành 1 chuỗi Markdown có marker trang.

    Args:
        pdf_path: Đường dẫn tới file PDF.

    Returns:
        str: Chuỗi Markdown, mỗi trang bắt đầu bằng "<!-- page:N -->".

    Raises:
        FileNotFoundError, RuntimeError: xem parse_pdf_to_pages.
    """
    pdf_path = Path(pdf_path)
    md_text = pages_to_markdown(parse_pdf_to_pages(pdf_path))
    print(f"[SUCCESS] Tong: {len(md_text)} ky tu tu {pdf_path.name}.")
    return md_text


if __name__ == "__main__":
    sample_pdfs = list(settings.data_dir.glob("*.pdf"))
    if sample_pdfs:
        md = parse_pdf_to_markdown(sample_pdfs[0])
        print("\n--- XEM 500 KY TU DAU ---")
        print(md[:500])
    else:
        print(f"[NOTICE] Chua co file PDF nao trong: {settings.data_dir}")
