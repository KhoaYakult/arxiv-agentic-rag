# Architecture

System reference for ArXiv Agentic RAG. For the upgrade plan and rationale behind pending architectural changes, see [`ROADMAP.md`](ROADMAP.md). For contributor conventions and gotchas, see [`../CLAUDE.md`](../CLAUDE.md). For current in-progress state, see [`../project-memory/STATE.md`](../project-memory/STATE.md).

> **Phase 2 cutover done (2026-09-20):** storage moved from ChromaDB + BM25 pickles + a JSON registry to a single Supabase Postgres (pgvector + full-text search). This doc describes the **current** (post-cutover) architecture. Phase 1's `app/indexing/vector_store.py`, `bm25_store.py`, and `hybrid_retriever.py` have since been deleted outright (2026-09-27, see *Layers* below). Chat history (LangGraph checkpointer) lives in the same Postgres DB too.

## Overview

```mermaid
flowchart TD
    subgraph UI["Frontend"]
        ST["streamlit_app.py"]
    end

    subgraph API["app/api/"]
        MAIN["main.py (FastAPI app, CORS)"]
        ROUTES["routes.py (/health /papers /upload /ask)"]
    end

    subgraph ING["app/ingestion/"]
        PARSER["parser.py\nparse_pdf_to_markdown()"]
        CHUNKER["chunker.py\nsplit_parent_sections()\ncreate_child_chunks()"]
    end

    subgraph EMB["app/indexing/embeddings.py"]
        GEMINI["GeminiEmbeddingProvider\n768-dim, asymmetric query/doc"]
    end

    subgraph STORE["app/storage/repository.py"]
        POOL["asyncpg pool (pgvector codec)"]
        CRUD["upsert_paper / insert_sections / insert_chunks"]
        SEARCH["hybrid_search()\ndense (pgvector) + sparse (FTS) + RRF"]
    end

    subgraph PG["Supabase Postgres"]
        TABLES[("papers / sections / chunks / paper_cards")]
    end

    subgraph AGENT["app/agent/rag_graph.py (async)"]
        GRAPH["LangGraph StateGraph\nretrieve -> grade -> rewrite? -> generate"]
    end

    subgraph LLM["app/llm/"]
        FACTORY["llm_factory.get_llm()\nGroq -> Gemini fallback"]
        PROMPTS["prompt_templates.py"]
    end

    ST -->|HTTP| MAIN --> ROUTES
    ROUTES -->|POST /upload| PARSER --> CHUNKER
    CHUNKER --> GEMINI --> CRUD
    ROUTES --> CRUD
    CRUD --> POOL --> TABLES
    ROUTES -->|POST /ask| GRAPH
    GRAPH --> GEMINI
    GRAPH --> SEARCH
    SEARCH --> POOL
    GRAPH --> FACTORY --> PROMPTS
```

## Data flow

### Upload path (`POST /api/v1/upload`)

1. `routes.upload_paper()` hashes the upload (sha256) and, if a paper with the same content is already `ready`, returns **`200`** with that existing paper (its original `paper_id`, possibly different from the one supplied) without re-parsing. Otherwise it saves the raw PDF to `data/{paper_id}.pdf` (slugified from the filename unless a `paper_id` is supplied), creates the `papers` row with `status="processing"`, returns **`202`** immediately, and runs steps 2-5 below in a `BackgroundTasks` job. Clients poll `GET /papers/{paper_id}/status`.
2. `chunker.process_paper_ingestion()` orchestrates:
   - `parser.parse_pdf_to_markdown()` — PyMuPDF4LLM (`page_chunks=True`) with a raw-`fitz` fallback if it OOMs. Output is a single Markdown string with `<!-- page:N -->` markers between pages (the raw-`fitz` fallback emits no markers).
   - `chunker.split_parent_sections()` — regex heading detection splits the Markdown into `ParentSection` objects (`section_id`, `section_name`, `text`).
   - `chunker.create_child_chunks()` — strips the page markers out of each section's text (they never reach the embedded/generated text) and sliding-window splits it into `ChildChunk` objects (`chunk_id`, `parent_section_id`, `parent_section_name`, `paper_id`, `text`, `is_table`, `page_num`, `char_start`, `char_end`, `level`), snapping cuts to paragraph → sentence → word boundaries. `page_num` is the page of the chunk's first character; the page in effect is carried across section boundaries (a marker usually lands at the end of the *previous* section, just before the next heading), so every chunk after the document's first marker gets a real page — 181/181 chunks on `data/sample_cortexODE.pdf`. `page_num` is `NULL` only when the document has no markers at all (fitz fallback) or for content before the first marker — never a guessed page 1. `char_start`/`char_end` are offsets into the marker-stripped section text.
   - The Phase 1 JSON chunk cache (`load_chunks_from_file`) is **no longer used** here — it only ever cached `ChildChunk`s, never `ParentSection`s, so a cache hit would silently produce empty sections now that sections are actually persisted. Every upload re-parses.
