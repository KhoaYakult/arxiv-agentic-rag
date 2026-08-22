"""
app/indexing/bm25_store.py
===========================
Module quản lý BM25 Sparse Index cho Hybrid Retrieval.
BM25 (Best Matching 25) tìm kiếm dựa trên tần suất từ khóa (TF-IDF cải tiến).
Ưu điểm: Bắt dính 100% từ khóa chính xác, số liệu, tên biến, thuật ngữ toán học.
"""

import pickle
import re
import sys
from pathlib import Path

# Tự động thêm thư mục gốc dự án vào sys.path khi chạy file trực tiếp
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.ingestion.chunker import ChildChunk

# Thư mục lưu BM25 Index trên ổ D
BM25_INDEX_DIR = settings.data_dir / "bm25_index"
BM25_INDEX_FILE = BM25_INDEX_DIR / "bm25.pkl"
BM25_CHUNKS_FILE = BM25_INDEX_DIR / "chunks_meta.pkl"


# ──────────────────────────────────────────────────────────────────────────────
# TOKENIZER: chuyên biệt cho bài báo khoa học
# ──────────────────────────────────────────────────────────────────────────────

# Ký tự phân cách (giữ lại chữ số, chữ cái, dấu gạch dưới và dấu chấm trong số)
_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+(?:[._\-][a-zA-Z0-9]+)*")


def tokenize(text: str) -> list[str]:
    """
    Tách chuỗi văn bản thành danh sách các token.
    Giữ nguyên các thuật ngữ khoa học (ODE, CortexODE, 0.163, MRI...)
    và loại bỏ các token quá ngắn (< 2 ký tự) ít mang thông tin.

    Args:
        text: Chuỗi văn bản đầu vào.

    Returns:
        list[str]: Danh sách token đã được chuẩn hóa chữ thường.
    """
    tokens = _TOKEN_PATTERN.findall(text.lower())
    # Lọc token quá ngắn (ký tự đơn như "a", "b", "i", "x")
    return [t for t in tokens if len(t) >= 2]


# ──────────────────────────────────────────────────────────────────────────────
# BM25 STORE MANAGER
# ──────────────────────────────────────────────────────────────────────────────

