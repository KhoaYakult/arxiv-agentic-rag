-- ArXiv Agentic RAG - Phase 2 schema (Supabase Postgres + pgvector)
--
-- Chay 1 lan qua Supabase SQL Editor (Project -> SQL Editor -> New query -> paste -> Run).
-- Idempotent: dung IF NOT EXISTS xuyen suot, chay lai nhieu lan khong loi.
--
-- Xem docs/ROADMAP.md muc "Phase 2" de biet ly do cac quyet dinh (vi sao paper_id
-- la text PK thay vi UUID, vi sao chunks co ca embedding lan fts trong 1 bang, ...)

CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────────────────────────────────────────────────────────
-- PAPERS - thay the data/papers_registry.json
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS papers (
    paper_id    TEXT PRIMARY KEY,           -- slug, vd "cortex_ode_2023" - giu nguyen
                                             -- convention hien tai cua app (khong doi
                                             -- sang UUID de khoi phai sua moi cho dang
                                             -- dung paper_id lam string xuyen suot code)
    title       TEXT NOT NULL,
    authors     TEXT,
    arxiv_id    TEXT,
    filename    TEXT NOT NULL,
    file_hash   TEXT UNIQUE,                -- sha256 file PDF, dung de dedup upload
    num_pages   INTEGER,
    num_chunks  INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'processing'
                CHECK (status IN ('processing', 'ready', 'failed')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTIONS - ParentSection, thay the "duoc tao roi vut di" hien tai
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sections (
    id          BIGSERIAL PRIMARY KEY,
    paper_id    TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    section_id  TEXT NOT NULL,              -- vd "sec_0" - chi unique TRONG 1 paper,
                                             -- khong global-unique (giu nguyen convention
                                             -- cua chunker.py hien tai)
    name        TEXT NOT NULL,
    level       SMALLINT NOT NULL DEFAULT 0,
    text        TEXT NOT NULL,
    page_start  INTEGER,
    page_end    INTEGER,
    UNIQUE (paper_id, section_id)
);

CREATE INDEX IF NOT EXISTS sections_paper_id_idx ON sections (paper_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- CHUNKS - ChildChunk + dense vector + sparse FTS trong CUNG 1 bang.
-- Day la diem mau chot cua Phase 2: chunk, embedding, va sparse index duoc ghi
-- trong CUNG 1 transaction -> khong con class bug "BM25 mat du lieu paper cu"
-- (bug #6 cua Phase 1) vi khong con 2 store tach roi nhau nua.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS chunks (
    id          BIGSERIAL PRIMARY KEY,
    chunk_id    TEXT NOT NULL UNIQUE,       -- vd "{paper_id}_chk_3"
    paper_id    TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    section_pk  BIGINT REFERENCES sections(id) ON DELETE SET NULL,
    text        TEXT NOT NULL,
    page_num    INTEGER,
    char_start  INTEGER,
    char_end    INTEGER,
    is_table    BOOLEAN NOT NULL DEFAULT FALSE,
    level       SMALLINT NOT NULL DEFAULT 0,   -- 0 = leaf chunk thuong,
                                                -- >0 = RAPTOR summary node (Phase 5) -
                                                -- tai dung bang nay, KHONG tao bang moi
    embedding   vector(768),                   -- Gemini gemini-embedding-001, MRL truncate 768
    fts         tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);

CREATE INDEX IF NOT EXISTS chunks_paper_id_idx ON chunks (paper_id);
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_fts_gin_idx ON chunks USING gin (fts);

-- ─────────────────────────────────────────────────────────────────────────────
-- PAPER_CARDS - tom tat + embedding cap do paper, dung cho Phase 4 (multi-paper
-- routing: chon top-3 paper lien quan truoc khi retrieve chunk trong tung paper)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS paper_cards (
    paper_id    TEXT PRIMARY KEY REFERENCES papers(paper_id) ON DELETE CASCADE,
    summary     TEXT NOT NULL,
    embedding   vector(768)
);

CREATE INDEX IF NOT EXISTS paper_cards_embedding_hnsw_idx
    ON paper_cards USING hnsw (embedding vector_cosine_ops);

-- ─────────────────────────────────────────────────────────────────────────────
-- CHECKPOINTER (LangGraph AsyncPostgresSaver)
-- Khong khai bao bang o day - AsyncPostgresSaver tu tao bang rieng cua no
-- (checkpoints, checkpoint_writes, checkpoint_blobs) qua `await saver.setup()`
-- goi 1 lan luc app khoi dong. Xem app/agent/rag_graph.py khi cutover.
-- ─────────────────────────────────────────────────────────────────────────────
