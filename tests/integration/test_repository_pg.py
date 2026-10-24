"""
Integration test cho app/storage/repository.py trên Postgres + pgvector thật.
Embedding giả (vector cơ sở) để kết quả dense tất định, không gọi Gemini.
"""

import asyncpg
import pytest

from app.ingestion.chunker import ChildChunk, ParentSection
from app.storage import repository
from tests.integration.conftest import run

DIM = 768


def vec(i: int) -> list[float]:
    """Vector cơ sở thứ i: 2 vector khác i có cosine distance = 1, cùng i = 0."""
    v = [0.0] * DIM
    v[i] = 1.0
    return v


def make_chunk(idx: int, text: str, section: str = "sec_0", page: int | None = 1) -> ChildChunk:
    return ChildChunk(
        chunk_id=f"p1_chk_{idx}",
        parent_section_id=section,
        parent_section_name="Method",
        paper_id="p1",
        text=text,
        page_num=page,
        char_start=0,
        char_end=len(text),
    )


async def seed_ready_paper(paper_id="p1", file_hash=None):
    await repository.upsert_paper(paper_id, "Title", f"{paper_id}.pdf", file_hash=file_hash)
    await repository.set_paper_status(paper_id, "ready", num_chunks=0)


class TestIndexingRoundTrip:
    def test_sections_store_page_range_and_chunks_store_page_num(self):
        async def scenario():
            await repository.upsert_paper("p1", "T", "p1.pdf")
            sec_map = await repository.insert_sections(
                "p1", [ParentSection("sec_0", "Method", "text of section", page_start=2, page_end=3)]
            )
            chunks = [make_chunk(0, "alpha beta", page=2), make_chunk(1, "gamma delta", page=None)]
            await repository.insert_chunks("p1", chunks, [vec(0), vec(1)], sec_map)

            pool = await repository.get_pool()
            sec = await pool.fetchrow("SELECT page_start, page_end FROM sections WHERE paper_id='p1'")
            rows = await pool.fetch(
                "SELECT chunk_id, page_num, char_end, section_pk FROM chunks ORDER BY chunk_id"
            )
            return sec, rows, sec_map

        sec, rows, sec_map = run(scenario)
        assert (sec["page_start"], sec["page_end"]) == (2, 3)
        assert [r["page_num"] for r in rows] == [2, None]
        assert all(r["section_pk"] == sec_map["sec_0"] for r in rows)

    def test_mismatched_embeddings_raise(self):
        async def scenario():
            await repository.upsert_paper("p1", "T", "p1.pdf")
            with pytest.raises(ValueError):
                await repository.insert_chunks("p1", [make_chunk(0, "x")], [], {})

        run(scenario)

    def test_reindexing_same_chunk_id_updates_instead_of_duplicating(self):
        async def scenario():
            await repository.upsert_paper("p1", "T", "p1.pdf")
            await repository.insert_chunks("p1", [make_chunk(0, "old text", page=1)], [vec(0)], {})
            await repository.insert_chunks("p1", [make_chunk(0, "new text", page=5)], [vec(0)], {})
            pool = await repository.get_pool()
            return await pool.fetch("SELECT text, page_num FROM chunks")

        rows = run(scenario)
        assert len(rows) == 1 and rows[0]["text"] == "new text" and rows[0]["page_num"] == 5


