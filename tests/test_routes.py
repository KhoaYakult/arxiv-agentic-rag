"""
Test cac ham logic thuan (khong goi network/DB) trong app/api/routes.py.
"""

from app.api.routes import _should_clear_stale_hash, _should_reuse_by_hash, is_quota_error


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


class TestIsQuotaError:
    def test_detects_quota_markers(self):
        assert is_quota_error(RuntimeError("429 Too Many Requests"))
        assert is_quota_error(RuntimeError("Error: RESOURCE_EXHAUSTED"))
        assert is_quota_error(RuntimeError("Rate limit reached"))

    def test_detects_http_code_attributes(self):
        class WithStatus(Exception):
            status_code = 429

        class WithCode(Exception):
            code = 429

        assert is_quota_error(WithStatus("boom"))
        assert is_quota_error(WithCode("boom"))

    def test_follows_exception_chain(self):
        try:
            try:
                raise RuntimeError("429 quota")
            except RuntimeError as inner:
                raise ValueError("wrapped") from inner
        except ValueError as outer:
            assert is_quota_error(outer)

    def test_429_inside_other_numbers_is_not_quota(self):
        # arXiv id 2310.04291 chua chuoi "429" nhung khong phai loi quota
        assert not is_quota_error(RuntimeError("paper 2310.04291 failed"))
        assert not is_quota_error(ValueError("bad json"))
