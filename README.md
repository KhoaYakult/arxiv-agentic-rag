# ArXiv Agentic RAG

Corrective-RAG (CRAG) question-answering system over scientific PDF papers. Upload a paper (or import it by arXiv ID), ask questions about it in Vietnamese or English, and get answers grounded in the paper's content with source citations (section and page).

```mermaid
flowchart TD
    subgraph CLIENT ["Client and API"]
        WEB["Web UI: Next.js<br/>(own Vercel project)"] -->|"HTTPS + X-API-Key<br/>(added server-side)"| API["FastAPI<br/>(Vercel)"]
        ST["Streamlit UI<br/>(being retired)"] -.->|"HTTPS + X-API-Key"| API
        WEB -.->|"signed URL"| STORE[("Supabase Storage<br/>original PDFs")]
    end

    subgraph INGESTION ["Ingestion (background task)"]
        PDF["PDF upload (up to 4 MB)<br/>or arXiv import (up to 30 MB)"] --> PARSER["parser.py<br/>PyMuPDF4LLM"]
        PDF --> STORE
        PARSER --> CHUNKER["chunker.py<br/>parent-child chunking"]
        CHUNKER --> EMB["Gemini embeddings"]
        EMB --> DB[("Supabase Postgres<br/>pgvector + full-text index")]
    end

    subgraph AGENT ["LangGraph agent (Corrective RAG)"]
        RETRIEVE["Retrieve"] --> DENSE["Dense: pgvector"]
        RETRIEVE --> SPARSE["Sparse: Postgres FTS (OR)"]
        DENSE & SPARSE --> RRF["RRF fusion"]
        RRF --> RERANK["Cohere rerank-v3.5<br/>(local CrossEncoder fallback)"]
        RERANK --> GRADE{"Grade: enough<br/>context?"}
        GRADE -->|"no, up to 2 times"| REWRITE["Rewrite query"]
        REWRITE --> RETRIEVE
        GRADE -->|"yes"| GEN["Generate answer<br/>with citations"]
    end

    API --> PDF
    API --> RETRIEVE
    DB -.-> DENSE
    DB -.-> SPARSE
```

## Status

