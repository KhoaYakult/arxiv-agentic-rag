"""
app/indexing/reranker.py
=========================
Module Re-ranking (Xếp hạng lại) giai đoạn 2 của Hybrid Retrieval.
Nhận vào Top-20 kết quả từ Hybrid Search, trả về Top-5 chính xác nhất.

Hỗ trợ 2 chế độ tự động:
  - Cohere Rerank API  : Nếu COHERE_API_KEY được cấu hình trong .env
  - Local CrossEncoder : Fallback offline dùng cross-encoder/ms-marco-MiniLM-L-6-v2
                         (~85MB, tối ưu chạy trên CPU i3)
"""

import sys
from pathlib import Path

# Tự động thêm thư mục gốc dự án vào sys.path khi chạy file trực tiếp
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import settings


# ──────────────────────────────────────────────────────────────────────────────
# RERANKER MANAGER
# ──────────────────────────────────────────────────────────────────────────────

class RerankerManager:
    """
    Quản lý việc Re-ranking kết quả tìm kiếm theo 2 chế độ:
      - "cohere" : Dùng Cohere Rerank API (yêu cầu COHERE_API_KEY)
      - "local"  : Dùng CrossEncoder offline (ms-marco-MiniLM-L-6-v2)
    Tự động lựa chọn chế độ dựa trên cấu hình trong .env.
    """

    # Tên model CrossEncoder nhẹ nhất, tối ưu cho CPU
    LOCAL_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(self):
        self._cross_encoder = None  # Lazy load: chỉ khởi tạo khi cần dùng lần đầu

        if settings.cohere_api_key:
            self.mode = "cohere"
            print("[INFO] Reranker mode: Cohere API", flush=True)
        else:
            self.mode = "local"
            print(f"[INFO] Reranker mode: Local CrossEncoder ({self.LOCAL_CROSS_ENCODER_MODEL})", flush=True)

    def _get_cross_encoder(self):
        """
        Lazy initialization: chỉ load CrossEncoder khi hàm rerank được gọi lần đầu.
        Tránh load model ngay khi import module (gây crash module-level trên Windows).
        """
        if self._cross_encoder is None:
            from sentence_transformers import CrossEncoder
            print(f"[INFO] Khoi tao CrossEncoder: {self.LOCAL_CROSS_ENCODER_MODEL}...", flush=True)
            self._cross_encoder = CrossEncoder(
                self.LOCAL_CROSS_ENCODER_MODEL,
                max_length=512,      # Giới hạn token để tránh tràn RAM trên CPU
            )
            print("[SUCCESS] CrossEncoder san sang.", flush=True)
        return self._cross_encoder

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """
        Re-rank danh sách candidates theo mức độ liên quan với câu hỏi.

        Args:
            query: Câu hỏi gốc của người dùng.
            candidates: Danh sách kết quả từ Hybrid Search (list[dict] có key "text").
                        Mỗi item phải có ít nhất các key: text, chunk_id, paper_id,
                        parent_section_name, is_table.
            top_k: Số lượng kết quả tốt nhất cần trả về sau khi rerank.

        Returns:
            list[dict]: Danh sách kết quả đã được sắp xếp lại, kèm thêm
                        "rerank_rank" và "rerank_score".
        """
        if not candidates:
            print("[NOTICE] Danh sach candidates rong, khong co gi de rerank.", flush=True)
            return []

        if self.mode == "cohere":
            return self._rerank_cohere(query, candidates, top_k)
        else:
            return self._rerank_local(query, candidates, top_k)

    def _rerank_local(
        self, query: str, candidates: list[dict], top_k: int
    ) -> list[dict]:
        """
        Re-rank offline dùng CrossEncoder: đưa từng cặp (query, document) vào model
        để dự đoán điểm liên quan. Chính xác hơn Bi-Encoder nhưng chậm hơn.
        """
        model = self._get_cross_encoder()

        # Tạo danh sách cặp [query, chunk_text] để CrossEncoder chấm điểm
        # Giới hạn độ dài chunk text ở 512 ký tự để tránh vượt max_length
        pairs = [[query, c["text"][:512]] for c in candidates]

        print(f"[INFO] CrossEncoder dang cham diem {len(pairs)} candidates...", flush=True)
        scores = model.predict(pairs, show_progress_bar=False)

        # Gắn rerank score vào từng candidate
        for i, score in enumerate(scores):
            candidates[i]["rerank_score"] = float(score)

        # Sắp xếp theo rerank_score giảm dần (cao hơn = liên quan hơn)
        candidates.sort(key=lambda x: x["rerank_score"], reverse=True)

        # Gán lại thứ hạng sau khi rerank và trả về top_k
        results = []
        for rank, item in enumerate(candidates[:top_k], 1):
            item["rerank_rank"] = rank
            results.append(item)

        return results

    def _rerank_cohere(
        self, query: str, candidates: list[dict], top_k: int
    ) -> list[dict]:
        """
        Re-rank qua Cohere Rerank API. Yêu cầu kết nối internet và COHERE_API_KEY.
        Hỗ trợ model mới nhất: rerank-english-v3.0
        """
        try:
            import cohere
        except ImportError:
            print("[ERROR] Thu vien 'cohere' chua duoc cai dat. Chay: pip install cohere", flush=True)
            print("[INFO] Chuyen sang Local CrossEncoder...", flush=True)
            return self._rerank_local(query, candidates, top_k)

        print(f"[INFO] Cohere Rerank API dang cham diem {len(candidates)} candidates...", flush=True)
        client = cohere.ClientV2(api_key=settings.cohere_api_key)

        documents = [c["text"][:2048] for c in candidates]  # Cohere giới hạn độ dài text

        response = client.rerank(
            model="rerank-english-v3.0",
            query=query,
            documents=documents,
            top_n=top_k,
        )

        results = []
        for rank, result in enumerate(response.results, 1):
            item = candidates[result.index].copy()
            item["rerank_rank"] = rank
            item["rerank_score"] = float(result.relevance_score)
            results.append(item)

        return results


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT (chạy trực tiếp để test)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from app.ingestion.chunker import load_chunks_from_file
    from app.indexing.bm25_store import BM25StoreManager

    PAPER_ID = "test_cortex_ode"

    print("[INFO] Bat dau chay test Buoc 3.3 (Reranker)...", flush=True)

    # 1. Load chunks từ cache
    chunks = load_chunks_from_file(PAPER_ID)
    if chunks is None:
        print("[ERROR] Chua co chunks cache. Chay chunker.py truoc.", flush=True)
        raise SystemExit(1)

    # 2. Dùng BM25 để lấy Top-10 candidates (giả lập output của Hybrid Search)
    print(f"\n[INFO] Buoc 1: Lay Top-10 candidates bang BM25...", flush=True)
    bm25 = BM25StoreManager()
    if bm25._bm25 is None:
        print("[INFO] Chua co BM25 Index, dang xay dung...", flush=True)
        bm25.build_index(chunks)

    test_query = "What is the Dice coefficient of CortexODE compared to FreeSurfer?"
    candidates = bm25.search(query=test_query, paper_id=PAPER_ID, top_k=10)

    print(f"\n[TRUOC RERANK] Top-5 tu BM25:", flush=True)
    print("=" * 60, flush=True)
    for c in candidates[:5]:
        print(f"  BM25 Rank {c['bm25_rank']} | Score: {c['score']:.4f} | Section: {c['parent_section_name']}", flush=True)
        print(f"  Chunk: {c['chunk_id']} | Is Table: {c['is_table']}", flush=True)
        print("-" * 60, flush=True)

    # 3. Áp dụng Reranker
    print(f"\n[INFO] Buoc 2: Ap dung Reranker...", flush=True)
    reranker = RerankerManager()
    reranked = reranker.rerank(query=test_query, candidates=candidates, top_k=5)

    print(f"\n[SAU RERANK] Top-5 sau khi Reranker sap xep lai:", flush=True)
    print("=" * 60, flush=True)
    for r in reranked:
        print(f"  Rerank #{r['rerank_rank']} | Score: {r['rerank_score']:.4f} | Section: {r['parent_section_name']}", flush=True)
        print(f"  Chunk: {r['chunk_id']} | Is Table: {r['is_table']}", flush=True)
        print(f"  Noi dung: {r['text'][:200]}...", flush=True)
        print("-" * 60, flush=True)

    # 4. Phân tích: Reranker đã đổi thứ hạng những chunk nào?
    print(f"\n[PHAN TICH THAY DOI THU HANG]", flush=True)
    bm25_rank_map = {c["chunk_id"]: c["bm25_rank"] for c in candidates}
    for r in reranked:
        old_rank = bm25_rank_map.get(r["chunk_id"], "?")
        arrow = "  " if old_rank == r["rerank_rank"] else "->"
        print(f"  BM25 #{old_rank:>2} {arrow} Rerank #{r['rerank_rank']} | {r['parent_section_name']} ({r['chunk_id']})", flush=True)
