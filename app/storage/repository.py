"""
app/storage/repository.py
===========================
Postgres (Supabase) repository layer - nguon su that duy nhat cho papers/
sections/chunks, thay the 3 thu rai rac cua Phase 1 (data/papers_registry.json,
ChromaDB qua app/indexing/vector_store.py, BM25 pickle qua
app/indexing/bm25_store.py - ca 3 file/co che nay da bi xoa, xem
project-memory/FIXED_BUGS.md va git history neu can xem lai).

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


async def clear_stale_file_hash(paper_id: str) -> None:
    """
    Go claim file_hash cua 1 paper dang 'processing'/'failed' (KHONG PHAI
    'ready') - goi truoc khi /upload ghi 1 row moi cung file_hash do, vi
    `papers.file_hash` la UNIQUE tren TOAN BANG (db/schema.sql), khong scope
    rieng theo status='ready'. Neu khong go truoc, insert row moi se dam vao
    asyncpg.exceptions.UniqueViolationError (bug tim thay khi review Task 3
    dedup: "fresh upload" fallback cho paper cu 'failed' bi crash 500 thay vi
    thanh cong, xem project-memory/FIXED_BUGS.md).

    Dieu kien `status != 'ready'` trong WHERE la an toan-kep (defense in
    depth): neu paper vua chuyen sang 'ready' dung luc ham nay chay (race
    hiem), no se KHONG bi xoa file_hash - dung, vi khi do no dang giu 1 ban
    index that su, khong phai stale claim.
    """
    pool = await get_pool()
    await pool.execute(
        "UPDATE papers SET file_hash = NULL WHERE paper_id = $1 AND status != 'ready'",
        paper_id,
    )


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
# reciprocal_rank_fusion() song o day (chuyen tu app/indexing/hybrid_retriever.py,
# file da bi xoa cung Phase 1 - xem project-memory/FIXED_BUGS.md) vi day la noi
# duy nhat con goi no. Ham khong quan tam nguon goc ranking (BM25 hay Postgres
# FTS), chi can dict co key {chunk_id, dense_rank} hoac {chunk_id, bm25_rank}.
# Giu nguyen ten key "bm25_rank" du gio la Postgres FTS (khong phai BM25 that) -
# fusion la thuat toan generic tren 2 danh sach rank, khong phu thuoc cach tinh
# diem cu the.
# ─────────────────────────────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    dense_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """
    Reciprocal Rank Fusion (RRF): Gop 2 danh sach xep hang tu Dense va BM25
    thanh 1 danh sach thong nhat bang cong thuc:

        RRF_score(doc) = sum over each list: 1 / (k + rank_in_that_list)

    k = 60 la gia tri mac dinh tu bai bao goc cua RRF (Cormack et al., 2009).
    Gia tri nay giam thieu anh huong cua nhung vi tri hang dau qua cao.

    Args:
        dense_results: Ket qua tu Dense Vector Search (co key 'chunk_id', 'dense_rank').
        bm25_results:  Ket qua tu BM25 Search (co key 'chunk_id', 'bm25_rank').
        k: Hang so lam mo RRF (mac dinh 60).

    Returns:
        list[dict]: Danh sach da duoc gop va sap xep theo RRF score giam dan,
                    moi item co them 'rrf_score' va 'rrf_rank'.
    """
    rrf_scores: dict[str, float] = {}
    chunk_data: dict[str, dict] = {}

    for item in dense_results:
        cid = item["chunk_id"]
        rank = item["dense_rank"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank)
        chunk_data[cid] = item.copy()

    for item in bm25_results:
        cid = item["chunk_id"]
        rank = item["bm25_rank"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank)
        if cid not in chunk_data:
            chunk_data[cid] = item.copy()

    sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)

    results = []
    for rank, cid in enumerate(sorted_ids, 1):
        item = chunk_data[cid]
        item["rrf_score"] = round(rrf_scores[cid], 6)
        item["rrf_rank"] = rank
        results.append(item)

    return results


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
    dense_results, sparse_results = await asyncio.gather(
        dense_search(paper_id, query_embedding, top_k),
        sparse_search(paper_id, query_text, top_k),
    )
    fused = reciprocal_rank_fusion(dense_results, sparse_results)
    return fused[:top_k]
