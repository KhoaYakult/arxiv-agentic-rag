"""
app/storage/repository.py
===========================
Postgres (Supabase) repository layer - Phase 2.

Thay the 3 thu rai rac cua Phase 1:
  - data/papers_registry.json (_load_registry/_save_registry trong routes.py)
  - app/indexing/vector_store.py (VectorStoreManager, ChromaDB)
  - app/indexing/bm25_store.py (BM25StoreManager, pickle)

CHUA duoc wire vao routes.py - vector_store.py/bm25_store.py van la pipeline
dang chay that, da verify end-to-end (xem project-memory/STATE.md). Chi
chua CRUD cho papers/sections/chunks; ham tim kiem (hybrid search) se viet
sau khi co Postgres that de test - viet mo (blind) mot SQL search phuc tap
ma khong chay thu duoc thi rui ro sai cao hon loi ich.

Truoc khi dung module nay: chay db/schema.sql qua Supabase SQL Editor.
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import asyncpg
from pgvector.asyncpg import register_vector

from app.config import settings
from app.ingestion.chunker import ChildChunk, ParentSection

_pool: asyncpg.Pool | None = None


async def _register_vector_codec(conn: asyncpg.Connection) -> None:
    """Day asyncpg biet convert Python list[float] <-> Postgres `vector` type.
    Luu y: doc lai (SELECT) cot embedding se tra ve pgvector.Vector, khong
    phai list[float] thuan - goi .to_list() khi can list thuan tuy."""
    await register_vector(conn)


async def get_pool() -> asyncpg.Pool:
    """Lazy singleton connection pool - goi 1 lan, tai su dung xuyen suot app."""
    global _pool
    if _pool is None:
        if not settings.database_url:
            raise ValueError(
                "DATABASE_URL chua duoc cau hinh trong .env! "
                "Lay connection string tu Supabase: Project -> Connect -> URI."
            )
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=1,
            max_size=5,
            init=_register_vector_codec,
        )
    return _pool


async def close_pool() -> None:
    """Dong pool luc app shutdown (goi trong FastAPI lifespan)."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ─────────────────────────────────────────────────────────────────────────────
# PAPERS
# ─────────────────────────────────────────────────────────────────────────────

async def upsert_paper(
    paper_id: str,
    title: str,
    filename: str,
    file_hash: str | None = None,
    num_pages: int | None = None,
    status: str = "processing",
) -> None:
    """Tao moi hoac cap nhat 1 paper (upsert de ho tro re-upload cung paper_id)."""
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO papers (paper_id, title, filename, file_hash, num_pages, status)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (paper_id) DO UPDATE SET
            title = EXCLUDED.title,
            filename = EXCLUDED.filename,
            file_hash = EXCLUDED.file_hash,
            num_pages = EXCLUDED.num_pages,
            status = EXCLUDED.status
        """,
        paper_id, title, filename, file_hash, num_pages, status,
    )


async def set_paper_status(paper_id: str, status: str, num_chunks: int | None = None) -> None:
    """Cap nhat trang thai xu ly - dung cho /upload BackgroundTasks polling (viec sau)."""
    pool = await get_pool()
    if num_chunks is None:
        await pool.execute("UPDATE papers SET status = $2 WHERE paper_id = $1", paper_id, status)
    else:
        await pool.execute(
            "UPDATE papers SET status = $2, num_chunks = $3 WHERE paper_id = $1",
            paper_id, status, num_chunks,
        )


async def get_paper_by_hash(file_hash: str) -> dict | None:
    """Dung de dedup upload: file da parse roi thi khong lam lai."""
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM papers WHERE file_hash = $1", file_hash)
    return dict(row) if row else None


async def get_paper(paper_id: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM papers WHERE paper_id = $1", paper_id)
    return dict(row) if row else None


async def list_papers() -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch("SELECT * FROM papers ORDER BY created_at DESC")
    return [dict(r) for r in rows]


async def delete_paper(paper_id: str) -> None:
    """Xoa 1 paper - CASCADE tu xoa sections/chunks/paper_cards lien quan (schema.sql)."""
    pool = await get_pool()
    await pool.execute("DELETE FROM papers WHERE paper_id = $1", paper_id)


# ─────────────────────────────────────────────────────────────────────────────
# SECTIONS
# ─────────────────────────────────────────────────────────────────────────────

async def insert_sections(paper_id: str, sections: list[ParentSection]) -> dict[str, int]:
    """
    Ghi danh sach ParentSection, tra ve map {section_id (string, vd "sec_0") ->
    id (int, primary key trong Postgres)} de insert_chunks() dung lam FK.

    Day la lan dau ParentSection thuc su duoc luu lai (Phase 1 tao ra roi vut
    di ngay - xem project-memory/FIXED_BUGS.md).
    """
    if not sections:
        return {}

    pool = await get_pool()
    section_pk_map: dict[str, int] = {}
    async with pool.acquire() as conn, conn.transaction():
        for sec in sections:
            pk = await conn.fetchval(
                """
                INSERT INTO sections (paper_id, section_id, name, text)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (paper_id, section_id) DO UPDATE SET
                    name = EXCLUDED.name, text = EXCLUDED.text
                RETURNING id
                """,
                paper_id, sec.section_id, sec.section_name, sec.text,
            )
            section_pk_map[sec.section_id] = pk
    return section_pk_map


# ─────────────────────────────────────────────────────────────────────────────
# CHUNKS
# ─────────────────────────────────────────────────────────────────────────────

async def insert_chunks(
    paper_id: str,
    chunks: list[ChildChunk],
    embeddings: list[list[float]],
    section_pk_map: dict[str, int],
) -> None:
    """
    Ghi ChildChunk + embedding trong 1 transaction (fts tu sinh boi Postgres
    qua GENERATED ALWAYS, khong can truyen). Day la buoc thay the 2 lan ghi
    tach roi cua Phase 1 (add_child_chunks() vao ChromaDB + build_index() vao
    BM25 pickle rieng) - gop lam 1 de khong con nguy co lech du lieu giua
    dense va sparse index (bug #6 cua Phase 1).

    ChildChunk hien tai (Phase 1) CHUA co page_num/char_start/char_end - cac
    cot nay se NULL cho den khi chunker.py duoc nang cap de page-aware (viec
    rieng, xem project-memory/NEXT_STEPS.md truoc khi gia dinh da co du lieu).
    """
    if not chunks:
        return
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"So chunks ({len(chunks)}) khong khop so embeddings ({len(embeddings)})"
        )

    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            section_pk = section_pk_map.get(chunk.parent_section_id)
            await conn.execute(
                """
                INSERT INTO chunks (chunk_id, paper_id, section_pk, text, is_table, embedding)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    text = EXCLUDED.text,
                    is_table = EXCLUDED.is_table,
                    embedding = EXCLUDED.embedding
                """,
                chunk.chunk_id, paper_id, section_pk, chunk.text, chunk.is_table, embedding,
            )
