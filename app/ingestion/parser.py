"""
app/ingestion/parser.py
========================
Module trích xuất file PDF bài báo khoa học (arXiv) sang định dạng Markdown có cấu trúc.
Giữ nguyên tiêu đề (Heading #, ##), công thức LaTeX ($...$) và bảng biểu HTML/Markdown.
"""

import sys
from pathlib import Path

# Tự động thêm thư mục gốc dự án vào sys.path khi chạy file trực tiếp
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pymupdf4llm
from app.config import settings


def parse_pdf_to_markdown(pdf_path: str | Path) -> str:
    """
    Chuyển đổi file PDF bài báo khoa học thành chuỗi Markdown có cấu trúc.

    Args:
        pdf_path: Đường dẫn tới file PDF.

    Returns:
        str: Chuỗi văn bản Markdown đã trích xuất.

    Raises:
        FileNotFoundError: Nếu không tìm thấy file PDF tại đường dẫn chỉ định.
        RuntimeError: Nếu quá trình parse PDF thất bại (file hỏng, có password...).
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"[ERROR] Khong tim thay file PDF tai: {pdf_path}")

    print(f"[INFO] Bat dau parse file: {pdf_path.name} ...")

    try:
        md_text = pymupdf4llm.to_markdown(str(pdf_path))
    except Exception as e:
        print(f"[WARN] pymupdf4llm loi hoac het RAM tren Server: {e}", flush=True)
        print("[INFO] Chuyen sang che do fallback PyMuPDF (fitz) sieu nhe (15MB RAM)...", flush=True)
        try:
            import fitz
            doc = fitz.open(pdf_path)
            pages_text = []
            for page in doc:
                text = page.get_text()
                if text.strip():
                    pages_text.append(text)
            md_text = "\n\n".join(pages_text)
        except Exception as e2:
            raise RuntimeError(
                f"[ERROR] Parse PDF thất bại hoàn toàn.\nLỗi 1: {e}\nLỗi 2: {e2}"
            ) from e2

    if not md_text or not md_text.strip():
        raise RuntimeError(
            f"[ERROR] Parse thanh cong nhung ket qua trong rong. "
            f"Kiem tra lai file PDF: {pdf_path.name}"
        )

    print(f"[SUCCESS] Parse xong! Tong: {len(md_text)} ky tu tu {pdf_path.name}.")
    return md_text


if __name__ == "__main__":
    sample_pdfs = list(settings.data_dir.glob("*.pdf"))
    if sample_pdfs:
        md = parse_pdf_to_markdown(sample_pdfs[0])
        print("\n--- XEM 500 KY TU DAU ---")
        print(md[:500])
    else:
        print(f"[NOTICE] Chua co file PDF nao trong: {settings.data_dir}")