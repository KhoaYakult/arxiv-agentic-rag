"""
Test ham reciprocal_rank_fusion() trong app/indexing/hybrid_retriever.py.
Ham nay thuan (khong goi ChromaDB/BM25/network) nen test truc tiep voi
danh sach dict gia lap ket qua tu dense/sparse retriever.
"""

from app.indexing.hybrid_retriever import reciprocal_rank_fusion


def _dense(chunk_id: str, rank: int) -> dict:
    return {"chunk_id": chunk_id, "dense_rank": rank, "text": f"dense-{chunk_id}"}


def _bm25(chunk_id: str, rank: int) -> dict:
    return {"chunk_id": chunk_id, "bm25_rank": rank, "text": f"bm25-{chunk_id}"}


class TestReciprocalRankFusion:
    def test_item_in_both_lists_outranks_item_in_one_list(self):
        dense = [_dense("a", 1), _dense("b", 2)]
        bm25 = [_bm25("a", 2), _bm25("c", 1)]
        result = reciprocal_rank_fusion(dense, bm25, k=60)

        ids_in_order = [r["chunk_id"] for r in result]
        # "a" xuat hien ca 2 danh sach -> RRF score cao nhat -> dung dau
        assert ids_in_order[0] == "a"

    def test_rrf_score_matches_formula(self):
        dense = [_dense("a", 1)]
        bm25 = [_bm25("a", 1)]
        result = reciprocal_rank_fusion(dense, bm25, k=60)

        expected = round(1.0 / (60 + 1) + 1.0 / (60 + 1), 6)
        assert result[0]["rrf_score"] == expected

    def test_rrf_rank_is_sequential_from_one(self):
        dense = [_dense("a", 1), _dense("b", 2), _dense("c", 3)]
        result = reciprocal_rank_fusion(dense, [], k=60)
        assert [r["rrf_rank"] for r in result] == [1, 2, 3]

    def test_dense_only_and_bm25_only_items_both_survive(self):
        dense = [_dense("dense-only", 1)]
        bm25 = [_bm25("bm25-only", 1)]
        result = reciprocal_rank_fusion(dense, bm25, k=60)
        ids = {r["chunk_id"] for r in result}
        assert ids == {"dense-only", "bm25-only"}

    def test_empty_inputs_return_empty_list(self):
        assert reciprocal_rank_fusion([], [], k=60) == []
