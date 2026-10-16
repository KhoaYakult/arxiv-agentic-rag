"""
Fixture cho integration test: chạy trên 1 Postgres + pgvector THẬT nhưng DÙNG RIÊNG
để test (container pgvector ở CI hoặc docker local) - tuyệt đối không phải Supabase thật.

Bật bằng biến môi trường TEST_DATABASE_URL; không có thì cả thư mục này tự skip, nên
`make test` / CI không cần DB vẫn xanh. Xem tests/integration/README.md để chạy local.

Chốt an toàn: từ chối chạy nếu URL chứa "supabase" - test này TRUNCATE bảng.
"""

import asyncio
import os
from pathlib import Path

import asyncpg
import pytest

from app.config import settings
from app.storage import repository

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "")
SCHEMA_SQL = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def pytest_collection_modifyitems(config, items):
    if TEST_DB_URL:
        return
    skip = pytest.mark.skip(reason="Chua dat TEST_DATABASE_URL (Postgres+pgvector rieng de test)")
    for item in items:
        if "tests/integration" in str(item.fspath).replace("\\", "/"):
            item.add_marker(skip)


async def _prepare_database() -> None:
    """Dựng DB giống Supabase: extension pgvector nằm ở schema `extensions`, search_path gồm cả nó."""
    conn = await asyncpg.connect(TEST_DB_URL)
    try:
        await conn.execute("CREATE SCHEMA IF NOT EXISTS extensions")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions")
        db_name = await conn.fetchval("SELECT current_database()")
        await conn.execute(f'ALTER DATABASE "{db_name}" SET search_path = public, extensions')
    finally:
        await conn.close()

    # Kết nối mới để nhận search_path mới rồi mới chạy schema.sql
    conn = await asyncpg.connect(TEST_DB_URL)
    try:
        await conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def _guard_and_prepare_db():
    if not TEST_DB_URL:
        yield
        return
    if "supabase" in TEST_DB_URL.lower():
        pytest.exit("TEST_DATABASE_URL tro vao Supabase - tu choi chay (test se TRUNCATE bang).", returncode=2)
    asyncio.run(_prepare_database())
    yield


@pytest.fixture(autouse=True)
def _point_repository_at_test_db(monkeypatch):
    """Ép repository/checkpointer dùng DB test, KHÔNG dùng DATABASE_URL trong .env."""
    if not TEST_DB_URL:
        yield
        return
    monkeypatch.setattr(settings, "database_url", TEST_DB_URL)
    monkeypatch.setattr(repository, "_pool", None)
    yield


def run(scenario):
    """
    Chạy 1 kịch bản async trong 1 event loop riêng rồi đóng pool.
    Pool asyncpg gắn với event loop đã tạo ra nó, nên MỖI test chỉ được dùng đúng 1
    lần asyncio.run (cùng lý do rag_graph.py phải async hoàn toàn).
    """
    async def _wrapped():
        pool = await repository.get_pool()
        await pool.execute("TRUNCATE papers CASCADE")
        try:
            return await scenario()
        finally:
            await repository.close_pool()

    return asyncio.run(_wrapped())
