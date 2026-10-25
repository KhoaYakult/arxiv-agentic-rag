"""
Test app/storage/pdf_store.py bang httpx.MockTransport - KHONG goi Supabase that.
"""

import asyncio
import json

import httpx
import pytest

from app.config import settings
from app.storage import pdf_store


@pytest.fixture
def storage(monkeypatch):
    """Bat Storage voi URL/key gia + ghi lai moi request gui di."""
    monkeypatch.setattr(settings, "supabase_url", "https://proj.supabase.co/")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")
    monkeypatch.setattr(settings, "storage_bucket", "papers")
    calls: list[httpx.Request] = []
    responses: dict[str, httpx.Response] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        key = f"{request.method} {request.url.path}"
        return responses.get(key, httpx.Response(200, json={}))

    monkeypatch.setattr(pdf_store, "_transport", httpx.MockTransport(handler))
    return calls, responses


class TestIsEnabled:
    def test_disabled_without_url_or_key(self, monkeypatch):
        monkeypatch.setattr(settings, "supabase_url", "")
        monkeypatch.setattr(settings, "supabase_service_role_key", "k")
        assert pdf_store.is_enabled() is False
        monkeypatch.setattr(settings, "supabase_url", "https://x.supabase.co")
        monkeypatch.setattr(settings, "supabase_service_role_key", "")
        assert pdf_store.is_enabled() is False

    def test_enabled_with_both(self, storage):
        assert pdf_store.is_enabled() is True


class TestUpload:
    def test_upload_posts_pdf_with_upsert_and_auth(self, storage):
        calls, _ = storage
        asyncio.run(pdf_store.upload_pdf("arxiv-1706.03762", b"%PDF-1.4 data"))
        (req,) = calls
        assert req.method == "POST"
        assert req.url.path == "/storage/v1/object/papers/arxiv-1706.03762.pdf"
        assert req.headers["authorization"] == "Bearer service-key"
        assert req.headers["apikey"] == "service-key"
        assert req.headers["x-upsert"] == "true"
        assert req.headers["content-type"] == "application/pdf"
        assert req.content == b"%PDF-1.4 data"

    def test_upload_error_raises_storage_error(self, storage):
        _, responses = storage
        responses["POST /storage/v1/object/papers/p.pdf"] = httpx.Response(500, text="boom")
        with pytest.raises(pdf_store.StorageError):
            asyncio.run(pdf_store.upload_pdf("p", b"%PDF"))

    def test_transport_error_raises_storage_error(self, monkeypatch):
        monkeypatch.setattr(settings, "supabase_url", "https://proj.supabase.co")
        monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        monkeypatch.setattr(pdf_store, "_transport", httpx.MockTransport(handler))
        with pytest.raises(pdf_store.StorageError):
            asyncio.run(pdf_store.upload_pdf("p", b"%PDF"))


class TestSignedUrl:
    def test_returns_absolute_url(self, storage):
        calls, responses = storage
        responses["POST /storage/v1/object/sign/papers/p.pdf"] = httpx.Response(
            200, json={"signedURL": "/object/sign/papers/p.pdf?token=abc"}
        )
        url = asyncio.run(pdf_store.signed_url("p"))
        assert url == "https://proj.supabase.co/storage/v1/object/sign/papers/p.pdf?token=abc"
        assert json.loads(calls[0].content) == {"expiresIn": pdf_store.SIGNED_URL_TTL}

    def test_missing_signed_url_raises(self, storage):
        _, responses = storage
        responses["POST /storage/v1/object/sign/papers/p.pdf"] = httpx.Response(200, json={})
        with pytest.raises(pdf_store.StorageError):
            asyncio.run(pdf_store.signed_url("p"))

    def test_http_error_raises(self, storage):
        _, responses = storage
        responses["POST /storage/v1/object/sign/papers/p.pdf"] = httpx.Response(400, json={"error": "not_found"})
        with pytest.raises(pdf_store.StorageError):
            asyncio.run(pdf_store.signed_url("p"))

    def test_non_json_body_raises_storage_error(self, storage):
        _, responses = storage
        responses["POST /storage/v1/object/sign/papers/p.pdf"] = httpx.Response(200, text="<html>")
        with pytest.raises(pdf_store.StorageError):
            asyncio.run(pdf_store.signed_url("p"))


class TestDelete:
    def test_delete_calls_object_path(self, storage):
        calls, _ = storage
        asyncio.run(pdf_store.delete_pdf("p"))
        assert (calls[0].method, calls[0].url.path) == ("DELETE", "/storage/v1/object/papers/p.pdf")

    def test_delete_missing_object_is_not_an_error(self, storage):
        _, responses = storage
        responses["DELETE /storage/v1/object/papers/p.pdf"] = httpx.Response(404, json={"error": "not_found"})
        asyncio.run(pdf_store.delete_pdf("p"))  # khong raise

    def test_delete_server_error_raises(self, storage):
        _, responses = storage
        responses["DELETE /storage/v1/object/papers/p.pdf"] = httpx.Response(500, text="x")
        with pytest.raises(pdf_store.StorageError):
            asyncio.run(pdf_store.delete_pdf("p"))