- **Phase 1 (hardening) and Phase 2 (one Postgres for everything) are done.** Supabase Postgres + pgvector, Gemini embeddings, Postgres full-text search, Postgres-backed chat memory.
- **Web UI (new):** a Next.js app in `web/` (library, chat with clickable page citations, side-by-side PDF viewer that highlights the quoted passage), deployed as its own Vercel project. It is a private beta behind one shared password, and its server-side route handlers add the API key, so the key never reaches the browser. The Streamlit UI in `ui/` is being retired and will be removed once the web app has run stably. See [`web/README.md`](web/README.md) (Vietnamese) for running and deploying it. "Paper Reader" is a temporary product name (it collides with an existing iOS app) and must change before any public launch.
- **Deployed:** API on Vercel; the Streamlit UI on Streamlit Community Cloud until the web app replaces it. The API is protected by an `X-API-Key` header and the UIs are private, so there is no public demo link.
- **Known gap, citations:** the model never invents citation numbers, but it often leaves them out. Only 10/21 answers carry a valid `[n]` marker, well under the 80% target (see [Evaluation](#evaluation)). Every answer still shows its sources row, so the evidence is always visible. Improving marker coverage is the next step.
- **Phase 3 (evaluation) is in progress:** a golden set and a retrieval benchmark exist and have already driven two fixes (see [Evaluation](#evaluation)). Still to do: answer-quality evaluation (RAGAS / LLM judge), language-aware sparse search, a parser comparison.
- Planned after that: multi-paper querying, RAPTOR-style summaries, production polish (rate limiting, streaming).

## Stack

- **Parsing**: PyMuPDF4LLM (layout mode, with raw `fitz` fallback), page-aware
- **Chunking**: section-based parent-child (regex heading detection + sliding window), every chunk carries its section and page
- **Retrieval**: Postgres/pgvector (dense, HNSW) + Postgres full-text search (sparse, OR semantics over the question's lexemes) -> Reciprocal Rank Fusion -> Cohere `rerank-v3.5` (multilingual; local CrossEncoder fallback when `sentence-transformers` is installed)
- **Embeddings**: Gemini (`gemini-embedding-001`, 768 dimensions)
- **Agent**: LangGraph Corrective-RAG (`retrieve -> grade -> rewrite-if-insufficient -> generate`), chat memory in Postgres (`AsyncPostgresSaver`)
- **LLM**: Groq (primary) with automatic runtime fallback to Gemini
- **Backend**: FastAPI
- **Frontend**: Next.js 16 + React 19 + Tailwind 4 + shadcn/ui, react-pdf for the viewer (`web/`); the legacy Streamlit UI (`ui/`) is being retired
- **Storage**: Supabase Storage (private bucket) keeps the original PDFs for the viewer
- **Deploy**: Vercel (API and web UI as two projects) + Streamlit Community Cloud (legacy UI)

## Evaluation

Retrieval quality is measured with a small hand-written golden set (`eval/golden_set.jsonl`): questions over three arXiv papers (Attention Is All You Need, DPR, CRAG; 427 chunks), each with a reference answer and a verbatim evidence quote plus its page. A retrieved chunk counts as relevant if it contains the quote (*strict*: exact substring; *lenient*: at least 80% of the quote's 8-character shingles, which tolerates the parser scrambling table cells). The numbers below use **lenient** matching on the **21 answerable questions** (15 English, 6 Vietnamese).

| Pipeline | Hit@1 | Hit@5 | MRR@20 | nDCG@10 | Hit@5 EN / VI |
|---|---|---|---|---|---|
| Baseline: "hybrid" (its sparse half silently returned nothing, so effectively dense-only) + Cohere `rerank-english-v3.0` | 0.381 | 0.667 | 0.503 | 0.508 | 0.80 / 0.33 |
| Dense only, no rerank (reference) | 0.381 | 0.571 | 0.508 | 0.565 | 0.53 / 0.67 |
| **Current**: OR-semantics sparse + RRF + Cohere `rerank-v3.5` | **0.619** | **0.905** | **0.735** | **0.756** | **0.93 / 0.83** |

What the evaluation found and what was fixed:

- **Sparse search returned zero results on 21/21 questions.** `websearch_to_tsquery` ANDs every word of a long natural-language question, so no chunk matched. Now the question's lexemes are OR-ed (`plainto_tsquery(...)` with `&` replaced by `|`) and ranked with `ts_rank_cd`.
- **The English-only reranker hurt Vietnamese questions** (Hit@5 0.67 -> 0.33). Switching to the multilingual `rerank-v3.5` brought Vietnamese to 0.83. The model is configurable via `COHERE_RERANK_MODEL`.
- Strict matching gives a lower bound for the current pipeline: Hit@5 = 0.857. Table and numeric questions remain the weakest spot (the parser loses some table structure).

**Caveat: n = 21.** One question is worth about 4.8 points, so only the large jumps above should be trusted, and even those are directional rather than statistically solid. Answer-quality evaluation is not done yet. Per-question ranks and per-type / per-language breakdowns are written to `eval/results/<date>_<label>.md`.

**Citation check.** `make eval-citations` asks the 21 answerable questions through the real agent and checks the `[n]` markers in each answer (results in `eval/results/2026-10-25_citations.md`, and `2026-10-25_citations-v2.md` after tightening the prompt). Both runs gave the same numbers: (a) 10/21 = 48% of answers contain at least one valid marker, (b) 0 out-of-range markers, (c) citation precision (lenient) 8/21 = 38%. That is below the 80% target set for the web UI: the model never invents citation numbers, but it often omits them. Raising marker coverage is the next step.

To reproduce, you need a throwaway Postgres with pgvector (never point this at a real database; the scripts refuse URLs containing `supabase`), a `GEMINI_API_KEY`, and the three PDFs in `eval/papers/` (named `1706.03762.pdf`, `2004.04906.pdf`, `2401.15884.pdf`; PDFs are not committed):

```bash
docker run -d --name pgeval -e POSTGRES_PASSWORD=postgres -p 55434:5432 \
    -v arxiv_eval_pg:/var/lib/postgresql/data pgvector/pgvector:pg16
export EVAL_DATABASE_URL=postgresql://postgres:postgres@localhost:55434/postgres

python eval/index_papers.py   # index eval/papers/*.pdf (sleeps 61 s between papers: Gemini free-tier quota)
make eval                     # all configs: sparse, dense, rrf, rrf+rerank (query embeddings are cached in eval/cache/)
make eval ARGS="--label my-change --configs rrf,rrf+rerank"
```

Metrics: Hit@1/3/5/10/20, MRR@20, nDCG@10, plus the count of questions where a config returned nothing. `make eval` also needs `COHERE_API_KEY` for the `rrf+rerank` config.

## Setup

```bash
pip install -r requirements-dev.txt   # runtime deps + local CrossEncoder + pytest/ruff
# (requirements.txt alone is the slim runtime set that Vercel installs)
cp .env.example .env   # fill in DATABASE_URL, GROQ_API_KEY, GEMINI_API_KEY, COHERE_API_KEY, HF_TOKEN
```

`DATABASE_URL` is a Supabase **Session pooler** URI (the direct connection is IPv6-only). Run `db/schema.sql` once on a fresh database (e.g. in the Supabase SQL editor).

## Running

```bash
# API (from repo root, auto-reloads)
make run        # uvicorn app.api.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs

# UI (separate process, calls the API over HTTP)
make ui         # streamlit run ui/streamlit_app.py
```

The Streamlit UI finds the API through `API_BASE` (environment variable, then Streamlit secrets, then `http://127.0.0.1:8000`) and sends `APP_API_KEY` as `X-API-Key` when set. See `ui/README.md` (Vietnamese) for details.

```bash
# Web UI (Next.js, needs the API running)
cp web/.env.example web/.env.local   # API_BASE, APP_API_KEY, ACCESS_PASSWORD, SESSION_SECRET (32+ chars)
make web-dev                         # cd web && npm run dev, http://localhost:3000
make web-test                        # lint + typecheck + Vitest
```

End-to-end tests (`cd web && npm run e2e`) run against a mock backend, so they use no API quota. See `web/README.md` (Vietnamese).

## API

All routes live under `/api/v1`. When `APP_API_KEY` is set, every route except the two health checks requires the header `X-API-Key: <APP_API_KEY>` (HTTP 401 otherwise).

| Method and path | Purpose |
|---|---|
| `GET /health` | Liveness (public) |
| `GET /health/db` | `SELECT 1` against Postgres (public; a daily Vercel cron calls it so Supabase free does not auto-pause) |
| `GET /papers` | List papers that are `ready` (each includes `has_pdf`) |
| `POST /upload` | Upload a PDF (up to 4 MB, must start with `%PDF`). Returns `202` and indexes in the background, or `200` with the existing paper when the same bytes were already indexed (sha256 dedup) |
| `POST /papers/arxiv` | Import by arXiv ID, body `{"arxiv_id": "2401.15884"}`. The server downloads the PDF itself (up to 30 MB), then behaves like `/upload`; `paper_id` is `arxiv-<id>` |
| `GET /papers/{paper_id}/status` | Poll `processing` / `ready` / `failed` (a job stuck in `processing` for over 15 minutes is reported as `failed`); also reports `has_pdf` |
| `GET /papers/{paper_id}/pdf-url` | Signed URL (valid 1 hour) for the original PDF in Supabase Storage, so the browser downloads it directly. `404` if the paper has no stored PDF or Storage is not configured |
| `DELETE /papers/{paper_id}` | Delete a paper with its sections, chunks and PDF |
| `POST /ask` | Ask a question about one paper: answer, sources (section, page, chunk `text`), number of query rewrites. Returns `429` when the upstream AI quota is exhausted |

## Deploy

> **Deploy order:** run `db/migrations/2026-10-25_has_pdf.sql` on Supabase **before** pushing/deploying this version of the API (pushing `main` auto-deploys it). Otherwise uploads and arXiv imports fail (500), because `upsert_paper` now writes `has_pdf`.

**API on Vercel (Hobby plan)** - the FastAPI app is deployed as a single Python function.

1. Import the GitHub repo in Vercel. `vercel.json` defines one `api` service (FastAPI, entrypoint `app.api.main:app`, `maxDuration` 300 s, `excludeFiles` to keep the bundle small, a rewrite of all paths to the service and a daily cron). `.python-version` pins Python 3.12.
2. **Dependencies come from `pyproject.toml`**: Vercel reads `[project].dependencies` before `requirements.txt`. Keep the two files identical (`tests/test_dependency_sync.py` enforces this and forbids `torch` / `sentence-transformers` / `streamlit` in the runtime list).
3. Set these environment variables (Project -> Settings -> Environment Variables):
   - `DATABASE_URL` - Supabase Session pooler URI
   - `GEMINI_API_KEY` (embeddings + fallback LLM), optionally `GROQ_API_KEY`
   - `COHERE_API_KEY` - strongly recommended: without it (and without `sentence-transformers`, which is not installed on Vercel) reranking is disabled and chunks keep their RRF order
   - `APP_API_KEY` - the value clients must send as `X-API-Key`; always set it on a production deployment, and the web project must use the same value
   - `ALLOWED_ORIGINS` - comma-separated; add the Streamlit Cloud URL (e.g. `https://your-app.streamlit.app`)
   - `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` - enable storing the original PDFs for the web UI's viewer (the service role key stays on the API project only). `STORAGE_BUCKET` defaults to `papers`. Without them the API still works, but papers have `has_pdf=false`
   - optional: `GEMINI_MODEL_NAME`, `COHERE_RERANK_MODEL`, `MAX_UPLOAD_MB`
4. The cron in `vercel.json` calls `GET /api/v1/health/db` daily at 06:00 UTC (production deployments only).

Platform limits that shaped the code:
- A request body is capped at 4.5 MB, so `POST /upload` rejects files over 4 MB (`MAX_UPLOAD_MB`, HTTP 413). For larger PDFs use `POST /papers/arxiv`, where the server downloads the file.
- A function is cut off after 300 s (`maxDuration`); a paper whose indexing is killed stays `processing` and is reported as `failed` after 15 minutes.
- The filesystem is writable only under `/tmp` (not shared across instances); data and caches go there when `VERCEL` is set, while papers live in Postgres.
- Gemini free tier allows 100 embeddings/min and 1000/day; indexing is serialized per process and pauses between batches to stay inside it.

**Supabase Storage (one-time, for the web UI's PDF viewer)** - create a **private** bucket named `papers`, and run `db/migrations/2026-10-25_has_pdf.sql` in the SQL editor (adds `papers.has_pdf`; safe to re-run). Then add the two Supabase variables above to the API project and redeploy.

**Web UI on Vercel (second project)** - import the same repo as a new project with **Root Directory = `web`** (framework Next.js). Set `API_BASE` (the API project's URL, without `/api/v1`), `APP_API_KEY` (same value as the API's, which must be set in production), `ACCESS_PASSWORD` (the shared password) and `SESSION_SECRET` (32+ random characters). Limits: uploads up to 4 MB, arXiv imports up to 30 MB, and the Gemini free tier allows 1000 embeddings per day (resets at midnight Pacific: about 14:00 Vietnam time, or 15:00 after US daylight saving ends). Papers indexed before the Storage setup have `has_pdf=false`, and re-importing one returns the existing paper unchanged, so delete it and import again to get a PDF. A paper whose embedding hits the quota may end up `failed`. Step-by-step guide (Vietnamese): `web/README.md`.

**Legacy UI on Streamlit Community Cloud (being retired)** - create an app from this repo with main file `ui/streamlit_app.py`; dependencies come from `ui/requirements.txt` (only `streamlit` and `requests`). In *Advanced settings -> Secrets* set:

```toml
API_BASE = "https://<your-vercel-project>.vercel.app"
APP_API_KEY = "<same value as the API's APP_API_KEY>"
```

The theme (dark base) and `maxUploadSize = 4` live in `.streamlit/config.toml` at the **repository root**. If the sidebar shows "Server chưa chạy" on Streamlit Cloud, the `API_BASE` secret is missing. Full instructions (Vietnamese): `ui/README.md`.

## Docker

```bash
docker build -t arxiv-rag .
docker run -p 8000:8000 --env-file .env arxiv-rag
```

## Testing & linting

```bash
make test               # unit tests, no network or API keys needed
make test-integration   # needs a throwaway Postgres+pgvector (never Supabase), see the Makefile
make lint               # ruff check .
```

CI (`.github/workflows/ci.yml`) runs `ruff` and the unit tests on every push/PR to `main`.

## Project layout

- `app/ingestion/` - PDF parsing (`parser.py`) and parent-child chunking (`chunker.py`)
- `app/indexing/` - embedding provider (`embeddings.py`) and reranking (`reranker.py`)
- `app/storage/` - Postgres repository layer (`repository.py`): CRUD for papers/sections/chunks + `hybrid_search()` (dense pgvector + sparse Postgres FTS, fused with RRF), and Supabase Storage client for the original PDFs (`pdf_store.py`, signed URLs)
- `app/agent/` - LangGraph Corrective-RAG agent (`rag_graph.py`)
- `app/llm/` - LLM provider factory (`llm_factory.py`) and prompt templates (`prompt_templates.py`)
- `app/api/` - FastAPI app, routes and API-key auth
- `web/` - Next.js web UI (shared-password private beta): pages, `/api/*` proxy route handlers, PDF viewer, Vitest and Playwright tests (Vietnamese `README.md`)
- `db/migrations/` - one-off SQL migrations (e.g. `2026-10-25_has_pdf.sql`)
- `ui/` - legacy Streamlit frontend, being replaced by `web/` (`streamlit_app.py`, its own `requirements.txt` and `README.md`)
- `.streamlit/config.toml` - Streamlit theme and upload limit (must stay at the repo root)
- `eval/` - Phase 3 retrieval evaluation: golden set, metrics, runner, indexer and results (`eval/results/`)
- `db/schema.sql` - Postgres schema
- `tests/` - unit tests (`tests/integration/` needs Postgres)
- `vercel.json`, `pyproject.toml`, `requirements*.txt` - deployment and dependency configuration
