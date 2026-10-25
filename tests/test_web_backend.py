"""
Test cac thay doi backend phuc vu web UI moi (has_pdf, pdf-url, SourceChunk.text,
luu PDF trong job nen) - KHONG goi DB/Storage that (monkeypatch repository/pdf_store).
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.api.schemas import PaperInfo, PaperStatusResponse, PdfUrlResponse, SourceChunk
from app.config import settings


def make_client(monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "app_api_key", "")
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    return TestClient(app)


class TestSchemas:
    def test_has_pdf_defaults_false(self):
        assert PaperInfo(paper_id="a", title="A", num_chunks=1).has_pdf is False
        assert PaperStatusResponse(paper_id="a", title="A", status="ready", num_chunks=1).has_pdf is False

    def test_source_chunk_text_defaults_empty(self):
        s = SourceChunk(chunk_id="c", section="S", content_preview="p", page_num=1)
        assert s.text == ""

    def test_pdf_url_response(self):
        assert PdfUrlResponse(url="https://x", expires_in=3600).expires_in == 3600


class TestPapersListCarriesHasPdf:
    def test_list_and_status_pass_has_pdf(self, monkeypatch):
        from app.storage import repository

        row = {"paper_id": "a", "title": "A", "num_chunks": 3, "status": "ready",
               "has_pdf": True, "created_at": None}

        async def fake_list():
            return [row]

        async def fake_get(pid):
            return row

        monkeypatch.setattr(repository, "list_papers", fake_list)
        monkeypatch.setattr(repository, "get_paper", fake_get)
        c = make_client(monkeypatch)
        assert c.get("/api/v1/papers").json()["papers"][0]["has_pdf"] is True
        assert c.get("/api/v1/papers/a/status").json()["has_pdf"] is True