class TestHybridSearch:
    def test_dense_and_sparse_both_contribute_and_page_num_is_returned(self):
        async def scenario():
            await seed_ready_paper()
            chunks = [
                make_chunk(0, "convolutional networks for imaging", page=1),
                make_chunk(1, "neural ordinary differential equations flow", page=7),
                make_chunk(2, "completely unrelated cooking recipe", page=9),
            ]
            await repository.insert_chunks("p1", chunks, [vec(0), vec(1), vec(2)], {})
            # dense gần chunk_0 nhất; sparse khớp từ khoá "ordinary" của chunk_1
            return await repository.hybrid_search("p1", "ordinary", vec(0), top_k=3)

        results = run(scenario)
        ids = [r["chunk_id"] for r in results]
        assert {"p1_chk_0", "p1_chk_1"} <= set(ids[:2])
        by_id = {r["chunk_id"]: r for r in results}
        assert by_id["p1_chk_1"]["page_num"] == 7
        assert by_id["p1_chk_1"]["parent_section_name"] == "Unknown section"  # section_pk NULL
        assert [r["rrf_rank"] for r in results] == list(range(1, len(results) + 1))

    def test_search_is_isolated_per_paper(self):
        async def scenario():
            await seed_ready_paper("p1")
            await seed_ready_paper("p2")
            await repository.insert_chunks("p1", [make_chunk(0, "shared keyword here")], [vec(0)], {})
            other = ChildChunk("p2_chk_0", "sec_0", "S", "p2", "shared keyword here")
            await repository.insert_chunks("p2", [other], [vec(0)], {})
            return await repository.hybrid_search("p1", "keyword", vec(0))

        results = run(scenario)
        assert {r["paper_id"] for r in results} == {"p1"}


class TestPaperLifecycle:
    def test_list_papers_only_returns_ready(self):
        async def scenario():
            await repository.upsert_paper("a", "A", "a.pdf")  # processing
            await seed_ready_paper("b")
            await repository.upsert_paper("c", "C", "c.pdf")
            await repository.set_paper_status("c", "failed")
            return [p["paper_id"] for p in await repository.list_papers()]

        assert run(scenario) == ["b"]

    def test_delete_cascades_to_sections_and_chunks(self):
        async def scenario():
            await repository.upsert_paper("p1", "T", "p1.pdf")
            sec_map = await repository.insert_sections("p1", [ParentSection("sec_0", "M", "txt")])
            await repository.insert_chunks("p1", [make_chunk(0, "x")], [vec(0)], sec_map)
            await repository.delete_paper("p1")
            pool = await repository.get_pool()
            return (
                await pool.fetchval("SELECT count(*) FROM sections"),
                await pool.fetchval("SELECT count(*) FROM chunks"),
            )

        assert run(scenario) == (0, 0)


class TestFileHashDedup:
    def test_get_paper_by_hash(self):
        async def scenario():
            await seed_ready_paper("a", file_hash="H1")
            return await repository.get_paper_by_hash("H1"), await repository.get_paper_by_hash("nope")

        found, missing = run(scenario)
        assert found["paper_id"] == "a" and missing is None

    def test_stale_hash_blocks_new_paper_until_cleared(self):
        """Tái hiện bug #13: paper cũ 'failed' vẫn giữ file_hash UNIQUE -> insert paper mới vỡ."""
        async def scenario():
            await repository.upsert_paper("a", "A", "a.pdf", file_hash="H")
            await repository.set_paper_status("a", "failed")
            with pytest.raises(asyncpg.exceptions.UniqueViolationError):
                await repository.upsert_paper("b", "B", "b.pdf", file_hash="H")
            await repository.clear_stale_file_hash("a")
            await repository.upsert_paper("b", "B", "b.pdf", file_hash="H")
            return (await repository.get_paper_by_hash("H"))["paper_id"]

        assert run(scenario) == "b"

    def test_clear_stale_hash_never_touches_a_ready_paper(self):
        async def scenario():
            await seed_ready_paper("a", file_hash="H")
            await repository.clear_stale_file_hash("a")
            return await repository.get_paper_by_hash("H")

        assert run(scenario)["paper_id"] == "a"


class TestDeployHelpers:
    def test_reupload_resets_created_at_so_failed_paper_is_not_instantly_stuck(self):
        async def scenario():
            await repository.upsert_paper("p1", "T", "p1.pdf")
            pool = await repository.get_pool()
            await pool.execute("UPDATE papers SET status='failed', created_at = now() - interval '2 hours'")
            await repository.upsert_paper("p1", "T", "p1.pdf", status="processing")
            return await pool.fetchval("SELECT now() - created_at < interval '1 minute' FROM papers")

        assert run(scenario) is True

    def test_ping_runs_select_1(self):
        async def scenario():
            await repository.ping()
            return True

        assert run(scenario) is True
