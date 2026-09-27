# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Start here

**Before doing anything else, read `project-memory/STATE.md`, `project-memory/FIXED_BUGS.md`, and `project-memory/NEXT_STEPS.md`.** They're the living record of what's currently in progress, what's already fixed (and must not be re-broken the same way), and what's queued next — kept more current than this file. `project-memory/README.md` explains how they're meant to be read and updated.

## Project

ArXiv Agentic RAG: a Corrective-RAG (CRAG) question-answering system over scientific PDF papers. Pipeline: PDF → parse to Markdown → parent-child chunking → hybrid retrieval (dense pgvector + sparse Postgres full-text search, in Supabase Postgres) → rerank → LangGraph self-reflective agent (retrieve → grade → rewrite-if-insufficient → generate) → FastAPI backend + Streamlit frontend. Deployed on Railway (API) / Streamlit Cloud (UI).

The project is mid-upgrade from MVP to a production-grade portfolio piece (Phase 1 done, Phase 2 nearly done, see `docs/ROADMAP.md`). **Read `docs/ROADMAP.md` before making architectural changes** — it defines the current phase, the target architecture (migrating storage to Supabase Postgres + pgvector, embeddings to Gemini, BM25 to Postgres FTS), and which known bugs are "fix now" vs. "will be deleted in Phase 2, don't over-engineer a patch." For a system-level reference (data flow, diagrams, what state does/doesn't survive a redeploy), see `docs/Architecture.md`. Code comments and docstrings in this repo are written in Vietnamese (mixed with English technical terms) — follow that convention when editing existing files.

## Commands

```bash
# Install (requirements.txt is pinned with == — see its header comment
# before hand-editing a version)
pip install -r requirements.txt

# Run the API (from repo root; auto-reloads)
make run
# same as: uvicorn app.api.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs

# Run the Streamlit UI (separate process, calls the API over HTTP)
make ui   # same as: streamlit run streamlit_app.py

# Tests (36 unit tests, no network/API keys required — see tests/)
make test   # same as: python -m pytest tests/ -v

# Lint
make lint          # ruff check .
make fmt           # ruff check . --fix

# Ad-hoc module tests (each of these has an `if __name__ == "__main__":` block
# that exercises the module directly against live APIs / a sample PDF in data/
# — different from the tests/ suite, which is network-free)
python app/ingestion/parser.py
python app/ingestion/chunker.py
python app/llm/llm_factory.py
python app/agent/rag_graph.py

# Docker
make docker-build   # same as: docker build -t arxiv-rag .
make docker-run     # same as: docker run -p 8000:8000 --env-file .env arxiv-rag
```

CI (`.github/workflows/ci.yml`) runs `ruff check .` + `pytest tests/` on every push/PR to `main`. `pyproject.toml` holds the ruff/pytest config; note the `ignore` list there documents *why* `E402`/`B904`/`B008` are off (repo-wide conventions, not oversights) — read it before "fixing" one of those as a drive-by.

Config comes from `.env` (see `.env.example` for required keys: `DATABASE_URL` (Supabase Session pooler URI), `GROQ_API_KEY`, `GEMINI_API_KEY`, `COHERE_API_KEY`, `HF_TOKEN`). `app/config.py` loads it via `pydantic-settings`; import `from app.config import settings` rather than reading env vars directly.

## Architecture

### Ingestion pipeline (`app/ingestion/`)
`parser.py` → `chunker.py`, invoked together via `process_paper_ingestion()` in `chunker.py`.
- `parser.parse_pdf_to_markdown()`: PyMuPDF4LLM with a raw-`fitz` fallback if it fails (e.g. OOM on the Railway free tier). Page-chunk output is joined into a single Markdown string with `<!-- page:N -->` markers, which `chunker.create_child_chunks()` consumes (see below). The raw-`fitz` fallback emits no markers.
- `chunker.split_parent_sections()`: regex-based heading detection (Markdown `#`, bold `**Title**`, or Roman/decimal numbered IEEE-style headings) splits the document into `ParentSection`s.
- `chunker.create_child_chunks()`: sliding-window split of each section into `ChildChunk`s (`settings.chunk_size`/`chunk_overlap`, default 800/150 chars), snapping cut points to paragraph → sentence → word boundaries via `_find_split_point()`. It strips the `<!-- page:N -->` markers out first (they must never reach embedded/generated text) and fills `ChildChunk.page_num` (page of the chunk's first char), `char_start`/`char_end` (offsets in the marker-stripped section text) and `level` (always 0 for now). The page in effect is carried **across** section boundaries — a marker usually lands at the end of the previous section, just before the next heading — so every chunk after the document's first marker gets a real page (181/181 on `data/sample_cortexODE.pdf`). `page_num=None` means only "no markers anywhere" or "before the first marker"; never default it to 1.
- `ParentSection`s are persisted to the Postgres `sections` table and chunks link to them via `section_pk`, but "small-to-big" retrieval (expanding a matched chunk back to its full section) is not implemented yet.
- `save_chunks_to_file`/`load_chunks_from_file` (`data/chunks_cache/`) still exist but the upload path no longer uses them — every upload re-parses (the cache never stored `ParentSection`s).

### Indexing / retrieval (`app/indexing/`, `app/storage/repository.py`)
Phase 1's ChromaDB/BM25 stack (`app/indexing/vector_store.py`, `bm25_store.py`, `hybrid_retriever.py`) has been fully deleted — Postgres/pgvector is now the only retrieval path, not just the recommended one. If you're looking for that history (why it was designed that way, why it was replaced), see `project-memory/FIXED_BUGS.md` and `docs/Notebook.md` mục 4; don't expect those files to exist on disk anymore.
- `app/storage/repository.py::hybrid_search()`: runs dense search (pgvector cosine distance `<=>`, backed by an HNSW index) and sparse search (Postgres full-text search via `websearch_to_tsquery`/`ts_rank_cd`, a GIN index on the generated `tsvector` column) concurrently with `asyncio.gather()`, then fuses the two ranked lists with `reciprocal_rank_fusion()` (`k=60`, moved into this same file — it's data-source agnostic, so reusing it as-is needed no changes). Isolation between papers is a plain `WHERE paper_id = $1` — no metadata-filter workaround needed since Postgres has real per-row filtering. There's no separate retriever class or per-request store construction anymore; `hybrid_search()` is a plain async function, top-k straight into the reranker.
- `reranker.py`: `RerankerManager` picks Cohere Rerank (`rerank-english-v3.0`) if `COHERE_API_KEY` is set, otherwise falls back to a local `sentence-transformers` CrossEncoder (`ms-marco-MiniLM-L-6-v2`, `max_length=512`). Don't pre-truncate chunk text by character count before handing it to the CrossEncoder — let the tokenizer's own `max_length` truncation handle it (a previous bug did character-truncation to 512 chars, discarding most of an 800-char chunk).

### Agent (`app/agent/rag_graph.py`)
LangGraph `StateGraph` over `AgentState` (question, paper_id, retrieved_chunks, grade, rewrite_count, answer, messages). Flow: `retrieve → grade → (rewrite → retrieve)* → generate`, capped at `MAX_REWRITES = 2`. `grade_node` does a single whole-batch yes/no LLM call over all retrieved chunks (not per-document). Conversation memory uses `AsyncPostgresSaver` (`langgraph-checkpoint-postgres`), keyed by `thread_id`, in the same Supabase Postgres DB as papers/chunks — history survives restarts and Railway redeploys. It has its own `psycopg_pool.AsyncConnectionPool(min_size=1, max_size=1)` (the library only supports `psycopg`, not the `asyncpg` pool in `repository.py`), which reconnects if the connection drops; keep `max_size=1` so the total DB connection budget stays at 6 (5 asyncpg + 1). The graph and pool are built lazily on the first `ask()` call under an `asyncio.Lock`, so a bad `DATABASE_URL` shows up on the first `/ask`, not at startup. There is deliberately no broad `except Exception` fallback around checkpointer setup — the old SQLite version silently fell back to in-memory `MemorySaver` and lost chat history (`project-memory/FIXED_BUGS.md` #7); don't reintroduce that. The single public entry point other modules should use is `ask(question, paper_id, thread_id)` — don't call the graph nodes directly.

### LLM factory (`app/llm/llm_factory.py`)
`get_llm(provider=None, temperature=0.2, max_tokens=5096)` is the only way other modules should construct an LLM — never import `ChatGroq`/`ChatGoogleGenerativeAI`/`ChatOllama` directly elsewhere. Provider auto-detect order: Groq → Gemini → Ollama, based on which API key is set in `.env`. When Groq is auto-selected and `GEMINI_API_KEY` is also present, the returned LLM is wrapped with `.with_fallbacks([gemini_llm])` so a Groq runtime failure (rate limit, decommissioned model, timeout) transparently retries on Gemini. `get_llm()` and the internal Groq model-picker (`_pick_best_groq_model`, which calls the Groq API to pick the best currently-available model from a hardcoded preference list) are both `@lru_cache`d — do not add per-call state that would need to vary across calls without also reconsidering the cache.

### API (`app/api/`)
FastAPI app in `main.py`, all routes in `routes.py` under prefix `/api/v1` (`/health`, `/papers`, `POST /upload`, `POST /ask`). Also `GET /papers/{paper_id}/status` and `DELETE /papers/{paper_id}`. Paper metadata lives in the Postgres `papers` table via `app/storage/repository.py`. `/upload` dedups by sha256 of the file content: if the same bytes are already `ready`, it returns `200` with the existing paper (original `paper_id`) and does no work; otherwise it saves `data/{paper_id}.pdf` (never the client's filename — `FIXED_BUGS.md` #12), creates the row as `processing`, returns `202`, and parses/embeds/indexes in `BackgroundTasks`; clients poll the status route.

### Frontend (`streamlit_app.py`)
Single-file Streamlit app. Resolves the API base URL via `_resolve_api_base()`: `API_BASE` env var → `st.secrets["API_BASE"]` → local `http://127.0.0.1:8000` fallback. Session state tracks `chat_history`, `thread_id`, `selected_paper`; changing the selected paper or clicking "Xóa lịch sử chat" issues a fresh `thread_id`.

### Config (`app/config.py`)
`Settings` (pydantic-settings) loads `.env` and also sets `HF_HOME`/`OLLAMA_MODELS` env vars at import time to redirect model caches into `cache/` inside the repo — importing `app.config` has this side effect, so it should generally be imported before other libraries that read those env vars (transformers, huggingface_hub, ollama).