3. `embeddings.get_embedding_provider().embed_documents()` embeds every chunk's text via the Gemini API (`task_type=RETRIEVAL_DOCUMENT`, 768-dim). Batches of ≤100 texts with a **61-second sleep between batches** — Gemini's free-tier quota is metered per embedded item per minute, not per HTTP call, so a 182-chunk paper takes noticeably longer than a 90-chunk one to upload (see `project-memory/FIXED_BUGS.md` #11).
4. `repository.upsert_paper()` writes the `papers` row (`status="processing"` first, then `"ready"` once steps 5-6 succeed), `repository.insert_sections()` writes `ParentSection`s and returns a `{section_id: postgres_pk}` map, `repository.insert_chunks()` writes `ChildChunk`s + their embeddings using that map for the `section_pk` foreign key.
5. Postgres auto-generates the `fts` (full-text search) column on `chunks` via `GENERATED ALWAYS AS (to_tsvector(...))` — no separate sparse-index write step, which is what eliminates the Phase 1 class of bug where the dense and sparse indexes could drift out of sync (`FIXED_BUGS.md` #6).

**Note:** steps 2-5 run in the background — `/upload` returns `202` right away, and failures are caught and recorded as `papers.status='failed'` rather than raised. A large paper can take minutes to reach `ready` because of the rate-limit cooldown in step 3.

### Query path (`POST /api/v1/ask`)

1. `routes.ask_agent()` checks the paper exists via `repository.get_paper()`, then calls `rag_graph.ask(question, paper_id, thread_id)` — the only public entry point into the agent. Both this route and the whole graph are `async`.
2. `rag_graph.py` runs a LangGraph `StateGraph` over `AgentState`:

   ```
   retrieve -> grade -> [insufficient?] -> rewrite -> retrieve -> grade -> ...
                      -> [sufficient, or MAX_REWRITES=2 hit] -> generate -> END
   ```

   - `retrieve_node` (async): embeds the question (`embed_query`, `task_type=RETRIEVAL_QUERY`), calls `repository.hybrid_search()` — dense (pgvector cosine `<=>`, backed by an HNSW index) and sparse (Postgres `websearch_to_tsquery` + `ts_rank_cd`) run concurrently via `asyncio.gather`, fused by the same `reciprocal_rank_fusion()` function from Phase 1 (reused as-is — the algorithm doesn't care what produced the two ranked lists), then reranked (Cohere if `COHERE_API_KEY` is set, else a local CrossEncoder) down to top-5.
   - `grade_node`, `rewrite_node`, `generate_node`: same logic as Phase 1, just `async def` now with `await chain.ainvoke(...)` instead of `chain.invoke(...)` — LangChain runnables support both natively, so the prompts/templates didn't need to change.
3. Conversation memory is `AsyncPostgresSaver` (`langgraph-checkpoint-postgres`), keyed by `thread_id`, stored in the **same Supabase Postgres DB** (`checkpoints`/`checkpoint_writes`/`checkpoint_blobs` tables, created by `saver.setup()`), so history survives restarts and redeploys. It uses its own `psycopg_pool.AsyncConnectionPool(min_size=1, max_size=1)` — `langgraph-checkpoint-postgres` only supports the `psycopg` driver, not `asyncpg` — which reconnects on its own if the connection drops (total DB connections: 5 asyncpg + 1 checkpointer = 6). The graph (and the pool) is built lazily on the first `ask()` call (`_get_rag_app()`, guarded by an `asyncio.Lock` so concurrent first requests build it once), because compiling the graph needs an awaited connection that can't happen at plain module-import time. Consequence: a bad `DATABASE_URL` for the checkpointer surfaces on the first `/ask`, not at startup, so `/health` stays green. `close_checkpointer()` closes the pool in the FastAPI `lifespan` shutdown.
4. `routes.ask_agent()` reads `result["retrieved_chunks"]` to populate the `sources` field of the response (each item carries `chunk_id`, `parent_section_name`, `text`, `page_num`).

**Why async was mandatory, not a style choice:** `asyncpg` (the Postgres driver) only supports async. Bridging a single sync node with `asyncio.run()` would have broken `repository.py`'s cached connection pool across calls — a pool is bound to the event loop that created it, and `asyncio.run()` creates and tears down a new loop every call.

## Layers

| Layer | Files | Responsibility |
|---|---|---|
| Ingestion | `app/ingestion/parser.py`, `chunker.py` | PDF → Markdown → `ParentSection`/`ChildChunk` |
| Embedding | `app/indexing/embeddings.py` | `GeminiEmbeddingProvider` (768-dim, asymmetric query/document, self-throttled) |
| Storage | `app/storage/repository.py` | Postgres connection pool, CRUD for papers/sections/chunks, `hybrid_search()` |
| Reranking | `app/indexing/reranker.py` | `RerankerManager` (Cohere / local CrossEncoder) — unchanged from Phase 1, data-source agnostic |
| Agent | `app/agent/rag_graph.py` | LangGraph Corrective-RAG state machine (async) |
| LLM | `app/llm/llm_factory.py`, `prompt_templates.py` | Provider-agnostic LLM construction + prompts |
| API | `app/api/main.py`, `routes.py`, `schemas.py` | FastAPI app, HTTP contracts |
| Frontend | `streamlit_app.py` | Chat UI, calls the API over HTTP |
| Config | `app/config.py` | `pydantic-settings` loaded from `.env`; also redirects `HF_HOME`/`OLLAMA_MODELS` into `cache/` on import |

Phase 1's `app/indexing/vector_store.py`, `bm25_store.py`, and `hybrid_retriever.py` (ChromaDB/BM25 pipeline) are **permanently deleted**, not just unused — the rollback safety net they were kept for turned out not to be needed. See `project-memory/FIXED_BUGS.md` and git history if you need to see the old code.

## Key data structures

```python
# app/ingestion/chunker.py — page_num is populated from the parser's
# <!-- page:N --> markers (NULL only with no markers / before the first one);
# char_start/char_end are offsets into the marker-stripped section text;
# level is always 0 until RAPTOR summary nodes (Phase 5) exist
@dataclass
class ParentSection:
    section_id: str
    section_name: str
    text: str

@dataclass
class ChildChunk:
    chunk_id: str
    parent_section_id: str
    parent_section_name: str
    paper_id: str
    text: str
    is_table: bool = False
    page_num: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    level: int = 0

# app/agent/rag_graph.py
class AgentState(TypedDict):
    question: str
    paper_id: str
    retrieved_chunks: list       # list[dict], not LangChain Document
    grade: str                   # "yes" | "no"
    rewrite_count: int
    answer: str
    messages: Annotated[list, add_messages]
```

```sql
-- db/schema.sql (Supabase). See the file itself for the full DDL with
-- indexes; this is the shape, not the exact statements.
papers(paper_id PK, title, authors, arxiv_id, filename, file_hash UNIQUE,
       num_pages, num_chunks, status, created_at)
sections(id PK, paper_id FK, section_id, name, level, text, page_start, page_end)
chunks(id PK, chunk_id UNIQUE, paper_id FK, section_pk FK, text,
       page_num, char_start, char_end, is_table, level,
       embedding vector(768),               -- HNSW index, cosine ops
       fts tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED)  -- GIN index
paper_cards(paper_id PK/FK, summary, embedding vector(768))  -- Phase 4, not used yet
```

## State & persistence (current)

| What | Where | Survives redeploy? |
|---|---|---|
| Uploaded PDFs | `data/*.pdf` | No (ephemeral disk on Railway) |
| Papers, sections, chunks, embeddings | **Supabase Postgres** | **Yes** |
| Chat history | **Supabase Postgres** (`AsyncPostgresSaver` checkpoint tables) | **Yes** |
| Model download cache | `cache/huggingface/` | No (only used by the now-dead `sentence-transformers` CrossEncoder fallback path in `reranker.py`) |

The core data (papers/sections/chunks/embeddings) and chat history now survive a redeploy — this was the top item in `ROADMAP.md` Phase 2 and is done. Only the uploaded PDF files themselves are still on ephemeral disk (they're not needed after indexing).

## Deployment topology

- **API**: Railway, single Docker container (`Dockerfile`), FastAPI on `$PORT` (defaults to 8000 locally). **Not yet redeployed to Railway with the Phase 2 code** — verified so far via local `uvicorn` + a real Supabase project, not the production environment.
- **UI**: Streamlit Community Cloud, separate deploy, talks to the API over HTTP (`API_BASE` resolved via env var → `st.secrets` → local fallback in `streamlit_app.py`).
- **Database**: Supabase Postgres, connected via the **Session pooler** (`aws-0-<region>.pooler.supabase.com`) — not the "Direct connection" host, which is IPv6-only and unreachable from networks without IPv6 egress (`project-memory/FIXED_BUGS.md` #8).
- **External APIs**: Groq (primary LLM), Gemini (fallback LLM + embeddings), Cohere (rerank, optional).

## Known gaps

See `ROADMAP.md` Phase 2 checklist and `project-memory/NEXT_STEPS.md` for the full, currently-accurate list. Highlights relevant to anyone reading this file for the first time:

- `page_num` is derived from marker strings in the parser's Markdown output, not from a structured per-page parser result — the `parser.py` per-page offset refactor is still open.
- `char_start`/`char_end` are stored but not yet used (small-to-big expansion to the parent section isn't implemented).
- Not yet redeployed to Railway — only verified locally against the real Supabase project.
