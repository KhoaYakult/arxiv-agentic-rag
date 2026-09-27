"""
Test cac ham logic thuan (khong goi network/DB) trong app/api/routes.py.
"""

from app.api.routes import _should_clear_stale_hash, _should_reuse_by_hash


class TestShouldReuseByHash:
    def test_no_existing_paper_means_no_reuse(self):
        assert _should_reuse_by_hash(None) is False

    def test_ready_existing_paper_is_reused(self):
        assert _should_reuse_by_hash({"status": "ready"}) is True

    def test_processing_existing_paper_is_not_reused(self):
        assert _should_reuse_by_hash({"status": "processing"}) is False

    def test_failed_existing_paper_is_not_reused(self):
        assert _should_reuse_by_hash({"status": "failed"}) is False


class TestShouldClearStaleHash:
    """
    Bug tim thay o review Task 3: `papers.file_hash` la UNIQUE tren toan
    bang (db/schema.sql), khong scope rieng status='ready'. Neu khong go
    claim cu tren 1 paper 'processing'/'failed' truoc khi ghi row moi cung
    file_hash, upsert_paper() se nem UniqueViolationError - "fresh upload"
    fallback (Review Focus item b) se crash 500 thay vi thanh cong.
    """

    def test_no_existing_paper_means_no_clear_needed(self):
        assert _should_clear_stale_hash(None) is False

    def test_ready_existing_paper_needs_no_clear(self):
        assert _should_clear_stale_hash({"status": "ready"}) is False

    def test_processing_existing_paper_needs_clear(self):
        assert _should_clear_stale_hash({"status": "processing"}) is True

    def test_failed_existing_paper_needs_clear(self):
        assert _should_clear_stale_hash({"status": "failed"}) is True
