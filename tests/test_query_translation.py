"""Dich cau hoi tieng Viet sang tieng Anh cho nhanh tu khoa (app/agent/rag_graph.py) - khong goi mang."""

import asyncio

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda


class TestIsVietnamese:
    def test_vietnamese_questions(self):
        from app.agent.rag_graph import is_vietnamese

        assert is_vietnamese("Mô hình Transformer cỡ big có bao nhiêu tham số?")
        assert is_vietnamese("Bài báo định nghĩa self-attention như thế nào?")
        assert is_vietnamese("CRAG dùng ngưỡng nào trên PopQA?")

    def test_english_and_loanwords_are_not(self):
        from app.agent.rag_graph import is_vietnamese

        assert not is_vietnamese("How does the paper define self-attention?")
        assert not is_vietnamese("A naïve baseline")  # 1 ky tu co dau
        assert not is_vietnamese("")


class TestSparseQueryFor:
    def _patch(self, monkeypatch, llm):
        from app.llm import llm_factory

        monkeypatch.setattr(llm_factory, "get_translator_llm", lambda: llm)

    def test_translates_vietnamese(self, monkeypatch):
        from app.agent.rag_graph import sparse_query_for

        seen = {}

        def fake(prompt):
            seen["prompt"] = prompt.to_string()
            return AIMessage(content="  How does the paper define self-attention?\n")

        self._patch(monkeypatch, RunnableLambda(fake))
        out = asyncio.run(sparse_query_for("Bài báo định nghĩa self-attention như thế nào?"))
        assert out == "How does the paper define self-attention?"
        assert "Bài báo định nghĩa self-attention" in seen["prompt"]

    def test_english_question_not_translated(self, monkeypatch):
        from app.agent.rag_graph import sparse_query_for

        def boom(_):
            raise AssertionError("khong duoc goi dich cho cau tieng Anh")

        self._patch(monkeypatch, RunnableLambda(boom))
        assert asyncio.run(sparse_query_for("How does the paper define self-attention?")) is None

    def test_disabled_translator(self, monkeypatch):
        from app.agent.rag_graph import sparse_query_for

        self._patch(monkeypatch, None)
        assert asyncio.run(sparse_query_for("Bài báo định nghĩa self-attention như thế nào?")) is None

    def test_translation_error_falls_back_to_original(self, monkeypatch):
        from app.agent.rag_graph import sparse_query_for

        def boom(_):
            raise RuntimeError("429 rate limit")

        self._patch(monkeypatch, RunnableLambda(boom))
        assert asyncio.run(sparse_query_for("Bài báo định nghĩa self-attention như thế nào?")) is None


class TestHybridSearchSparseQuery:
    def test_sparse_branch_uses_separate_text(self, monkeypatch):
        from app.storage import repository

        calls = {}

        async def dense(pid, emb, k):
            return [{"chunk_id": "a", "dense_rank": 1}]

        async def sparse(pid, text, k):
            calls["sparse"] = text
            return [{"chunk_id": "a", "bm25_rank": 1}]

        monkeypatch.setattr(repository, "dense_search", dense)
        monkeypatch.setattr(repository, "sparse_search", sparse)
        asyncio.run(repository.hybrid_search("p", "câu tiếng Việt", [0.0], sparse_query_text="english text"))
        assert calls["sparse"] == "english text"
        asyncio.run(repository.hybrid_search("p", "câu tiếng Việt", [0.0]))
        assert calls["sparse"] == "câu tiếng Việt"


class TestGetTranslatorLlm:
    def test_disabled_without_model(self, monkeypatch):
        from app.config import settings
        from app.llm import llm_factory

        monkeypatch.setattr(settings, "groq_api_key", "gsk_test")
        monkeypatch.setattr(settings, "translate_model", "")
        llm_factory.get_translator_llm.cache_clear()
        assert llm_factory.get_translator_llm() is None
        llm_factory.get_translator_llm.cache_clear()

    def test_qwen_with_short_timeout_and_no_fallback(self, monkeypatch):
        from app.config import settings
        from app.llm import llm_factory

        monkeypatch.setattr(settings, "groq_api_key", "gsk_test")
        monkeypatch.setattr(settings, "translate_model", "qwen/qwen3.8-27b")
        llm_factory.get_translator_llm.cache_clear()
        llm = llm_factory.get_translator_llm()
        assert llm.model_name == "qwen/qwen3.8-27b"
        assert llm.reasoning_effort == "none" and llm.temperature < 0.01  # ChatGroq doi 0 -> 1e-8
        # Dich la buoc phu: cham/loi thi bo qua, khong duoc treo /ask
        assert llm.request_timeout == 8 and llm.max_retries == 1
        llm_factory.get_translator_llm.cache_clear()
