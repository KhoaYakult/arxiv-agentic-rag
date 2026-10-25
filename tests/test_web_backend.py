"""
Test cac thay doi backend phuc vu web UI moi (has_pdf, pdf-url, SourceChunk.text,
luu PDF trong job nen) - KHONG goi DB/Storage that (monkeypatch repository/pdf_store).
"""

import asyncio

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


class TestPdfUrlEndpoint:
    def _setup(self, monkeypatch, paper, enabled=True, sign=None):
        from app.storage import pdf_store, repository

        async def fake_get(pid):
            return paper

        async def fake_sign(pid, expires_in=3600):
            if sign is None:
                return f"https://proj.supabase.co/storage/v1/object/sign/papers/{pid}.pdf?token=t"
            raise sign

        monkeypatch.setattr(repository, "get_paper", fake_get)
        monkeypatch.setattr(pdf_store, "is_enabled", lambda: enabled)
        monkeypatch.setattr(pdf_store, "signed_url", fake_sign)
        return make_client(monkeypatch)

    def test_ok(self, monkeypatch):
        c = self._setup(monkeypatch, {"paper_id": "a", "has_pdf": True})
        r = c.get("/api/v1/papers/a/pdf-url")
        assert r.status_code == 200
        assert r.json() == {"url": "https://proj.supabase.co/storage/v1/object/sign/papers/a.pdf?token=t", "expires_in": 3600}

    def test_404_when_paper_missing(self, monkeypatch):
        assert self._setup(monkeypatch, None).get("/api/v1/papers/a/pdf-url").status_code == 404

    def test_404_when_no_pdf(self, monkeypatch):
        assert self._setup(monkeypatch, {"paper_id": "a", "has_pdf": False}).get("/api/v1/papers/a/pdf-url").status_code == 404

    def test_404_when_storage_disabled(self, monkeypatch):
        c = self._setup(monkeypatch, {"paper_id": "a", "has_pdf": True}, enabled=False)
        assert c.get("/api/v1/papers/a/pdf-url").status_code == 404

    def test_502_when_storage_fails(self, monkeypatch):
        from app.storage.pdf_store import StorageError

        c = self._setup(monkeypatch, {"paper_id": "a", "has_pdf": True}, sign=StorageError("x"))
        assert c.get("/api/v1/papers/a/pdf-url").status_code == 502

    def test_400_on_bad_id(self, monkeypatch):
        c = self._setup(monkeypatch, {"paper_id": "a", "has_pdf": True})
        assert c.get("/api/v1/papers/a..b/pdf-url").status_code == 400

    def test_protected_by_api_key(self, monkeypatch):
        c = self._setup(monkeypatch, {"paper_id": "a", "has_pdf": True})
        monkeypatch.setattr(settings, "app_api_key", "s3cret")
        assert c.get("/api/v1/papers/a/pdf-url").status_code == 401


