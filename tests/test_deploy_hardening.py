"""
Test network-free cho cac thay doi phuc vu deploy cong khai (Vercel):
validate paper_id/arxiv_id, kiem tra %PDF, gioi han upload, API key, job ket,
va reranker khi khong co model.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import routes
from app.api.auth import require_api_key
from app.config import settings


class TestPaperIdValidation:
    @pytest.mark.parametrize("pid", ["a", "cortex_ode_2023", "paper-1a2b3c", "0abc", "a" * 64])
    def test_valid_ids_pass(self, pid):
        assert routes.validate_paper_id(pid) == pid

    @pytest.mark.parametrize(
        "pid",
        ["", "../etc/passwd", "a/b", "a\\b", "..", "-abc", "_abc", "Abc", "a b", "a.b", "a" * 65, "abc\n"],
    )
    def test_invalid_ids_rejected_with_400(self, pid):
        with pytest.raises(HTTPException) as exc:
            routes.validate_paper_id(pid)
        assert exc.value.status_code == 400

    def test_lookup_id_allows_arxiv_dot_but_blocks_traversal(self):
        assert routes.validate_lookup_id("arxiv-2401.15884") == "arxiv-2401.15884"
        for bad in ["..", "a..b", "a/b", "a\\b", ".hidden", "x" * 65]:
            with pytest.raises(HTTPException):
                routes.validate_lookup_id(bad)


class TestMakePaperId:
    def test_slug_plus_6_hex(self):
        pid = routes.make_paper_id("My Great Paper (v2).pdf")
        assert pid.startswith("my-great-paper-v2-")
        assert routes.PAPER_ID_RE.fullmatch(pid)
        assert len(pid.rsplit("-", 1)[1]) == 6

    def test_same_filename_gives_different_ids(self):
        assert routes.make_paper_id("paper.pdf") != routes.make_paper_id("paper.pdf")

    def test_slug_truncated_to_40_chars(self):
        pid = routes.make_paper_id("x" * 200 + ".pdf")
        slug, suffix = pid.rsplit("-", 1)
        assert len(slug) <= 40 and len(suffix) == 6
        assert routes.PAPER_ID_RE.fullmatch(pid)

    @pytest.mark.parametrize("name", ["....pdf", "!!!.pdf", "../../etc/passwd.pdf", "Bài báo.pdf"])
    def test_weird_names_still_produce_valid_id(self, name):
        assert routes.PAPER_ID_RE.fullmatch(routes.make_paper_id(name))


class TestArxivIdValidation:
    @pytest.mark.parametrize("aid", ["2401.15884", "2401.1588", "1905.10044v2", "2401.15884v10"])
    def test_valid(self, aid):
        assert routes.validate_arxiv_id(aid) == aid

    @pytest.mark.parametrize(
        "aid",
        ["", "hep-th/9901001", "2401.158", "2401.158845", "240.15884", "2401.15884v", "../2401.15884",
         "2401.15884/../x", "https://arxiv.org/abs/2401.15884"],
    )
    def test_invalid_rejected_with_400(self, aid):
        with pytest.raises(HTTPException) as exc:
            routes.validate_arxiv_id(aid)
        assert exc.value.status_code == 400

    def test_parse_arxiv_title(self):
        xml = (
            '<feed xmlns="http://www.w3.org/2005/Atom"><title>query</title>'
            "<entry><title>  A Title\n   Across Lines </title></entry></feed>"
        )
        assert routes.parse_arxiv_title(xml) == "A Title Across Lines"
        assert routes.parse_arxiv_title('<feed xmlns="http://www.w3.org/2005/Atom"></feed>') is None


class TestPdfAndSizeChecks:
    def test_pdf_magic_ok(self):
        routes.ensure_pdf(b"%PDF-1.7\nrest")

    @pytest.mark.parametrize("content", [b"", b"<html>", b"PK\x03\x04", b" %PDF-1.4"])
    def test_non_pdf_rejected(self, content):
        with pytest.raises(HTTPException) as exc:
            routes.ensure_pdf(content)
        assert exc.value.status_code == 400

    def test_custom_status_for_non_pdf(self):
        with pytest.raises(HTTPException) as exc:
            routes.ensure_pdf(b"nope", status_code=502)
        assert exc.value.status_code == 502

    def test_size_limit_boundary(self):
        routes.enforce_upload_limit(b"x" * 1024 * 1024, max_mb=1.0)  # dung bang gioi han: OK
        with pytest.raises(HTTPException) as exc:
            routes.enforce_upload_limit(b"x" * (1024 * 1024 + 1), max_mb=1.0)
        assert exc.value.status_code == 413
        assert "arxiv" in exc.value.detail.lower()

    def test_size_limit_defaults_to_setting(self, monkeypatch):
        monkeypatch.setattr(settings, "max_upload_mb", 0.001)
        with pytest.raises(HTTPException) as exc:
            routes.enforce_upload_limit(b"x" * 2000)
        assert exc.value.status_code == 413


class TestStuckJobs:
    NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)

    def test_old_processing_is_stuck(self):
        paper = {"status": "processing", "created_at": self.NOW - timedelta(minutes=16)}
        assert routes.is_stuck(paper, now=self.NOW) is True

    def test_recent_processing_is_not_stuck(self):
        paper = {"status": "processing", "created_at": self.NOW - timedelta(minutes=14)}
        assert routes.is_stuck(paper, now=self.NOW) is False

    @pytest.mark.parametrize("st", ["ready", "failed"])
    def test_other_statuses_never_stuck(self, st):
        paper = {"status": st, "created_at": self.NOW - timedelta(days=3)}
        assert routes.is_stuck(paper, now=self.NOW) is False

    def test_naive_datetime_treated_as_utc(self):
        paper = {"status": "processing", "created_at": (self.NOW - timedelta(hours=1)).replace(tzinfo=None)}
        assert routes.is_stuck(paper, now=self.NOW) is True


class TestApiKeyDependency:
    @pytest.fixture
    def client(self):
        app = FastAPI()

        @app.get("/protected", dependencies=[Depends(require_api_key)])
        def protected():
            return {"ok": True}

        return TestClient(app)

    def test_disabled_when_key_empty(self, client, monkeypatch):
        monkeypatch.setattr(settings, "app_api_key", "")
        assert client.get("/protected").status_code == 200

    def test_missing_header_is_401(self, client, monkeypatch):
        monkeypatch.setattr(settings, "app_api_key", "s3cret")
        assert client.get("/protected").status_code == 401

    def test_wrong_key_is_401(self, client, monkeypatch):
        monkeypatch.setattr(settings, "app_api_key", "s3cret")
        assert client.get("/protected", headers={"X-API-Key": "nope"}).status_code == 401

    def test_non_ascii_key_does_not_crash(self, client, monkeypatch):
        monkeypatch.setattr(settings, "app_api_key", "s3cret")
        assert client.get("/protected", headers={"X-API-Key": "khóa".encode()}).status_code == 401

    def test_correct_key_is_200(self, client, monkeypatch):
        monkeypatch.setattr(settings, "app_api_key", "s3cret")
        assert client.get("/protected", headers={"X-API-Key": "s3cret"}).status_code == 200

    def test_real_router_health_open_papers_protected(self, monkeypatch):
        monkeypatch.setattr(settings, "app_api_key", "s3cret")
        app = FastAPI()
        app.include_router(routes.router, prefix="/api/v1")
        c = TestClient(app)
        assert c.get("/api/v1/health").status_code == 200
        assert c.get("/api/v1/papers").status_code == 401
        assert c.post("/api/v1/papers/arxiv", json={"arxiv_id": "2401.15884"}).status_code == 401
        assert c.post("/api/v1/ask", json={"question": "abc", "paper_id": "x"}).status_code == 401
        assert c.delete("/api/v1/papers/x").status_code == 401

    def test_arxiv_endpoint_rejects_bad_id_before_any_network(self, monkeypatch):
        monkeypatch.setattr(settings, "app_api_key", "")
        app = FastAPI()
        app.include_router(routes.router, prefix="/api/v1")
        r = TestClient(app).post("/api/v1/papers/arxiv", json={"arxiv_id": "../etc/passwd"})
        assert r.status_code == 400

    def test_upload_rejects_bad_paper_id_and_non_pdf(self, monkeypatch):
        monkeypatch.setattr(settings, "app_api_key", "")
        app = FastAPI()
        app.include_router(routes.router, prefix="/api/v1")
        c = TestClient(app)
        r = c.post("/api/v1/upload", files={"file": ("a.pdf", b"%PDF-1.4 x")}, data={"paper_id": "../evil"})
        assert r.status_code == 400
        r = c.post("/api/v1/upload", files={"file": ("a.pdf", b"not a pdf")})
        assert r.status_code == 400
        monkeypatch.setattr(settings, "max_upload_mb", 0.0001)
        r = c.post("/api/v1/upload", files={"file": ("a.pdf", b"%PDF-1.4 " + b"x" * 5000)})
        assert r.status_code == 413


class TestRerankerWithoutModel:
    def _candidates(self, n=8):
        return [{"chunk_id": f"c{i}", "text": f"t{i}", "rrf_score": 1 / (i + 1)} for i in range(n)]

    @pytest.fixture
    def disabled_reranker(self, monkeypatch):
        from app.indexing import reranker

        monkeypatch.setattr(settings, "cohere_api_key", "")
        monkeypatch.setattr(reranker, "_local_model_available", lambda: False)
        return reranker.RerankerManager()

    def test_mode_is_disabled(self, disabled_reranker):
        assert disabled_reranker.mode == "disabled"

    def test_keeps_rrf_order_and_adds_rank(self, disabled_reranker):
        cands = self._candidates()
        out = disabled_reranker.rerank("q", cands, top_k=5)
        assert [c["chunk_id"] for c in out] == ["c0", "c1", "c2", "c3", "c4"]
        assert [c["rerank_rank"] for c in out] == [1, 2, 3, 4, 5]
        assert "rerank_rank" not in cands[0]  # khong mutate input

    def test_fewer_candidates_than_top_k_and_empty(self, disabled_reranker):
        assert len(disabled_reranker.rerank("q", self._candidates(2), top_k=5)) == 2
        assert disabled_reranker.rerank("q", [], top_k=5) == []

    def test_warns_when_disabled(self, monkeypatch, capsys):
        from app.indexing import reranker

        monkeypatch.setattr(settings, "cohere_api_key", "")
        monkeypatch.setattr(reranker, "_local_model_available", lambda: False)
        reranker.RerankerManager()
        assert "[WARN]" in capsys.readouterr().out

    def test_cohere_key_wins_over_missing_local_model(self, monkeypatch):
        from app.indexing import reranker

        monkeypatch.setattr(settings, "cohere_api_key", "dummy")
        monkeypatch.setattr(reranker, "_local_model_available", lambda: False)
        assert reranker.RerankerManager().mode == "cohere"

    def test_get_reranker_is_singleton(self, monkeypatch):
        from app.indexing import reranker

        monkeypatch.setattr(reranker, "_reranker", None)
        assert reranker.get_reranker() is reranker.get_reranker()


class TestSettings:
    def test_allowed_origins_parsing(self, monkeypatch):
        monkeypatch.setattr(settings, "allowed_origins", " https://a.app , http://localhost:8501,, ")
        assert settings.allowed_origins_list == ["https://a.app", "http://localhost:8501"]

    def test_defaults(self):
        from app.config import Settings

        s = Settings(_env_file=None)
        assert s.max_upload_mb == 4.0
        assert s.gemini_model_name == "gemini-3.5-flash-lite"


class TestIndexJobDoesNotBlockEventLoop:
    """Hoi quy bug that: parse/embed SYNC goi thang trong `async def` dong bang ca server."""

    @staticmethod
    def _patch(monkeypatch, state):
        import threading
        import time
        import types

        from app.indexing import embeddings
        from app.ingestion import chunker
        from app.storage import repository

        lock = threading.Lock()

        def fake_parse(pdf_path, paper_id):
            time.sleep(0.3)
            return [], []

        def fake_embed(texts):
            with lock:
                state["running"] += 1
                state["max_running"] = max(state["max_running"], state["running"])
            time.sleep(0.3)
            with lock:
                state["running"] -= 1
            return []

        async def noop(*a, **k):
            return {}

        monkeypatch.setattr(chunker, "process_paper_ingestion", fake_parse)
        monkeypatch.setattr(
            embeddings, "get_embedding_provider",
            lambda: types.SimpleNamespace(embed_documents=fake_embed),
        )
        for name in ("insert_sections", "insert_chunks", "set_paper_status"):
            monkeypatch.setattr(repository, name, noop)

    def test_loop_keeps_ticking_during_sync_work(self, monkeypatch):
        import asyncio
        from pathlib import Path

        state = {"running": 0, "max_running": 0}
        self._patch(monkeypatch, state)

        async def scenario():
            ticks = 0

            async def ticker():
                nonlocal ticks
                while True:
                    await asyncio.sleep(0.02)
                    ticks += 1

            t = asyncio.create_task(ticker())
            await routes._process_and_index_paper(Path("x.pdf"), "p")
            t.cancel()
            return ticks

        # Job mat ~0.6s; neu loop bi block thi ticks ~0, binh thuong ~25+.
        assert asyncio.run(scenario()) >= 10

    def test_only_one_embedding_job_at_a_time(self, monkeypatch):
        import asyncio
        from pathlib import Path

        state = {"running": 0, "max_running": 0}
        self._patch(monkeypatch, state)

        async def scenario():
            await asyncio.gather(
                routes._process_and_index_paper(Path("a.pdf"), "a"),
                routes._process_and_index_paper(Path("b.pdf"), "b"),
            )

        asyncio.run(scenario())
        assert state["max_running"] == 1
