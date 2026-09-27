"""
Test cac ham logic thuan (khong goi network/DB) trong app/api/routes.py.
"""

from app.api.routes import _should_reuse_by_hash


class TestShouldReuseByHash:
    def test_no_existing_paper_means_no_reuse(self):
        assert _should_reuse_by_hash(None) is False

    def test_ready_existing_paper_is_reused(self):
        assert _should_reuse_by_hash({"status": "ready"}) is True

    def test_processing_existing_paper_is_not_reused(self):
        assert _should_reuse_by_hash({"status": "processing"}) is False

    def test_failed_existing_paper_is_not_reused(self):
        assert _should_reuse_by_hash({"status": "failed"}) is False
