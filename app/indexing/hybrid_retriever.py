"""
app/indexing/hybrid_retriever.py
=================================
Module Orchestrator cua toan bo Buoc 3.
Ket hop Dense Vector + BM25 Sparse -> RRF Fusion -> Reranker
thanh 1 pipeline retrieve() duy nhat de cac module sau goi don gian.

Luong du lieu:
    [Query]
      │
      ├─► [Dense Vector Search]  → Top-20 (ket qua theo ngu nghia)
      │
      ├─► [BM25 Sparse Search]   → Top-20 (ket qua theo tu khoa chinh xac)
      │
      ├─► [RRF Fusion]           → Gop 2 danh sach bang Reciprocal Rank Fusion
      │                            → Top-20 Ung vien tot nhat
      │
      └─► [Reranker]             → Cham diem chi tiet tung cap (query, doc)
                                   → Top-5 Ket qua chinh xac nhat
"""

import sys
from pathlib import Path

# Tu dong them thu muc goc du an vao sys.path khi chay file truc tiep
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.ingestion.chunker import ChildChunk

# So luong ket qua lay tu moi retriever o giai doan 1 (First-Stage)
FIRST_STAGE_K = 20


# ──────────────────────────────────────────────────────────────────────────────
# RRF FUSION
# ──────────────────────────────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    dense_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """
    Reciprocal Rank Fusion (RRF): Gop 2 danh sach xep hang tu Dense va BM25
    thanh 1 danh sach thong nhat bang cong thuc:

        RRF_score(doc) = sum over each list: 1 / (k + rank_in_that_list)

    k = 60 la gia tri mac dinh tu bai bao goc cua RRF (Cormack et al., 2009).
    Gia tri nay giam thieu anh huong cua nhung vi tri hang dau qua cao.

    Args:
        dense_results: Ket qua tu Dense Vector Search (co key 'chunk_id', 'dense_rank').
        bm25_results:  Ket qua tu BM25 Search (co key 'chunk_id', 'bm25_rank').
        k: Hang so lam mo RRF (mac dinh 60).

    Returns:
        list[dict]: Danh sach da duoc gop va sap xep theo RRF score giam dan,
                    moi item co them 'rrf_score' va 'rrf_rank'.
    """
    rrf_scores: dict[str, float] = {}
    chunk_data: dict[str, dict] = {}

    # Cong diem RRF tu Dense results
    for item in dense_results:
        cid = item["chunk_id"]
        rank = item["dense_rank"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank)
        chunk_data[cid] = item.copy()

    # Cong diem RRF tu BM25 results
    for item in bm25_results:
        cid = item["chunk_id"]
        rank = item["bm25_rank"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank)
        # Giu lai data cua chunk neu chua co (Dense co the da co roi)
        if cid not in chunk_data:
            chunk_data[cid] = item.copy()

    # Sap xep theo RRF score giam dan
    sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)

    results = []
    for rank, cid in enumerate(sorted_ids, 1):
        item = chunk_data[cid]
        item["rrf_score"] = round(rrf_scores[cid], 6)
        item["rrf_rank"] = rank
        results.append(item)

    return results


# ──────────────────────────────────────────────────────────────────────────────
# HYBRID RETRIEVER
# ──────────────────────────────────────────────────────────────────────────────

class HybridRetriever:
    """
    Nhat truong ket hop toan bo pipeline Buoc 3:
      Dense Vector Search + BM25 Sparse Search + RRF Fusion + Reranker

    Cach su dung:
        retriever = HybridRetriever()
        results = retriever.retrieve(query="...", paper_id="my_paper", top_k=5)
    """

    def __init__(self):
        # Lazy init: cac thanh phan nang chi duoc khoi tao khi lan dau su dung
        self._vector_store = None
        self._bm25_store = None
        self._reranker = None
        print("[INFO] HybridRetriever san sang.", flush=True)

    def _get_vector_store(self):
        if self._vector_store is None:
            from app.indexing.vector_store import VectorStoreManager
            print("[INFO] Khoi tao VectorStoreManager...", flush=True)
            self._vector_store = VectorStoreManager()
        return self._vector_store

    def _get_bm25_store(self):
        if self._bm25_store is None:
            from app.indexing.bm25_store import BM25StoreManager
            print("[INFO] Khoi tao BM25StoreManager...", flush=True)
            self._bm25_store = BM25StoreManager()
        return self._bm25_store

    def _get_reranker(self):
        if self._reranker is None:
            from app.indexing.reranker import RerankerManager
            print("[INFO] Khoi tao RerankerManager...", flush=True)
            self._reranker = RerankerManager()
        return self._reranker

    def retrieve(
        self,
        query: str,
        paper_id: str | None = None,
        top_k: int = 5,
        first_stage_k: int = FIRST_STAGE_K,
        verbose: bool = False,
    ) -> list[dict]:
        """
        Chay toan bo pipeline Hybrid Retrieval va tra ve top_k ket qua chinh xac nhat.

        Args:
            query:         Cau hoi cua nguoi dung.
            paper_id:      Loc theo ID bai bao cu the (None = tim tren toan bo DB).
            top_k:         So ket qua cuoi cung can tra ve (mac dinh 5).
            first_stage_k: So ung vien lay tu moi retriever o giai doan 1 (mac dinh 20).
            verbose:       In ra ket qua trung gian (Dense, BM25, RRF) de debug.

        Returns:
            list[dict]: Danh sach ket qua da duoc rerank, sap xep tu lien quan nhat
                        xuong it nhat, moi item co day du metadata.
        """
        # ── GIAI DOAN 1A: Dense Vector Search ──
        vector_store = self._get_vector_store()
        dense_results = vector_store.similarity_search(
            query=query, paper_id=paper_id, top_k=first_stage_k
        )

        if verbose:
            print(f"\n  [Dense] Tim duoc {len(dense_results)} ket qua.", flush=True)
            for r in dense_results[:3]:
                print(f"    Rank {r['dense_rank']} | Score: {r['score']:.4f} | {r['parent_section_name']}", flush=True)

        # ── GIAI DOAN 1B: BM25 Sparse Search ──
        bm25_store = self._get_bm25_store()
        bm25_results = bm25_store.search(
            query=query, paper_id=paper_id, top_k=first_stage_k
        )

        if verbose:
            print(f"\n  [BM25] Tim duoc {len(bm25_results)} ket qua.", flush=True)
            for r in bm25_results[:3]:
                print(f"    Rank {r['bm25_rank']} | Score: {r['score']:.4f} | {r['parent_section_name']}", flush=True)

        # ── GIAI DOAN 1C: RRF Fusion ──
        fused = reciprocal_rank_fusion(dense_results, bm25_results)
        candidates = fused[:first_stage_k]  # Giu lai top first_stage_k sau khi fusion

        if verbose:
            print(f"\n  [RRF] Sau fusion: {len(fused)} unique chunks. Top-5:", flush=True)
            for r in candidates[:5]:
                src_dense = any(d["chunk_id"] == r["chunk_id"] for d in dense_results)
                src_bm25  = any(b["chunk_id"] == r["chunk_id"] for b in bm25_results)
                src = ("Dense+BM25" if src_dense and src_bm25
                       else "Dense" if src_dense else "BM25")
                print(f"    RRF #{r['rrf_rank']} | Score: {r['rrf_score']:.6f} | [{src}] {r['parent_section_name']}", flush=True)

        # ── GIAI DOAN 2: Reranker ──
        reranker = self._get_reranker()
        final_results = reranker.rerank(query=query, candidates=candidates, top_k=top_k)

        return final_results


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT (chay truc tiep de test)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from app.ingestion.chunker import load_chunks_from_file, save_chunks_to_file
    from app.ingestion.chunker import process_paper_ingestion

    PAPER_ID = "test_cortex_ode"

    print("[INFO] Bat dau chay test Buoc 3.4 (HybridRetriever)...", flush=True)

    # ── Kiem tra va khoi tao du lieu neu chua co ──
    print("\n[SETUP] Kiem tra du lieu can thiet...", flush=True)

    # 1. Lay chunks tu cache
    chunks = load_chunks_from_file(PAPER_ID)
    if chunks is None:
        print("[INFO] Chua co cache. Chay Ingestion Pipeline...", flush=True)
        sample_pdfs = list(settings.data_dir.glob("*.pdf"))
        if not sample_pdfs:
            print(f"[ERROR] Khong co file PDF nao trong: {settings.data_dir}", flush=True)
            raise SystemExit(1)
        sections, chunks = process_paper_ingestion(sample_pdfs[0], paper_id=PAPER_ID)
        save_chunks_to_file(chunks, paper_id=PAPER_ID)

    # ── Khoi tao HybridRetriever TRUOC (tranh load model 2 lan) ──
    # Sau do tai su dung cac instance ben trong de setup du lieu
    print("\n[INFO] Khoi tao HybridRetriever...", flush=True)
    retriever = HybridRetriever()

    # 2. Kiem tra ChromaDB qua instance ben trong HybridRetriever
    vm = retriever._get_vector_store()
    count = vm._get_collection_count()
    if count == 0:
        print("[INFO] ChromaDB trong. Nap lai chunks...", flush=True)
        vm.add_child_chunks(chunks)
    else:
        print(f"[OK] ChromaDB co san {count} vectors.", flush=True)

    # 3. Kiem tra BM25 Index qua instance ben trong HybridRetriever
    bm25 = retriever._get_bm25_store()
    if bm25._bm25 is None:
        print("[INFO] BM25 Index chua co. Dang build...", flush=True)
        bm25.build_index(chunks)
    else:
        print(f"[OK] BM25 Index co san ({len(bm25._chunks_meta)} docs).", flush=True)

    # ── Test 1: Cau hoi ngu nghia ──
    print("\n" + "=" * 60, flush=True)
    query1 = "How does CortexODE use neural ODE to reconstruct cortical surface?"
    print(f"[QUERY 1 - Semantic]: '{query1}'", flush=True)
    print("[INFO] Dense + BM25 + RRF + Rerank...", flush=True)

    results1 = retriever.retrieve(
        query=query1, paper_id=PAPER_ID, top_k=5, verbose=True,
    )

    print(f"\n{'=' * 60}", flush=True)
    print("[KET QUA FINAL - TOP 5] (Query 1)", flush=True)
    print("=" * 60, flush=True)
    for r in results1:
        print(f"  #{r['rerank_rank']} | Cohere: {r['rerank_score']:.4f} | RRF: {r.get('rrf_score', 0):.6f}", flush=True)
        print(f"     Section : {r['parent_section_name']}", flush=True)
        print(f"     Chunk   : {r['chunk_id']} | Table: {r['is_table']}", flush=True)
        print(f"     Noi dung: {r['text'][:180]}...", flush=True)
        print(f"  {'-' * 58}", flush=True)

    # ── Test 2: Cau hoi tu khoa chinh xac ──
    print("\n" + "=" * 60, flush=True)
    query2 = "Dice coefficient FreeSurfer baseline comparison table"
    print(f"[QUERY 2 - Exact Keyword]: '{query2}'", flush=True)
    print("[INFO] Dense + BM25 + RRF + Rerank...", flush=True)

    results2 = retriever.retrieve(
        query=query2, paper_id=PAPER_ID, top_k=5, verbose=True,
    )

    print(f"\n{'=' * 60}", flush=True)
    print("[KET QUA FINAL - TOP 5] (Query 2)", flush=True)
    print("=" * 60, flush=True)
    for r in results2:
        print(f"  #{r['rerank_rank']} | Cohere: {r['rerank_score']:.4f} | RRF: {r.get('rrf_score', 0):.6f}", flush=True)
        print(f"     Section : {r['parent_section_name']}", flush=True)
        print(f"     Chunk   : {r['chunk_id']} | Table: {r['is_table']}", flush=True)
        print(f"     Noi dung: {r['text'][:180]}...", flush=True)
        print(f"  {'-' * 58}", flush=True)

    print("\n[SUCCESS] Buoc 3.4 HybridRetriever test hoan tat!", flush=True)
