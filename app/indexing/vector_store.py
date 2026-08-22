"""
app/indexing/vector_store.py
=============================
Module quản lý Cơ sở dữ liệu Vector (ChromaDB) lưu trữ hoàn toàn trên Ổ D.
Sử dụng mô hình Embedding siêu nhẹ (all-MiniLM-L6-v2) tối ưu chạy trên CPU.
"""

import sys
from pathlib import Path

# Tự động thêm thư mục gốc dự án vào sys.path khi chạy file trực tiếp
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.ingestion.chunker import ChildChunk

# Số lượng chunk xử lý trong mỗi đợt gọi HF API
# (Tránh gọi quá nhiều request cùng lúc, gây rate-limit)
EMBED_BATCH_SIZE = 32

# Tên model embedding đầy đủ trên HuggingFace Hub
HF_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


# ──────────────────────────────────────────────────────────────────────────────
# HUGGINGFACE API EMBEDDINGS (Thay thế Local Model)
# Ưu điểm: 0MB RAM, chạy được cả khi deploy lên Streamlit Cloud / Railway.
# Nhược điểm: Cần mạng internet, phụ thuộc rate-limit của HuggingFace.
# ──────────────────────────────────────────────────────────────────────────────
class HuggingFaceAPIEmbeddings:
    """
    Gọi HuggingFace Inference API để tính Vector Embedding.
    Không nạp model vào RAM máy → giải quyết lỗi paging file trên Windows.
    Hoạt động giống hệt LocalFastEmbeddings về interface (embed_documents, embed_query).
    """

    def __init__(self, model_name: str = HF_EMBED_MODEL, api_token: str = ""):
        from huggingface_hub import InferenceClient

        self.model_name = model_name
        self.client = InferenceClient(token=api_token or None)
        print(f"[INFO] HuggingFace Inference API Embeddings san sang.", flush=True)
        print(f"[INFO] Model: {model_name}", flush=True)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Tính Embedding cho danh sách văn bản theo batch.
        Gọi HF Inference API, không ngốn RAM máy tính.
        """
        import numpy as np
        all_embeddings = []
        total = len(texts)
        for i in range(0, total, EMBED_BATCH_SIZE):
            batch = texts[i: i + EMBED_BATCH_SIZE]
            # feature_extraction trả về numpy array shape (batch_size, embedding_dim)
            result = self.client.feature_extraction(batch, model=self.model_name)
            arr = np.array(result)
            # Đảm bảo shape là (batch_size, dim) dù HF trả về 2D hay 3D
            if arr.ndim == 3:
                arr = arr[:, 0, :]  # mean pooling nếu có dimension thừa
            all_embeddings.extend(arr.tolist())
            done = min(i + EMBED_BATCH_SIZE, total)
            print(f"[INFO]   Embed API: {done}/{total} texts...", flush=True)
        return all_embeddings

    def embed_query(self, text: str) -> list[float]:
        """
        Tính Embedding cho 1 câu hỏi tìm kiếm (Query).
        """
        import numpy as np
        result = self.client.feature_extraction(text, model=self.model_name)
        arr = np.array(result)
        # Nếu HF trả về shape (1, dim) hoặc (dim,) thì flatten về 1D
        return arr.flatten().tolist()


#-----------------------------
# Vector Store Manager
#-----------------------------

class VectorStoreManager:
    """Quản lý lưu trữ và truy xuất Dense Vector sử dụng ChromaDB."""

    def __init__(self):
        self.db_dir = str(settings.db_dir)
        self.collection_name = "arxiv_papers"

        # Dùng HuggingFace Inference API thay vì local model
        # → 0MB RAM, hoạt động trên cả máy yếu lẫn Streamlit Cloud khi deploy
        self.embeddings = HuggingFaceAPIEmbeddings(
            model_name=HF_EMBED_MODEL,
            api_token=settings.hf_token,
        )

        import chromadb
        from langchain_chroma import Chroma

        self._chromadb = chromadb
        self._Chroma = Chroma

        print(f"[INFO] Ket noi toi ChromaDB tai: {self.db_dir}", flush=True)
        self.vector_db = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.db_dir,
        )

        # ChromaDB native client để thao tác collection trực tiếp
        self._chroma_client = chromadb.PersistentClient(path=self.db_dir)

    def _get_collection_count(self) -> int:
        """Trả về số lượng vector hiện có trong collection qua ChromaDB client chuẩn."""
        try:
            col = self._chroma_client.get_collection(self.collection_name)
            return col.count()
        except Exception:
            return 0

    def add_child_chunks(self, chunks: list[ChildChunk]) -> int:
        """
        Đóng gói danh sách ChildChunk thành Document và nạp vào ChromaDB
        theo từng batch nhỏ (32 chunks/batch) để tránh tràn RAM.

        Args:
            chunks: Danh sách các ChildChunk thu được từ Bước 2.

        Returns:
            int: Số lượng chunks đã được lưu thành công.
        """
        from langchain_core.documents import Document

        if not chunks:
            print("[NOTICE] Danh sach chunks rong.", flush=True)
            return 0

        documents = []
        ids = []
        for chunk in chunks:
            documents.append(Document(
                page_content=chunk.text,
                metadata={
                    "chunk_id": chunk.chunk_id,
                    "parent_section_id": chunk.parent_section_id,
                    "parent_section_name": chunk.parent_section_name,
                    "paper_id": chunk.paper_id,
                    "is_table": chunk.is_table,
                },
            ))
            ids.append(chunk.chunk_id)

        # Nạp theo batch, in tiến độ từng batch để terminal không trông như bị treo
        total = len(documents)
        for i in range(0, total, EMBED_BATCH_SIZE):
            batch_docs = documents[i: i + EMBED_BATCH_SIZE]
            batch_ids = ids[i: i + EMBED_BATCH_SIZE]
            self.vector_db.add_documents(documents=batch_docs, ids=batch_ids)
            done = min(i + EMBED_BATCH_SIZE, total)
            print(f"[INFO]   Nap Vector: {done}/{total} chunks...", flush=True)

        count = self._get_collection_count()
        print(f"[SUCCESS] Luu xong! Tong so vector trong DB: {count}", flush=True)
        return total

    def similarity_search(
        self, query: str, paper_id: str | None = None, top_k: int = 20
    ) -> list[dict]:
        """
        Tìm kiếm Dense Vector tương đồng dựa trên câu hỏi (Cosine Similarity).

        Args:
            query: Câu hỏi hoặc từ khóa tìm kiếm.
            paper_id: Lọc theo ID bài báo cụ thể.
            top_k: Số lượng kết quả trả về (mặc định 20 để phục vụ Re-ranking).

        Returns:
            list[dict]: Danh sách kết quả kèm điểm số và metadata.
        """
        search_filter = {"paper_id": paper_id} if paper_id else None

        results = self.vector_db.similarity_search_with_score(
            query=query, k=top_k, filter=search_filter
        )

        return [
            {
                "dense_rank": rank,
                "score": float(score),
                "chunk_id": doc.metadata.get("chunk_id", ""),
                "parent_section_id": doc.metadata.get("parent_section_id", ""),
                "parent_section_name": doc.metadata.get("parent_section_name", ""),
                "paper_id": doc.metadata.get("paper_id", ""),
                "is_table": doc.metadata.get("is_table", False),
                "text": doc.page_content,
            }
            for rank, (doc, score) in enumerate(results, 1)
        ]

    def reset_db(self):
        """
        Làm sạch DB bằng cách xóa và tạo lại collection.
        Đảm bảo sạch hoàn toàn, không phụ thuộc vào filter where={}.
        """
        from langchain_chroma import Chroma

        try:
            self._chroma_client.delete_collection(self.collection_name)
            print(f"[INFO] Da xoa collection cu: '{self.collection_name}'.", flush=True)
        except Exception:
            pass  # Collection chưa tồn tại, bỏ qua

        self._chroma_client.create_collection(self.collection_name)

        # Tạo lại vector_db với collection mới sạch
        self.vector_db = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.db_dir,
        )
        print(f"[INFO] Da tao moi collection: '{self.collection_name}'.", flush=True)


if __name__ == "__main__":
    from app.ingestion.chunker import load_chunks_from_file, process_paper_ingestion

    PAPER_ID = "test_cortex_ode"
    sample_pdfs = list(settings.data_dir.glob("*.pdf"))

    if not sample_pdfs:
        print(f"[NOTICE] Chua co file PDF nao trong: {settings.data_dir}", flush=True)
        print("         Hay chep 1 file PDF bai bao vao thu muc nay de test.", flush=True)
    else:
        print("[INFO] Bat dau chay test Buoc 3.1 (ChromaDB Vector Store)...", flush=True)

        # 1. Uu tien load tu chunks_cache de tranh parse lai PDF
        #    (parse PDF can ONNX Runtime ton nhieu RAM tren may yeu)
        print("[INFO] Buoc 1: Thu load chunks tu cache...", flush=True)
        chunks = load_chunks_from_file(PAPER_ID)

        if chunks is None:
            print("[INFO] Chua co cache. Chay Ingestion Pipeline (parse PDF)...", flush=True)
            _, chunks = process_paper_ingestion(sample_pdfs[0], paper_id=PAPER_ID)

        # 2. Khởi tạo VectorStoreManager & Xóa DB cũ
        print("\n[INFO] Buoc 2: Khoi tao VectorStoreManager...", flush=True)
        vm = VectorStoreManager()
        vm.reset_db()

        # 3. Nạp chunks vào ChromaDB (theo batch, có hiển thị tiến độ)
        print(f"\n[INFO] Buoc 3: Bat dau nap {len(chunks)} chunks vao ChromaDB...", flush=True)
        vm.add_child_chunks(chunks)

        # 4. Tìm kiếm thử nghiệm
        test_query = input("(Thử nghiệm) Hãy nhập câu hỏi của bạn: ")
        print(f"\n[INFO] Buoc 4: Tim kiem cho cau hoi: '{test_query}'", flush=True)

        results = vm.similarity_search(query=test_query, paper_id="test_cortex_ode", top_k=3)

        print("\n" + "=" * 60, flush=True)
        print("[KET QUA TIM KIEM DENSE VECTOR - TOP 3]", flush=True)
        print("=" * 60, flush=True)
        for r in results:
            print(f"  Rank {r['dense_rank']} | Score: {r['score']:.4f} | Section: {r['parent_section_name']}", flush=True)
            print(f"  Chunk ID: {r['chunk_id']} | Is Table: {r['is_table']}", flush=True)
            print(f"  Noi dung: {r['text'][:250]}...", flush=True)
            print("-" * 60, flush=True)