class BM25StoreManager:
    """
    Quản lý lưu trữ và truy xuất BM25 Sparse Index trên ổ D.
    Index được lưu dưới dạng file pickle để tái sử dụng mà không cần xây dựng lại.
    """

    def __init__(self):
        BM25_INDEX_DIR.mkdir(parents=True, exist_ok=True)

        self._bm25 = None          # BM25Okapi object (được load từ disk hoặc build mới)
        self._chunks_meta: list[dict] = []  # Metadata của từng chunk tương ứng với BM25 corpus

        # Tự động load index sẵn có nếu đã tồn tại trên ổ D
        if BM25_INDEX_FILE.exists() and BM25_CHUNKS_FILE.exists():
            self._load_index()

    def _load_index(self) -> None:
        """Load BM25 Index và chunks metadata từ file pickle trên ổ D."""
        print(f"[INFO] Tim thay BM25 Index tai: {BM25_INDEX_FILE}", flush=True)
        with open(BM25_INDEX_FILE, "rb") as f:
            self._bm25 = pickle.load(f)
        with open(BM25_CHUNKS_FILE, "rb") as f:
            self._chunks_meta = pickle.load(f)
        print(f"[SUCCESS] Load BM25 Index thanh cong! Corpus size: {len(self._chunks_meta)} docs.", flush=True)

    def _save_index(self) -> None:
        """Lưu BM25 Index và chunks metadata xuống file pickle trên ổ D."""
        with open(BM25_INDEX_FILE, "wb") as f:
            pickle.dump(self._bm25, f)
        with open(BM25_CHUNKS_FILE, "wb") as f:
            pickle.dump(self._chunks_meta, f)
        print(f"[SUCCESS] Luu BM25 Index xuong o D thanh cong!", flush=True)

    def build_index(self, chunks: list[ChildChunk]) -> None:
        """
        Xây dựng BM25 Index từ danh sách ChildChunk và lưu xuống ổ D.

        Quy trình:
          1. Tokenize nội dung từng chunk thành danh sách từ.
          2. Đưa toàn bộ corpus vào BM25Okapi để xây dựng thống kê TF-IDF.
          3. Lưu index và metadata xuống disk để tái sử dụng.

        Args:
            chunks: Danh sách ChildChunk từ pipeline Ingestion (Bước 2).
        """
        from rank_bm25 import BM25Okapi

        if not chunks:
            print("[NOTICE] Danh sach chunks rong, khong xay dung BM25 Index.", flush=True)
            return

        print(f"[INFO] Bat dau tokenize {len(chunks)} chunks...", flush=True)

        corpus_tokens = []
        self._chunks_meta = []

        for chunk in chunks:
            tokens = tokenize(chunk.text)
            corpus_tokens.append(tokens)
            self._chunks_meta.append({
                "chunk_id": chunk.chunk_id,
                "parent_section_id": chunk.parent_section_id,
                "parent_section_name": chunk.parent_section_name,
                "paper_id": chunk.paper_id,
                "is_table": chunk.is_table,
                "text": chunk.text,
            })

        print(f"[INFO] Xay dung BM25 Index tren {len(corpus_tokens)} documents...", flush=True)
        self._bm25 = BM25Okapi(corpus_tokens)

        # Lưu index xuống ổ D để tái sử dụng lần sau
        self._save_index()
        print(f"[SUCCESS] BM25 Index san sang! Path: {BM25_INDEX_DIR}", flush=True)

    def search(
        self, query: str, paper_id: str | None = None, top_k: int = 20
    ) -> list[dict]:
        """
        Tìm kiếm BM25 Sparse dựa trên từ khóa chính xác trong câu hỏi.

        Args:
            query: Câu hỏi hoặc từ khóa tìm kiếm.
            paper_id: Lọc kết quả theo ID bài báo cụ thể (nếu cần).
            top_k: Số lượng kết quả trả về.

        Returns:
            list[dict]: Danh sách kết quả kèm BM25 score và metadata,
                        sắp xếp từ liên quan nhất xuống ít nhất.
        """
        if self._bm25 is None:
            print("[ERROR] BM25 Index chua duoc xay dung. Hay goi build_index() truoc.", flush=True)
            return []

        # Tokenize câu hỏi theo cùng cách đã tokenize corpus
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        # Tính điểm BM25 cho tất cả documents trong corpus
        scores = self._bm25.get_scores(query_tokens)

        # Kết hợp score với metadata tương ứng
        scored_docs = [
            (float(scores[i]), self._chunks_meta[i])
            for i in range(len(self._chunks_meta))
        ]

        # Lọc theo paper_id nếu được chỉ định
        if paper_id:
            scored_docs = [
                (score, meta) for score, meta in scored_docs
                if meta["paper_id"] == paper_id
            ]

        # Lọc bỏ documents có score = 0 (hoàn toàn không khớp từ khóa)
        scored_docs = [(score, meta) for score, meta in scored_docs if score > 0]

        # Sắp xếp từ cao xuống thấp (BM25 score cao = liên quan hơn)
        scored_docs.sort(key=lambda x: x[0], reverse=True)

        # Lấy top_k kết quả và định dạng đầu ra
        results = []
        for rank, (score, meta) in enumerate(scored_docs[:top_k], 1):
            results.append({
                "bm25_rank": rank,
                "score": score,
                "chunk_id": meta["chunk_id"],
                "parent_section_id": meta["parent_section_id"],
                "parent_section_name": meta["parent_section_name"],
                "paper_id": meta["paper_id"],
                "is_table": meta["is_table"],
                "text": meta["text"],
            })

        return results

    def reset_index(self) -> None:
        """Xóa toàn bộ BM25 Index đã lưu trên ổ D."""
        if BM25_INDEX_FILE.exists():
            BM25_INDEX_FILE.unlink()
        if BM25_CHUNKS_FILE.exists():
            BM25_CHUNKS_FILE.unlink()

        self._bm25 = None
        self._chunks_meta = []
        print(f"[INFO] Da xoa BM25 Index tai: {BM25_INDEX_DIR}", flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT (chạy trực tiếp để test)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from app.ingestion.chunker import (
        load_chunks_from_file,
        process_paper_ingestion,
        save_chunks_to_file,
    )

    PAPER_ID = "test_cortex_ode"

    print("[INFO] Bat dau chay test Buoc 3.2 (BM25 Sparse Index)...", flush=True)

    # 1. Load chunks từ cache JSON nếu đã có, nếu chưa mới parse PDF
    chunks = load_chunks_from_file(PAPER_ID)

    if chunks is None:
        print("[INFO] Chua co cache. Chay Ingestion Pipeline de tao cache...", flush=True)
        sample_pdfs = list(settings.data_dir.glob("*.pdf"))
        if not sample_pdfs:
            print(f"[NOTICE] Chua co file PDF nao trong: {settings.data_dir}", flush=True)
            raise SystemExit(1)

        sections, chunks = process_paper_ingestion(sample_pdfs[0], paper_id=PAPER_ID)
        save_chunks_to_file(chunks, paper_id=PAPER_ID)
        print(f"[SUCCESS] Da luu cache. Tu lan sau se load truc tiep, khong can parse PDF.", flush=True)
    else:
        print(f"[INFO] Su dung chunks tu cache (khong parse lai PDF).", flush=True)

    # 2. Xây dựng BM25 Index
    print(f"\n[INFO] Buoc 2: Xay dung BM25 Index tu {len(chunks)} chunks...", flush=True)
    bm25_manager = BM25StoreManager()
    bm25_manager.reset_index()
    bm25_manager.build_index(chunks)

    # 3. Test 1 - Câu hỏi ngữ nghĩa (để so sánh với Dense Vector)
    query_semantic = "What is Neural ODE and how does CortexODE perform surface reconstruction?"
    print(f"\n[TEST 1 - SEMANTIC] Query: '{query_semantic}'", flush=True)
    results_semantic = bm25_manager.search(query=query_semantic, paper_id=PAPER_ID, top_k=3)

    print("=" * 60, flush=True)
    print("[KET QUA BM25 - TOP 3 (Semantic Query)]", flush=True)
    print("=" * 60, flush=True)
    for r in results_semantic:
        print(f"  Rank {r['bm25_rank']} | BM25 Score: {r['score']:.4f} | Section: {r['parent_section_name']}", flush=True)
        print(f"  Chunk ID: {r['chunk_id']} | Is Table: {r['is_table']}", flush=True)
        print(f"  Noi dung: {r['text'][:200]}...", flush=True)
        print("-" * 60, flush=True)

    # 4. Test 2 - Từ khóa chính xác (điểm mạnh độc quyền của BM25)
    query_exact = "Dice coefficient FreeSurfer 0.939"
    print(f"\n[TEST 2 - EXACT KEYWORD] Query: '{query_exact}'", flush=True)
    results_exact = bm25_manager.search(query=query_exact, paper_id=PAPER_ID, top_k=3)

    print("=" * 60, flush=True)
    print("[KET QUA BM25 - TOP 3 (Exact Keyword Query)]", flush=True)
    print("=" * 60, flush=True)
    if results_exact:
        for r in results_exact:
            print(f"  Rank {r['bm25_rank']} | BM25 Score: {r['score']:.4f} | Section: {r['parent_section_name']}", flush=True)
            print(f"  Chunk ID: {r['chunk_id']} | Is Table: {r['is_table']}", flush=True)
            print(f"  Noi dung: {r['text'][:200]}...", flush=True)
            print("-" * 60, flush=True)
    else:
        print("  [NOTICE] Khong tim thay ket qua phu hop.", flush=True)

