"""AsyncPostgresSaver (rag_graph) kết nối được tới Postgres thật, tự tạo bảng, đóng pool sạch."""

import asyncio

from app.agent import rag_graph
from tests.integration.conftest import run


def test_checkpointer_setup_creates_tables_and_closes_cleanly():
    async def scenario():
        saver = await rag_graph._get_checkpointer()
        try:
            async with rag_graph._checkpointer_pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name IN ('checkpoints','checkpoint_writes','checkpoint_blobs')"
                )
                tables = {row["table_name"] for row in await cur.fetchall()}
            return saver, tables
        finally:
            await rag_graph.close_checkpointer()

    saver, tables = run(scenario)
    assert saver is not None
    assert tables == {"checkpoints", "checkpoint_writes", "checkpoint_blobs"}
    assert rag_graph._checkpointer_pool is None


def test_missing_database_url_raises_instead_of_falling_back(monkeypatch):
    import pytest

    from app.config import settings

    monkeypatch.setattr(settings, "database_url", "")
    with pytest.raises(ValueError):
        asyncio.run(rag_graph._get_checkpointer())