class TestStorePdfInIndexJob:
    def _patch(self, monkeypatch, upload_error=None):
        import types

        from app.indexing import embeddings
        from app.ingestion import chunker
        from app.storage import pdf_store, repository

        events: list = []

        async def rec(name, *a, **k):
            events.append((name, a))

        monkeypatch.setattr(chunker, "process_paper_ingestion", lambda p, paper_id: ([], []))
        monkeypatch.setattr(embeddings, "get_embedding_provider",
                            lambda: types.SimpleNamespace(embed_documents=lambda t: []))
        monkeypatch.setattr(repository, "insert_sections", lambda *a, **k: rec("sections", *a))
        monkeypatch.setattr(repository, "insert_chunks", lambda *a, **k: rec("chunks", *a))
        monkeypatch.setattr(repository, "set_paper_status", lambda pid, status, **k: rec("status", pid, status))
        monkeypatch.setattr(repository, "set_has_pdf", lambda pid, v: rec("has_pdf", pid, v))
        monkeypatch.setattr(pdf_store, "is_enabled", lambda: True)

        async def fake_upload(pid, content):
            if upload_error:
                raise upload_error
            events.append(("upload", (pid, content)))

        monkeypatch.setattr(pdf_store, "upload_pdf", fake_upload)
        return events

    def test_uploads_pdf_then_sets_has_pdf_after_ready(self, monkeypatch, tmp_path):
        events = self._patch(monkeypatch)
        pdf = tmp_path / "p.pdf"
        pdf.write_bytes(b"%PDF-1.4 hello")
        asyncio.run(routes._process_and_index_paper(pdf, "p"))
        names = [e[0] for e in events]
        assert names.index("status") < names.index("upload") < names.index("has_pdf")
        assert ("status", ("p", "ready")) in events
        assert ("upload", ("p", b"%PDF-1.4 hello")) in events
        assert ("has_pdf", ("p", True)) in events

    def test_storage_failure_keeps_paper_ready(self, monkeypatch, tmp_path):
        from app.storage.pdf_store import StorageError

        events = self._patch(monkeypatch, upload_error=StorageError("down"))
        pdf = tmp_path / "p.pdf"
        pdf.write_bytes(b"%PDF")
        asyncio.run(routes._process_and_index_paper(pdf, "p"))
        assert ("status", ("p", "ready")) in events
        assert ("status", ("p", "failed")) not in events
        assert not [e for e in events if e[0] == "has_pdf"]

    def test_storage_disabled_skips_upload(self, monkeypatch, tmp_path):
        from app.storage import pdf_store

        events = self._patch(monkeypatch)
        monkeypatch.setattr(pdf_store, "is_enabled", lambda: False)
        pdf = tmp_path / "p.pdf"
        pdf.write_bytes(b"%PDF")
        asyncio.run(routes._process_and_index_paper(pdf, "p"))
        assert [e[0] for e in events].count("upload") == 0


class TestDeleteRemovesPdf:
    def test_delete_calls_storage_and_ignores_storage_errors(self, monkeypatch):
        from app.storage import pdf_store, repository
        from app.storage.pdf_store import StorageError

        deleted = []

        async def fake_get(pid):
            return {"paper_id": pid}

        async def fake_delete_row(pid):
            deleted.append(("row", pid))

        async def fake_delete_pdf(pid):
            deleted.append(("pdf", pid))
            raise StorageError("down")

        monkeypatch.setattr(repository, "get_paper", fake_get)
        monkeypatch.setattr(repository, "delete_paper", fake_delete_row)
        monkeypatch.setattr(pdf_store, "is_enabled", lambda: True)
        monkeypatch.setattr(pdf_store, "delete_pdf", fake_delete_pdf)
        r = make_client(monkeypatch).delete("/api/v1/papers/a")
        assert r.status_code == 204
        assert deleted == [("row", "a"), ("pdf", "a")]


class TestAskSourcesCarryText:
    def test_sources_have_full_text_in_retrieval_order(self, monkeypatch):
        from langchain_core.messages import AIMessage

        from app.agent import rag_graph
        from app.storage import repository

        async def fake_get(pid):
            return {"paper_id": pid}

        long_text = "x" * 700
        chunks = [
            {"chunk_id": "c2", "parent_section_name": "Results", "text": long_text, "page_num": 8},
            {"chunk_id": "c1", "parent_section_name": "Intro", "text": "short", "page_num": None},
        ]

        async def fake_ask(question, paper_id, thread_id):
            return {"messages": [AIMessage(content="Ans [1]")], "retrieved_chunks": chunks,
                    "grade": "yes", "rewrite_count": 0}

        monkeypatch.setattr(repository, "get_paper", fake_get)
        monkeypatch.setattr(rag_graph, "ask", fake_ask)
        r = make_client(monkeypatch).post("/api/v1/ask", json={"question": "abc?", "paper_id": "a", "thread_id": "t"})
        src = r.json()["sources"]
        assert [s["chunk_id"] for s in src] == ["c2", "c1"]
        assert src[0]["text"] == long_text
        assert src[0]["content_preview"] == long_text[:150]
        assert src[1]["page_num"] is None
