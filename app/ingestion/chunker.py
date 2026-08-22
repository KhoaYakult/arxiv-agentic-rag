"""
app/ingestion/chunker.py
=========================
Module thực hiện thuật toán Section-Based Parent-Child Chunking.
Tách văn bản Markdown thành:
 1. ParentSection: Lưu ngữ cảnh lớn của từng Section (Abstract, Intro, Method...)
 2. ChildChunk:    Lưu các đoạn nhỏ để tính Vector Embedding & lưu vào Vector DB
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Tự động thêm thư mục gốc dự án vào sys.path khi chạy file trực tiếp
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import settings


# ──────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ParentSection:
    """Đại diện cho 1 Section lớn trong bài báo (Parent context)."""
    section_id: str
    section_name: str
    text: str


@dataclass
class ChildChunk:
    """Đại diện cho 1 Chunk nhỏ phục vụ tìm kiếm Vector (Child context)."""
    chunk_id: str
    parent_section_id: str
    parent_section_name: str
    paper_id: str
    text: str
    is_table: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: phát hiện Markdown table
# ──────────────────────────────────────────────────────────────────────────────

# Markdown table chuẩn có ít nhất 2 dòng: dòng header "|...|" và dòng phân cách "|---|"
_TABLE_PATTERN = re.compile(r"^\|.+\|[\s]*$", re.MULTILINE)
_TABLE_SEP_PATTERN = re.compile(r"^\|[\s\-\|:]+\|[\s]*$", re.MULTILINE)


def _is_table_chunk(text: str) -> bool:
    """Trả về True nếu đoạn văn bản chứa Markdown table."""
    return bool(_TABLE_PATTERN.search(text)) and bool(_TABLE_SEP_PATTERN.search(text))


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: cắt văn bản tại ranh giới câu (không cắt giữa chừng một từ)
# ──────────────────────────────────────────────────────────────────────────────

# Dấu kết thúc câu: ".", "!", "?", "..." theo sau là khoảng trắng hoặc xuống dòng
_SENTENCE_BOUNDARY = re.compile(r'(?<=[.!?])\s+')


def _find_split_point(text: str, target: int) -> int:
    """
    Tìm vị trí cắt gần nhất với `target` mà không cắt giữa chừng một từ/câu.
    Ưu tiên theo thứ tự: ranh giới đoạn (\\n\\n) > ranh giới câu > ranh giới từ.
    """
    if target >= len(text):
        return len(text)

    # 1. Ưu tiên: tìm xuống dòng đôi (ranh giới đoạn) trong vùng [target-200, target]
    search_start = max(0, target - 200)
    para_boundary = text.rfind("\n\n", search_start, target)
    if para_boundary != -1:
        return para_boundary + 2

    # 2. Tìm ranh giới câu (.  !  ?) trong vùng [target-150, target]
    search_start = max(0, target - 150)
    window = text[search_start:target]
    for m in reversed(list(_SENTENCE_BOUNDARY.finditer(window))):
        return search_start + m.end()

    # 3. Fallback: tìm khoảng trắng gần nhất (không cắt giữa từ)
    space_pos = text.rfind(" ", max(0, target - 50), target)
    if space_pos != -1:
        return space_pos + 1

    # 4. Cuối cùng: cắt cứng tại target (không tránh được)
    return target


# ──────────────────────────────────────────────────────────────────────────────
# CORE: phân tách Markdown thành Parent Sections
# ──────────────────────────────────────────────────────────────────────────────

def split_parent_sections(markdown_text: str) -> list[ParentSection]:
    """
    Tách chuỗi Markdown thành danh sách các ParentSection một cách ĐỘNG.
    Tự động nhận diện tiêu đề Markdown (#, ##, ###), số La Mã IEEE (I., II., III.),
    và tiêu đề in đậm (**TITLE**) mà không phụ thuộc vào danh sách từ khóa cố định.
    """
    heading_pattern = re.compile(
        r"^(?:"
        r"#{1,4}\s+([^\n]+)|"                               # Dạng 1: # Title  hoặc  ## Sub Title
        r"\*\*\s*(?:[IVXLCDM]+\.|\d+\.)?\s*([^\n\*]+)\*\*|" # Dạng 2: **I. TITLE**  hoặc  **TITLE**
        r"(?:[IVXLCDM]+\.|\d+\.)\s+([A-Z0-9\s\:\-\_]{3,})$" # Dạng 3: I. TITLE ALL CAPS
        r")",
        re.MULTILINE
    )

    matches = list(heading_pattern.finditer(markdown_text))

    # Fallback nếu không tìm thấy tiêu đề nào
    if not matches:
        return [ParentSection(
            section_id="sec_0",
            section_name="Full_Document",
            text=markdown_text
        )]

    sections: list[ParentSection] = []

    # Phần Header trước tiêu đề đầu tiên (ví dụ: tên tạp chí, số trang...)
    if matches[0].start() > 0:
        header_text = markdown_text[:matches[0].start()].strip()
        if header_text:
            sections.append(ParentSection(
                section_id="sec_0",
                section_name="Header",
                text=header_text
            ))

    for i, match in enumerate(matches):
        # Lấy toàn bộ dòng tiêu đề thô, loại bỏ ký tự định dạng Markdown
        raw_heading = match.group(0).strip()
        clean_name = re.sub(r"^[#\*\_\s]+|[#\*\_\s]+$", "", raw_heading).strip()

        # Làm gọn tên section nếu tiêu đề chứa mô tả dài sau dấu "—" hoặc ":"
        for sep in ("—", "–"):
            if sep in clean_name and len(clean_name) > 40:
                clean_name = clean_name.split(sep)[0].strip()
                break
        if ":" in clean_name and len(clean_name) > 50:
            clean_name = clean_name.split(":")[0].strip()

        # Xóa lại ký tự định dạng thừa sau khi đã tách separator (vd: "Abstract_" → "Abstract")
        clean_name = re.sub(r"[#\*\_\s]+$", "", clean_name).strip()
        clean_name = re.sub(r"^[#\*\_\s]+", "", clean_name).strip()

        # Giới hạn độ dài tên section tối đa 60 ký tự
        clean_name = clean_name[:60].strip()

        start_idx = match.start()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
        sec_text = markdown_text[start_idx:end_idx].strip()

        # Bỏ qua section có tên quá ngắn (< 3 ký tự: bắt nhầm chữ cái đơn lẻ)
        # hoặc nội dung quá ngắn (< 30 ký tự: không mang thông tin)
        if len(clean_name) < 3 or not sec_text or len(sec_text) < 30:
            continue

        sections.append(ParentSection(
            section_id=f"sec_{len(sections)}",
            section_name=clean_name or f"Section_{len(sections)}",
            text=sec_text
        ))

    return sections


# ──────────────────────────────────────────────────────────────────────────────
# CORE: cắt Parent Sections thành Child Chunks
# ──────────────────────────────────────────────────────────────────────────────

def create_child_chunks(
    sections: list[ParentSection],
    paper_id: str,
    max_chars: int = settings.chunk_size,
    overlap_chars: int = settings.chunk_overlap,
) -> list[ChildChunk]:
    """
    Cắt từng ParentSection thành các ChildChunk nhỏ bằng kỹ thuật cửa sổ trượt
    (Sliding Window) có overlap, cắt tại ranh giới câu/đoạn thay vì giữa chừng từ.
    """
    child_chunks: list[ChildChunk] = []
    global_chunk_idx = 0

    for sec in sections:
        text = sec.text
        if not text:
            continue

        # Section ngắn hơn max_chars: giữ nguyên làm 1 chunk duy nhất
        if len(text) <= max_chars:
            child_chunks.append(ChildChunk(
                chunk_id=f"{paper_id}_chk_{global_chunk_idx}",
                parent_section_id=sec.section_id,
                parent_section_name=sec.section_name,
                paper_id=paper_id,
                text=text,
                is_table=_is_table_chunk(text),
            ))
            global_chunk_idx += 1
            continue

        # Sliding Window: cắt tại ranh giới tự nhiên (câu/đoạn), không cắt giữa từ
        start = 0
        while start < len(text):
            end = _find_split_point(text, start + max_chars)

            # Đảm bảo không bị vòng lặp vô hạn khi không tìm được ranh giới
            if end <= start:
                end = start + max_chars

            chunk_str = text[start:end].strip()

            if chunk_str:
                child_chunks.append(ChildChunk(
                    chunk_id=f"{paper_id}_chk_{global_chunk_idx}",
                    parent_section_id=sec.section_id,
                    parent_section_name=sec.section_name,
                    paper_id=paper_id,
                    text=chunk_str,
                    is_table=_is_table_chunk(chunk_str),
                ))
                global_chunk_idx += 1

            # Bước tiến: lùi lại overlap_chars từ vị trí kết thúc
            next_start = end - overlap_chars
            if next_start <= start:
                next_start = end  # tránh vòng lặp vô hạn
            else:
                # Snap next_start tiến về ranh giới từ gần nhất (không bắt đầu giữa chừng 1 từ)
                while next_start < len(text) and not text[next_start].isspace():
                    next_start += 1
                # Bỏ qua khoảng trắng đầu
                while next_start < len(text) and text[next_start].isspace():
                    next_start += 1
            start = next_start

    return child_chunks


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE WRAPPER
# ──────────────────────────────────────────────────────────────────────────────

def process_paper_ingestion(
    pdf_path: str | Path,
    paper_id: str = "sample_paper",
) -> tuple[list[ParentSection], list[ChildChunk]]:
    """
    Chạy toàn bộ pipeline Ingestion:
        Parser -> Section Splitter -> Child Chunker
    """
    from app.ingestion.parser import parse_pdf_to_markdown

    md_text = parse_pdf_to_markdown(pdf_path)
    parent_sections = split_parent_sections(md_text)
    child_chunks = create_child_chunks(parent_sections, paper_id=paper_id)

    print("\n" + "=" * 60)
    print(f"[BAO CAO INGESTION] paper_id = {paper_id}")
    print("=" * 60)
    print(f"  - So Parent Sections : {len(parent_sections)}")
    print(f"  - So Child Chunks    : {len(child_chunks)}")
    print("\n  Danh sach Sections:")
    for s in parent_sections:
        table_flag = " [TABLE]" if any(c.is_table for c in child_chunks if c.parent_section_id == s.section_id) else ""
        print(f"   [{s.section_id}] {s.section_name} — {len(s.text)} ky tu{table_flag}")
    print("=" * 60)

    return parent_sections, child_chunks


# ──────────────────────────────────────────────────────────────────────────────
# CHUNK SERIALIZATION: lưu / load chunks xuống ổ D
# Để các module sau (BM25, Vector Store...) tái sử dụng mà không cần parse lại PDF
# ──────────────────────────────────────────────────────────────────────────────

def save_chunks_to_file(chunks: list[ChildChunk], paper_id: str) -> Path:
    """
    Lưu danh sách ChildChunk xuống file JSON trên ổ D.

    Args:
        chunks: Danh sách ChildChunk cần lưu.
        paper_id: ID bài báo, dùng làm tên file.

    Returns:
        Path: Đường dẫn tới file JSON vừa lưu.
    """
    import json

    chunks_dir = settings.data_dir / "chunks_cache"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    out_path = chunks_dir / f"{paper_id}_chunks.json"
    data = [
        {
            "chunk_id": c.chunk_id,
            "parent_section_id": c.parent_section_id,
            "parent_section_name": c.parent_section_name,
            "paper_id": c.paper_id,
            "text": c.text,
            "is_table": c.is_table,
        }
        for c in chunks
    ]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[SUCCESS] Luu {len(chunks)} chunks xuong: {out_path}", flush=True)
    return out_path


def load_chunks_from_file(paper_id: str) -> list[ChildChunk] | None:
    """
    Load danh sách ChildChunk từ file JSON trên ổ D.

    Args:
        paper_id: ID bài báo cần load.

    Returns:
        list[ChildChunk] nếu file tồn tại, None nếu chưa có.
    """
    import json

    out_path = settings.data_dir / "chunks_cache" / f"{paper_id}_chunks.json"
    if not out_path.exists():
        return None

    with open(out_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = [
        ChildChunk(
            chunk_id=item["chunk_id"],
            parent_section_id=item["parent_section_id"],
            parent_section_name=item["parent_section_name"],
            paper_id=item["paper_id"],
            text=item["text"],
            is_table=item["is_table"],
        )
        for item in data
    ]
    print(f"[SUCCESS] Load {len(chunks)} chunks tu cache: {out_path}", flush=True)
    return chunks


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT (chạy trực tiếp để test)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sample_pdfs = list(settings.data_dir.glob("*.pdf"))

    if not sample_pdfs:
        print(f"[NOTICE] Chua co file PDF nao trong: {settings.data_dir}")
        print("         Hay chep 1 file PDF bai bao vao thu muc nay de test.")
    else:
        PAPER_ID = "test_cortex_ode"

        sections, chunks = process_paper_ingestion(
            sample_pdfs[0],
            paper_id=PAPER_ID
        )

        if chunks:
            # Lưu chunks cache xuống ổ D để các module sau (BM25, Vector Store)
            # tái sử dụng mà không cần parse lại PDF
            save_chunks_to_file(chunks, paper_id=PAPER_ID)

            first = chunks[0]
            print(f"\n[XEM TRUOC CHILD CHUNK DAU TIEN]")
            print(f"  Chunk ID  : {first.chunk_id}")
            print(f"  Section   : {first.parent_section_name}")
            print(f"  Is Table  : {first.is_table}")
            print(f"  Do dai    : {len(first.text)} ky tu")
            print(f"  Noi dung  :\n{first.text[:400]}")
            print("  ...")

            # Kiem tra: dam bao khong co chunk nao bi cat giua tu
            mid = chunks[len(chunks) // 2]
            print(f"\n[KIEM TRA CHUNK GIUA (idx={len(chunks)//2})]")
            print(f"  Bat dau bang: '{mid.text[:60]}'")
            print(f"  Ket thuc bang: '...{mid.text[-60:]}'")
