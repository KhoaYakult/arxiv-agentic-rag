"""
app/storage/repository.py
===========================
Postgres (Supabase) repository layer - Phase 2.

Thay the 3 thu rai rac cua Phase 1:
  - data/papers_registry.json (_load_registry/_save_registry trong routes.py)
  - app/indexing/vector_store.py (VectorStoreManager, ChromaDB)
  - app/indexing/bm25_store.py (BM25StoreManager, pickle)

CHUA duoc wire vao routes.py - vector_store.py/bm25_store.py van la pipeline
dang chay that, da verify end-to-end (xem project-memory/STATE.md).

Truoc khi dung module nay: chay db/schema.sql qua Supabase SQL Editor.
"""

import asyncio
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

    QUAN TRONG: Supabase cai extension pgvector vao schema `extensions`,
    KHONG PHAI `public` (khac mac dinh cua thu vien pgvector - register_vector()
    mac dinh schema='public'). DDL trong db/schema.sql van chay duoc vi
    search_path cua Supabase da bao gom `extensions`, nhung ham nay lookup
    type theo schema chi dinh ro rang nen phai truyen tay - thieu dong nay se
    loi "unknown type: public.vector" du extension da bat va bang da tao xong.

    Luu y: doc lai (SELECT) cot embedding se tra ve pgvector.Vector, khong
    phai list[float] thuan - goi .to_list() khi can list thuan tuy."""
    await register_vector(conn, schema="extensions")


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
    """Chi tra paper status='ready'. Tu khi /upload chay nen (BackgroundTasks),
    paper 'processing'/'failed' se ton tai that trong bang mot khoang thoi
    gian - loc o day de khong cho UI chon phai paper chua index xong."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM papers WHERE status = 'ready' ORDER BY created_at DESC"
    )
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

    ChildChunk gio da co page_num/char_start/char_end/level (chunker.py da
    page-aware, xem app/ingestion/chunker.py::create_child_chunks) - cac cot
    nay chi con NULL neu parser.py roi vao nhanh fallback fitz thuan (khong
    chen duoc marker trang).
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
                INSERT INTO chunks (
                    chunk_id, paper_id, section_pk, text, is_table, embedding,
                    page_num, char_start, char_end, level
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    text = EXCLUDED.text,
                    is_table = EXCLUDED.is_table,
                    embedding = EXCLUDED.embedding,
                    page_num = EXCLUDED.page_num,
                    char_start = EXCLUDED.char_start,
                    char_end = EXCLUDED.char_end,
                    level = EXCLUDED.level
                """,
                chunk.chunk_id, paper_id, section_pk, chunk.text, chunk.is_table, embedding,
                chunk.page_num, chunk.char_start, chunk.char_end, chunk.level,
            )


# ─────────────────────────────────────────────────────────────────────────────
# HYBRID SEARCH - dense (pgvector) + sparse (Postgres FTS) + RRF
#
# Tai su dung reciprocal_rank_fusion() da test trong Phase 1
# (app/indexing/hybrid_retriever.py) thay vi viet lai - ham do khong quan tam
# nguon goc ranking (BM25 hay Postgres FTS), chi can dict co key
# {chunk_id, dense_rank} hoac {chunk_id, bm25_rank}. Giu nguyen ten key
# "bm25_rank" du gio la Postgres FTS (khong phai BM25 that) de tai su dung
# ham fusion khong sua doi - fusion la thuat toan generic tren 2 danh sach
# rank, khong phu thuoc cach tinh diem cu the.
# ─────────────────────────────────────────────────────────────────────────────

_DENSE_SEARCH_SQL = """
    SELECT c.chunk_id, c.paper_id, c.text, c.is_table, c.page_num,
           COALESCE(s.name, 'Unknown section') AS parent_section_name
    FROM chunks c
    LEFT JOIN sections s ON s.id = c.section_pk
    WHERE c.paper_id = $1
    ORDER BY c.embedding <=> $2
    LIMIT $3
"""

_SPARSE_SEARCH_SQL = """
    SELECT c.chunk_id, c.paper_id, c.text, c.is_table, c.page_num,
           COALESCE(s.name, 'Unknown section') AS parent_section_name
    FROM chunks c
    LEFT JOIN sections s ON s.id = c.section_pk
    WHERE c.paper_id = $1 AND c.fts @@ websearch_to_tsquery('english', $2)
    ORDER BY ts_rank_cd(c.fts, websearch_to_tsquery('english', $2)) DESC
    LIMIT $3
"""


async def dense_search(paper_id: str, query_embedding: list[float], top_k: int = 20) -> list[dict]:
    """Tim theo ngu nghia bang pgvector cosine distance (`<=>`, can HNSW index)."""
    pool = await get_pool()
    rows = await pool.fetch(_DENSE_SEARCH_SQL, paper_id, query_embedding, top_k)
    return [{**dict(r), "dense_rank": i} for i, r in enumerate(rows, start=1)]


async def sparse_search(paper_id: str, query_text: str, top_k: int = 20) -> list[dict]:
    """Tim theo tu khoa bang Postgres full-text search (thay `rank_bm25` cua Phase 1)."""
    pool = await get_pool()
    rows = await pool.fetch(_SPARSE_SEARCH_SQL, paper_id, query_text, top_k)
    return [{**dict(r), "bm25_rank": i} for i, r in enumerate(rows, start=1)]


async def hybrid_search(
    paper_id: str,
    query_text: str,
    query_embedding: list[float],
    top_k: int = 20,
) -> list[dict]:
    """
    Dense + sparse chay song song (asyncio.gather), gop bang RRF. Tra ve
    top_k ung vien da fuse - chua rerank (buoc rerank van la
    app/indexing/reranker.py, khong doi, khong quan tam data tu dau ra).
    """
    from app.indexing.hybrid_retriever import reciprocal_rank_fusion

    dense_results, sparse_results = await asyncio.gather(
        dense_search(paper_id, query_embedding, top_k),
        sparse_search(paper_id, query_text, top_k),
    )
    fused = reciprocal_rank_fusion(dense_results, sparse_results)
    return fused[:top_k]
