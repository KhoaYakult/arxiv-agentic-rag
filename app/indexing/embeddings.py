"""
app/indexing/embeddings.py
============================
Embedding provider cho Phase 2 (Postgres + pgvector).

Phase 1 dung HuggingFaceAPIEmbeddings (vector_store.py, HF Inference API,
all-MiniLM-L6-v2, 384-dim, khong phan biet query/document). Phase 2 chuyen
sang Gemini gemini-embedding-001 (768-dim qua MRL truncation) - xem
docs/ROADMAP.md muc 1 de biet ly do chon.

CHUA duoc wire vao routes.py/hybrid_retriever.py - vector_store.py van la
pipeline dang chay that, da verify end-to-end (xem project-memory/STATE.md).
File nay se duoc dung khi cutover sang app/storage/repository.py.
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from functools import lru_cache

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings

EMBEDDING_DIM = 768


class GeminiEmbeddingProvider:
    """
    Embed van ban qua Gemini API, truncate con 768-dim bang MRL (Matryoshka
    Representation Learning - model duoc train de cac chieu dau tien van giu
    chat luong tot ngay ca khi cat bot, khac voi cat ngau nhien).

    Dung task_type BAT DOI XUNG (asymmetric): RETRIEVAL_DOCUMENT luc index,
    RETRIEVAL_QUERY luc tim kiem - dung dung bai toan retrieval. Phase 1
    (HuggingFaceAPIEmbeddings) dung chung 1 cach embed cho ca 2 chieu.

    Interface giu giong HuggingFaceAPIEmbeddings (embed_documents/embed_query)
    de repository.py khong can biet dang dung provider nao.
    """

    MODEL_NAME = "models/gemini-embedding-001"

    def __init__(self, api_key: str = "", dim: int = EMBEDDING_DIM):
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        resolved_key = api_key or settings.gemini_api_key
        if not resolved_key:
            raise ValueError(
                "GEMINI_API_KEY chua duoc cau hinh trong .env! "
                "Truy cap https://aistudio.google.com/apikey de lay key mien phi."
            )

        self.dim = dim
        self._client = GoogleGenerativeAIEmbeddings(
            model=self.MODEL_NAME,
            google_api_key=resolved_key,
        )

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed danh sach chunk luc index (task_type=RETRIEVAL_DOCUMENT)."""
        if not texts:
            return []
        return self._client.embed_documents(
            texts, task_type="RETRIEVAL_DOCUMENT", output_dimensionality=self.dim
        )

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def embed_query(self, text: str) -> list[float]:
        """Embed 1 cau hoi luc tim kiem (task_type=RETRIEVAL_QUERY)."""
        return self._client.embed_query(
            text, task_type="RETRIEVAL_QUERY", output_dimensionality=self.dim
        )


@lru_cache(maxsize=1)
def get_embedding_provider() -> GeminiEmbeddingProvider:
    """Factory function - giong pattern get_llm() trong app/llm/llm_factory.py."""
    return GeminiEmbeddingProvider()


if __name__ == "__main__":
    provider = get_embedding_provider()
    q_vec = provider.embed_query("What is CortexODE?")
    print(f"[TEST] embed_query dim: {len(q_vec)}")

    d_vecs = provider.embed_documents(
        ["CortexODE is a neural ODE model.", "Another unrelated sentence."]
    )
    print(f"[TEST] embed_documents dims: {[len(v) for v in d_vecs]}")
