# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

ArXiv Agentic RAG: a Corrective-RAG (CRAG) question-answering system over scientific PDF papers. Pipeline: PDF → parse to Markdown → parent-child chunking → hybrid retrieval (dense ChromaDB + sparse BM25) → rerank → LangGraph self-reflective agent (retrieve → grade → rewrite-if-insufficient → generate) → FastAPI backend + Streamlit frontend. Deployed on Railway (API) / Streamlit Cloud (UI).

The project is mid-upgrade from MVP to a production-grade portfolio piece (Phase 1 done, see `docs/ROADMAP.md`). **Read `docs/ROADMAP.md` before making architectural changes** — it defines the current phase, the target architecture (migrating storage to Supabase Postgres + pgvector, embeddings to Gemini, BM25 to Postgres FTS), and which known bugs are "fix now" vs. "will be deleted in Phase 2, don't over-engineer a patch." For a system-level reference (data flow, diagrams, what state does/doesn't survive a redeploy), see `docs/Architecture.md`. Code comments and docstrings in this repo are written in Vietnamese (mixed with English technical terms) — follow that convention when editing existing files.

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

# Tests (20 unit tests, no network/API keys required — see tests/)
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

Config comes from `.env` (see `.env.example` for required keys: `GROQ_API_KEY`, `GEMINI_API_KEY`, `COHERE_API_KEY`, `HF_TOKEN`). `app/config.py` loads it via `pydantic-settings`; import `from app.config import settings` rather than reading env vars directly.

## Architecture

### Ingestion pipeline (`app/ingestion/`)
`parser.py` → `chunker.py`, invoked together via `process_paper_ingestion()` in `chunker.py`.
- `parser.parse_pdf_to_markdown()`: PyMuPDF4LLM with a raw-`fitz` fallback if it fails (e.g. OOM on the Railway free tier). Page-chunk output is joined into a single Markdown string with `<!-- page:N -->` markers (used by a future page-aware chunker, not yet consumed).
- `chunker.split_parent_sections()`: regex-based heading detection (Markdown `#`, bold `**Title**`, or Roman/decimal numbered IEEE-style headings) splits the document into `ParentSection`s.
- `chunker.create_child_chunks()`: sliding-window split of each section into `ChildChunk`s (`settings.chunk_size`/`chunk_overlap`, default 800/150 chars), snapping cut points to paragraph → sentence → word boundaries via `_find_split_point()`.
- **Important existing gap**: `ParentSection`s are produced but never persisted anywhere downstream — only `ChildChunk`s get indexed. "Parent-child" retrieval (expanding a matched chunk back to its full section) does not currently exist despite the naming.
- Chunks are cached to `data/chunks_cache/{paper_id}_chunks.json` (`save_chunks_to_file`/`load_chunks_from_file`) so re-uploading the same `paper_id` skips re-parsing.

### Indexing / retrieval (`app/indexing/`)
- `vector_store.py`: `VectorStoreManager` wraps a single global ChromaDB collection (`arxiv_papers`, persisted at `settings.db_dir`). Isolation between papers is by metadata filter (`paper_id`), not separate collections. Embeddings come from `HuggingFaceAPIEmbeddings`, a duck-typed (not a LangChain `Embeddings` subclass) wrapper around the HF Inference API — no local model download.
- `bm25_store.py`: `BM25StoreManager` persists a `rank_bm25.BM25Okapi` index + chunk metadata as pickles under `data/bm25_index/`. `build_index()` **merges** new chunks into the existing on-disk corpus by `chunk_id` rather than replacing it — this was a deliberate fix for a bug where re-indexing one paper used to wipe out every other paper's BM25 entries while ChromaDB kept them, silently degrading hybrid search to dense-only. Don't "simplify" this back to a plain rebuild.
- `hybrid_retriever.py`: `HybridRetriever.retrieve()` runs dense (Chroma) + sparse (BM25) search independently, top-20 each, fuses with unweighted `reciprocal_rank_fusion()` (`k=60`), then hands the top `first_stage_k` to the reranker. Each `HybridRetriever()` instance builds its own store clients — there is no shared singleton, so constructing one per request is expected (if wasteful) with the current code.
- `reranker.py`: `RerankerManager` picks Cohere Rerank (`rerank-english-v3.0`) if `COHERE_API_KEY` is set, otherwise falls back to a local `sentence-transformers` CrossEncoder (`ms-marco-MiniLM-L-6-v2`, `max_length=512`). Don't pre-truncate chunk text by character count before handing it to the CrossEncoder — let the tokenizer's own `max_length` truncation handle it (a previous bug did character-truncation to 512 chars, discarding most of an 800-char chunk).

### Agent (`app/agent/rag_graph.py`)
LangGraph `StateGraph` over `AgentState` (question, paper_id, retrieved_chunks, grade, rewrite_count, answer, messages). Flow: `retrieve → grade → (rewrite → retrieve)* → generate`, capped at `MAX_REWRITES = 2`. `grade_node` does a single whole-batch yes/no LLM call over all retrieved chunks (not per-document). Conversation memory uses `SqliteSaver` at `data/chat_memory.db`, keyed by `thread_id` — this is on ephemeral disk in the current deploy, so history does not survive a Railway redeploy (tracked as a roadmap item). `_get_checkpointer()` needs the `langgraph-checkpoint-sqlite` package (in `requirements.txt`) for this — if it's ever missing, the broad `except Exception` around the import silently falls back to in-memory `MemorySaver` instead of erroring, which previously went unnoticed and lost chat history on every process restart, not just redeploys. The single public entry point other modules should use is `ask(question, paper_id, thread_id)` — don't call the graph nodes directly.

### LLM factory (`app/llm/llm_factory.py`)
`get_llm(provider=None, temperature=0.2, max_tokens=5096)` is the only way other modules should construct an LLM — never import `ChatGroq`/`ChatGoogleGenerativeAI`/`ChatOllama` directly elsewhere. Provider auto-detect order: Groq → Gemini → Ollama, based on which API key is set in `.env`. When Groq is auto-selected and `GEMINI_API_KEY` is also present, the returned LLM is wrapped with `.with_fallbacks([gemini_llm])` so a Groq runtime failure (rate limit, decommissioned model, timeout) transparently retries on Gemini. `get_llm()` and the internal Groq model-picker (`_pick_best_groq_model`, which calls the Groq API to pick the best currently-available model from a hardcoded preference list) are both `@lru_cache`d — do not add per-call state that would need to vary across calls without also reconsidering the cache.

### API (`app/api/`)
FastAPI app in `main.py`, all routes in `routes.py` under prefix `/api/v1` (`/health`, `/papers`, `POST /upload`, `POST /ask`). Uploaded-paper metadata lives in a flat JSON file, `data/papers_registry.json` (`_load_registry`/`_save_registry` in `routes.py`) — also ephemeral on Railway, also a tracked roadmap item to migrate to Postgres. `/upload`'s handler is synchronous work inside an `async def`, which blocks the event loop for the full parse+embed duration; this is known and slated for a `BackgroundTasks` refactor, not something to silently "fix" as a drive-by change without checking the roadmap phase first.

### Frontend (`streamlit_app.py`)
Single-file Streamlit app. Resolves the API base URL via `_resolve_api_base()`: `API_BASE` env var → `st.secrets["API_BASE"]` → local `http://127.0.0.1:8000` fallback. Session state tracks `chat_history`, `thread_id`, `selected_paper`; changing the selected paper or clicking "Xóa lịch sử chat" issues a fresh `thread_id`.

### Config (`app/config.py`)
`Settings` (pydantic-settings) loads `.env` and also sets `HF_HOME`/`OLLAMA_MODELS` env vars at import time to redirect model caches into `cache/` inside the repo — importing `app.config` has this side effect, so it should generally be imported before other libraries that read those env vars (transformers, huggingface_hub, ollama).
