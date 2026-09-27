# 🗺️ ROADMAP — ArXiv Agentic RAG → Production-Grade

> **Phiên bản:** 3.2 · **Cập nhật:** 2026-09-19
> **Trạng thái:** Phase 1 hoàn thành, đã verify end-to-end trên máy thật (xem mục Phase 1 bên dưới). Đang chuẩn bị Phase 2.
> **Mục tiêu:** sản phẩm chạy thật, có số đo chất lượng, kể được câu chuyện kỹ thuật mạnh trên CV.

---

## 0. Ràng buộc & định hướng

| Tiêu chí | Lựa chọn |
|---|---|
| Ưu tiên | **Cân bằng** — ổn định/hạ tầng trước, kỹ thuật advanced sau |
| Ngân sách | **Chỉ free tier** |
| Phạm vi | **Multi-paper** — thư viện cá nhân, hỏi trong 1 bài hoặc xuyên nhiều bài |
| Thời gian | **3+ tháng**, vừa học vừa làm |

---

## 1. Quyết định kiến trúc (chốt — định hình mọi phase)

| Vấn đề | Quyết định | Lý do |
|---|---|---|
| **Storage** | **Supabase Postgres + pgvector**, bỏ ChromaDB | 1 service thay vì 4. Postgres lo cả registry, parent sections, dense vector (HNSW), sparse (`tsvector` FTS), và LangGraph checkpointer (`AsyncPostgresSaver`). Free 500MB ≈ vài trăm paper. |
| **Sparse retrieval** | **Postgres FTS** thay `rank_bm25` | Sparse index thành một cột ghi trong cùng transaction với chunk → bug "upload paper B xoá BM25 paper A" **biến mất về mặt cấu trúc**, không phải được vá. Bỏ luôn pickle (fragile + unsafe load). |
| **Embedding** | **Gemini `gemini-embedding-001`, 768-dim** (MRL truncation) | Free, mạnh hơn MiniLM rõ rệt, có `task_type=RETRIEVAL_DOCUMENT/QUERY` (asymmetric — đúng bài RAG), 0MB RAM. Vẫn viết `EmbeddingProvider` interface + `reindex.py` để đổi model chỉ tốn 1 lệnh. |
| **Redis** | **Xoá khỏi requirements + config** | Đã khai báo từ lâu nhưng chưa từng được import. Postgres checkpointer thay thế hoàn toàn. |
| **Multi-paper** | **Two-stage routing + fan-out**, không GraphRAG ngay | Mỗi paper có "paper card" (summary) được embed. Router phân loại query → chọn top-3 paper → retrieve **fan-out từng paper riêng**. ⚠️ Nếu chỉ bỏ filter `paper_id` rồi lấy global top-k, cả 5 chunk sẽ rơi vào cùng 1 paper → câu "so sánh A với B" trả lời thiên lệch. |
| **RAPTOR** | **Làm** (Phase 5) | Rẻ, không cần hạ tầng mới, trả lời trực tiếp loại câu mà chunk-level RAG luôn thua ("đóng góp chính là gì"). Tái dùng bảng `chunks` với cột `level`. |
| **GraphRAG đầy đủ** | **Không làm** | Entity extraction + Leiden community + community summaries quá tốn LLM cho 50–200 paper, không đủ free tier để rebuild mỗi lần upload. **Thay bằng** bảng `paper_facts` quan hệ sinh bởi 1 LLM pass — câu "paper nào dùng contrastive loss trên ImageNet?" trở thành SQL, chính xác 100%. Đó là 80% giá trị GraphRAG với 5% chi phí. |
| **Deploy** | Railway (FastAPI) + Streamlit Cloud (UI) + Supabase + Gemini/Groq/Jina API | Không thêm service nào nữa. |

---

## 2. Bug đã xác minh — thứ tự xử lý

✅ Cả 7 bug dưới đây đã **sửa xong** trong Phase 1 (commit `f535a4e`, `0277d86`). Giữ bảng lại làm hồ sơ tra cứu — vị trí dòng có thể lệch so với code hiện tại.

| # | Bug | Vị trí (lúc phát hiện) | Quyết định |
|---|---|---|---|
| 1 | `to_markdown(page_chunks=True)` trả `list[dict]` nhưng hàm typed `-> str`, gọi `len()` rồi return → downstream regex `TypeError` | `app/ingestion/parser.py:43` | **Đã sửa**, giữ `page_chunks=True`, nối lại thành 1 chuỗi markdown kèm marker `<!-- page:N -->` — Phase 2 sẽ trích số trang từ marker này. |
| 2 | `_find_split_point` fallback #3: `space_pos = min(50, int(target*0.08))` trả index gần **đầu** chuỗi thay vì `rfind(" ")` gần `target` | `app/ingestion/chunker.py:89-91` | **Đã sửa** — `text.rfind(" ", int(target*0.08), target)`. Có test hồi quy trong `tests/test_chunker.py`. |
| 3 | `sources` **luôn rỗng**: đọc `result.get("documents")` nhưng `AgentState` chỉ có `retrieved_chunks` (dict, không phải `Document`) | `app/api/routes.py:275-283` | **Đã sửa** — đọc đúng `retrieved_chunks`. |
| 4 | Nhánh Gemini không bao giờ chạy khi có GROQ key; `_pick_best_groq_model()` gọi `models.list()` mỗi lần `get_llm()` (1 round-trip mạng / node); `langchain-google-genai` thiếu trong requirements | `app/llm/llm_factory.py:119-122, 138` | **Đã sửa** — `@lru_cache` cho cả hai hàm, fallback runtime Groq→Gemini qua `.with_fallbacks()` khi Groq lỗi, thêm dep. |
| 5 | `_rerank_local` cắt `text[:512]` — 512 **ký tự** không phải token (mất ~65% chunk 800 ký tự); mutate `candidates` in-place | `app/indexing/reranker.py:93-114` | **Đã sửa** — bỏ cắt ký tự (để tokenizer tự truncate), làm việc trên bản sao thay vì mutate. |
| 6 | `build_index()` reset `self._chunks_meta = []` → upload paper B **xoá sạch** BM25 của paper A, trong khi Chroma vẫn giữ → hybrid âm thầm tụt về dense-only | `app/indexing/bm25_store.py:111` | **Đã vá tạm** — merge theo `chunk_id` với corpus đã load từ disk. File này vẫn **sẽ bị xoá hoàn toàn ở Phase 2** khi chuyển sang Postgres FTS — đừng refactor tử tế thêm ở đây. |
| 7 *(phát hiện thêm khi verify Phase 1)* | `_get_checkpointer()` import `langgraph.checkpoint.sqlite`, nhưng `langgraph-checkpoint-sqlite` **chưa từng khai báo** trong `requirements.txt`. `except Exception` rộng nuốt `ModuleNotFoundError` → âm thầm fallback `MemorySaver` → **lịch sử chat mất mỗi lần restart process**, không chỉ khi Railway redeploy như ghi ở trên. | `app/agent/rag_graph.py` + `requirements.txt` | **Đã sửa** — thêm dependency, verify bằng cách import trực tiếp: trước fix in ra `[WARN] SqliteSaver loi`, sau fix in ra `[INFO] Checkpointer: SqliteSaver`. |

---

## Phase 1 — Cầm máu + nền kỹ thuật ✅ HOÀN THÀNH (2026-09-13)

**Mục tiêu:** pipeline chạy lại end-to-end; repo trông như repo của kỹ sư.
**CV claim:** *"engineering hygiene: typed config, pinned deps, CI, test suite"*

### Việc đã làm
- [x] Sửa bug #1, #2, #3, #4, #5, #7; vá tạm #6 (xem mục 2).
- [x] `pyproject.toml` (ruff + pytest config), `.pre-commit-config.yaml`, `Makefile` (`make install/run/ui/test/lint/fmt/docker-build/docker-run`), `.dockerignore`.
- [x] Pin toàn bộ `requirements.txt` theo `==` (không phải `>=`) — verify 2 lần: venv đang dùng + 1 venv sạch cài lại từ đầu chỉ bằng file này, cả 2 đều pass test + import toàn bộ module + compile được LangGraph. Thêm `huggingface_hub`, `numpy`, `langchain-google-genai`, `langgraph-checkpoint-sqlite` (bug #7). Xoá `upstash-redis`, `langgraph-checkpoint-redis` (chưa từng dùng).
- [x] `Dockerfile`: multi-stage (build-essential chỉ ở builder stage), `CMD` dùng `${PORT:-8000}` thay vì hardcode, non-root user (`appuser`), `HEALTHCHECK`.
- [x] `tests/`: 20 test cho 4 hàm thuần — `split_parent_sections`, `_find_split_point` (có test hồi quy cho bug #2), `reciprocal_rank_fusion`, `tokenize`.
- [x] GitHub Actions (`.github/workflows/ci.yml`): ruff + pytest trên mọi push/PR vào `main`.
- [x] `README.md`, `CLAUDE.md`, `docs/Architecture.md` (viết mới — bản cũ chỉ là bảng đề xuất, không phải tài liệu kiến trúc thật).
- [x] Dọn dẹp repo: `.gitignore` thiếu `.venv/` (1.5GB!)/`.pytest_cache/`/`.ruff_cache/`, xoá cache/pycache rác, gộp trùng lặp thư mục skill (`.agents/` trùng `.claude/skills/`).

### Kiểm chứng
- `make test` xanh (20/20), `ruff check .` sạch — verify trong CI lẫn local.
- `requirements.txt` verify trên venv sạch hoàn toàn (không rely vào package đã cài từ trước).
- ✅ **Verify trên máy thật (2026-09-19)**: `docker build`/`docker run` — `docker ps` báo `healthy`, `docker exec whoami` → `appuser` (non-root), `$PORT=9000` tuỳ chỉnh trả lời đúng port. Upload PDF thật (182 chunks) → `/ask` thật trả lời đúng nội dung, **`sources` có 5 phần tử** — xác nhận bug #3 hết thật ngoài đời, không chỉ unit test.

### Kiến thức đã áp dụng
pytest fixtures/class-based test grouping · ruff rule selection & per-file-ignore · Docker multi-stage build · `lru_cache` + LangChain `.with_fallbacks()` cho runtime resilience.

---

## Phase 2 — Supabase là nguồn sự thật duy nhất ⭐ *phase quan trọng nhất* — 🟡 ĐANG LÀM, phần lõi đã xong

**Mục tiêu:** dữ liệu sống sót qua redeploy; chunk có page number; parent section **thật sự tồn tại** (hiện `ParentSection` được tạo rồi vứt đi — "parent-child" chỉ có trên tên).
**CV claim:** *"migrated from ephemeral file-based stores to a single Postgres+pgvector backend; zero data loss on deploy"*

**Trạng thái (2026-09-27):** `/upload`, `/papers`, `/ask` đã cutover hoàn toàn sang Postgres, verify thật qua HTTP với PDF 182 chunks thật. `/upload` chạy nền qua `BackgroundTasks` (trả `202` gần như tức thì, poll `GET /papers/{id}/status`). `DELETE /papers/{id}` + FastAPI `lifespan` (đóng pool lúc shutdown) đã xong. Checkpointer đã chuyển từ `AsyncSqliteSaver` sang `AsyncPostgresSaver` thật (`langgraph-checkpoint-postgres`) — chat history giờ sống trong CÙNG Postgres DB, verify bằng cách chạy `ask()` với cùng `thread_id` ở 2 process `python` riêng biệt (`messages so far: 2` rồi `4`), chứng minh lịch sử sống sót dù không có Python object nào tồn tại giữa 2 lần chạy. Chi tiết đầy đủ + 5 bug môi trường/thiết kế tìm được lúc test (IPv6-only DNS, password có `@`, pgvector ở schema `extensions`, Gemini quota tính theo item/phút, PDF lưu theo tên gốc gây ghi đè) ở `project-memory/FIXED_BUGS.md` #8-#12. Page-aware chunking đã xong (2026-09-27, xem checklist bên dưới). File_hash dedup trên `/upload` cũng đã xong (2026-09-27, xem checklist bên dưới). Còn thiếu: xoá code Phase 1 cũ.

### Schema
```sql
papers(id, title, authors, arxiv_id, filename, file_hash UNIQUE,
       num_pages, num_chunks, status, created_at)

sections(id, paper_id FK, section_id, name, level, text, page_start, page_end)

chunks(id, paper_id FK, section_pk FK, chunk_id UNIQUE, text,
       page_num, char_start, char_end, is_table,
       level SMALLINT DEFAULT 0,
       embedding vector(768),
       fts tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED)
-- HNSW index trên embedding, GIN index trên fts

paper_cards(paper_id FK, summary, embedding vector(768))

-- checkpointer: để AsyncPostgresSaver tự tạo bảng
```
`file_hash` dùng để dedup upload.

### Việc cần làm
- [x] Viết `app/storage/repository.py` (asyncpg + pgvector) thay `_load_registry`/`_save_registry`, `VectorStoreManager`, `BM25StoreManager`. CRUD `papers`/`sections`/`chunks` + `hybrid_search()` (dense pgvector `<=>` + sparse Postgres FTS, gộp bằng `reciprocal_rank_fusion()` tái dùng từ Phase 1).
- [x] `EmbeddingProvider` mới (`app/indexing/embeddings.py`, Gemini `gemini-embedding-001` 768-dim) có retry (`tenacity`) + tự throttle theo quota free-tier (61s giữa batch >100 item — bug #11).
- [x] `routes.py`: `/upload` ghi thẳng Postgres, `/papers` đọc Postgres, `/ask` check tồn tại qua Postgres. `rag_graph.py` chuyển hẳn sang async (bắt buộc vì `asyncpg` chỉ async) — checkpointer đổi sang `AsyncSqliteSaver` (vẫn SQLite, chưa phải Postgres — đã đổi tiếp sang `AsyncPostgresSaver` thật, xem dòng bên dưới).
- [x] Dense + sparse chạy song song bằng `asyncio.gather` trong `hybrid_search()`.
- [x] `ChildChunk` thêm `page_num`, `char_start`, `char_end`, `level` — `create_child_chunks()` gỡ marker `<!-- page:N -->` (đã có sẵn từ `parser.py`) qua `_strip_page_markers()`/`_page_at()`, tính `page_num`/`char_start`/`char_end` theo vị trí ký tự trong text đã làm sạch. `insert_chunks()`/`_DENSE_SEARCH_SQL`/`_SPARSE_SEARCH_SQL` ghi và trả về `page_num`, `SourceChunk.page_num` xuất hiện trong response `/ask`. Verify thật qua HTTP (2026-09-27): upload `data/sample_cortexODE.pdf` → `/ask` → nhiều `sources[].page_num` khác null (vd `14`).
- [ ] `parser.py` trả `list[dict]` per-page có offset; `split_parent_sections` nhận input page-aware để map heading → trang. (Khác việc trên: đây là refactor sâu hơn ở tầng parser/section-splitter, chưa làm — hiện `page_num` chỉ tính được ở tầng chunk nhờ marker string đã có sẵn.)
- [x] `/upload` → `BackgroundTasks`, trả `202` + `status`, poll qua `GET /papers/{id}/status`. Lỗi trong task nền ghi `papers.status='failed'` (không raise — không còn request để nhận). `repository.list_papers()` đổi lọc `WHERE status='ready'` để dropdown UI không cho chọn paper chưa xong. `streamlit_app.py` cập nhật poll thay vì đọc `num_chunks` ngay trong response upload.
- [x] Thêm `DELETE /papers/{id}` (cascade qua FK có sẵn trong schema, xoá thêm file PDF trên đĩa).
- [x] Cleanup connection pool qua FastAPI `lifespan` (`get_pool()` vẫn lazy-singleton per-process như cũ, giờ có đóng tường minh lúc shutdown).
- [x] Chuyển checkpointer `AsyncSqliteSaver` → `AsyncPostgresSaver` thật (dùng `langgraph-checkpoint-postgres`, kết nối psycopg riêng tới cùng `settings.database_url`, `prepare_threshold=0` vì Supabase Session pooler/PgBouncer không hỗ trợ prepared statement đa client). Verify thật: `python app/agent/rag_graph.py` in `[INFO] Checkpointer: AsyncPostgresSaver (Postgres)` (không phải `[WARN]`); và chạy `ask()` với cùng `thread_id` ở 2 process riêng biệt → `messages so far: 2` rồi `4`, chứng minh lịch sử sống sót qua process restart (giả lập Railway redeploy) không chỉ trong 1 process.
- [x] File dedup qua `file_hash` (sha256) — `/upload` giờ gọi `repository.get_paper_by_hash()` trước khi lưu file: nếu đã có paper cùng `file_hash` với `status='ready'`, trả về luôn thông tin paper cũ (`200`, không phải `202`), không parse/embed/index lại, không ghi file mới lên đĩa. Match với paper `'processing'`/`'failed'` KHÔNG short-circuit (coi như chưa có gì đáng tin để tái sử dụng, xử lý như upload mới). Verify thật qua HTTP (2026-09-27): upload `data/sample_cortexODE.pdf` dưới `paper_id=dedup_probe_a` → ready 181 chunks → upload lại **cùng byte** dưới `paper_id=dedup_probe_b` khác → `HTTP 200`, body trả về `paper_id=dedup_probe_a` (bản gốc), `data/dedup_probe_b.pdf` không tồn tại, `GET /papers/dedup_probe_b/status` → `404` (không có row Postgres nào được tạo cho `dedup_probe_b`).
- [ ] **Xoá hẳn** `app/indexing/vector_store.py`, `bm25_store.py`, `hybrid_retriever.py` — đã là dead code (không còn được `routes.py`/`rag_graph.py` import), cố ý giữ lại vài ngày phòng cần rollback trước khi xoá thật.

### Kiểm chứng
✅ **Đã verify qua HTTP thật (2026-09-20)**, xem `project-memory/STATE.md`: upload PDF 182 chunks thật → Postgres, `/ask` với câu hỏi tổng quát trả lời đúng (`grade:"yes"`, 5 sources hợp lý), câu hỏi số liệu trong bảng bị từ chối đúng cách (`grade:"no"`, không hallucinate — ghi nhận là backlog Phase 3 chứ không phải bug). `/papers` phản ánh đúng Postgres.

Còn thiếu: verify qua `railway redeploy` thật (chưa deploy code Phase 2 lên Railway) · integration test Postgres trong CI (hiện CI chỉ chạy 20 unit test thuần, không cần network — chưa có test cần DB thật).

### Kiến thức cần học
pgvector (HNSW vs IVFFlat, `ef_search`) · Postgres FTS (`tsvector`, `ts_rank_cd`, GIN) · asyncpg pooling · FastAPI `lifespan` + `BackgroundTasks` · Alembic migration.

---

## Phase 3 — Eval harness + chất lượng retrieval (tuần 7–9)

**Mục tiêu:** ngừng đoán, bắt đầu đo.
**CV claim:** *"built an offline eval harness; improved Recall@10 from X to Y"* — **đây là thứ làm CV bạn khác 95% RAG portfolio.**

### Việc cần làm
- [ ] `eval/golden_set.jsonl`: 40–60 câu tự viết trên 5–8 paper, kèm `relevant_chunk_ids`.
- [ ] `eval/run_eval.py`: in Recall@k, MRR, nDCG@10 cho từng cấu hình (dense-only / sparse-only / RRF / +rerank). Thêm RAGAS (faithfulness, answer relevancy) dùng Gemini làm judge.
- [ ] **Sau khi có số đo mới tối ưu:** weighted RRF (`w_dense`, `w_sparse` vào config, tune trên golden set), bỏ `round(...,6)` đang gây tie, đổi rerank sang Jina Reranker API (free tier, xử lý được chunk dài).
- [ ] `grade_node` → **per-document** với structured output (`llm.with_structured_output(GradeResult)`, Pydantic `relevant: bool, confidence: float`). Hiện là 1 câu yes/no free-text cho **toàn bộ** chunk cùng lúc.
- [ ] `rewrite_node` nhận thêm `chat_history` + lý do fail của grader (hiện chỉ thấy `{question}`, mù hoàn toàn với context). Thêm multi-query (3 biến thể, RRF gộp).
- [ ] **Small-to-big**: sau rerank, expand chunk → parent section text trước khi đưa vào generate (giờ mới làm được, vì Phase 2 đã persist sections).
- [ ] `RAG_ANSWER_TEMPLATE` thêm chỉ dẫn citation `[^chunk_id]`; generate trả `answer` + `cited_chunk_ids`.

### Kiểm chứng
`make eval` in bảng so sánh · **mỗi thay đổi retrieval phải kèm số đo** · CI chạy eval trên subset, fail nếu Recall@10 tụt >3%.

### Kiến thức cần học
RRF paper (Cormack 2009) · Corrective-RAG & Self-RAG papers · HyDE · RAGAS metrics · LLM-as-judge bias · `with_structured_output` / function calling.

---

## Phase 4 — Multi-paper library (tuần 10–12)

**Mục tiêu:** hỏi xuyên paper.
**CV claim:** *"query router + two-stage retrieval over a multi-document corpus"*

### Việc cần làm
- [ ] Khi ingest: sinh paper card (LLM summary từ abstract + intro + conclusion) → bảng `paper_cards`.
- [ ] Thêm `router_node` vào `rag_graph.py` **trước** `retrieve`, structured output `QueryRoute(mode, paper_ids, reasoning)` với `mode ∈ {single_paper, cross_paper_compare, library_metadata}`.
- [ ] `AgentState`: `paper_id: str` → `paper_ids: list[str]` + `mode`.
- [ ] `retrieve_node` rẽ nhánh: single → như cũ; cross → **fan-out `asyncio.gather` per-paper**, mỗi paper top-3, **giữ nguyên nhóm theo paper**.
- [ ] `generate`: `COMPARE_TEMPLATE` với context nhóm theo paper, bắt buộc citation `[paper_title, p.N]`.
- [ ] API: `/ask` nhận `paper_ids: list[str] | None` (`None` = toàn thư viện), bỏ 404 cứng ở `routes.py:247-252`.

### Kiểm chứng
15 câu cross-paper trong golden set · assert context đưa vào generate chứa **≥2 `paper_id` phân biệt** khi `mode=compare` · đo router accuracy trên bộ query có nhãn.

### Kiến thức cần học
Query routing patterns · sub-question decomposition · document-level vs chunk-level retrieval · RAG-Fusion.

---

## Phase 5 — RAPTOR + structured knowledge layer (tuần 13–16)

**Mục tiêu:** phần "advanced technique" trên CV, nhưng **có lý do tồn tại**.

### Việc cần làm
- [ ] `app/indexing/raptor.py`: UMAP + GMM cluster embedding chunk trong 1 paper → LLM summarize từng cluster → ghi vào **cùng bảng `chunks`** với `level=1,2` (tái dùng schema, không thêm bảng). Retrieval "collapsed tree": query cả level 0, 1, 2 cùng lúc.
- [ ] Bảng `paper_facts(paper_id, task, dataset, metric_name, metric_value, method, baseline)` sinh bằng 1 LLM pass có structured output. Thêm tool `search_facts()` cho router gọi khi `mode=library_metadata`.
- [ ] *(Tuỳ chọn)* `paper_relations(src_paper, dst_paper, relation)` — `cites` / `extends` / `compares_with`. Đủ multi-hop 1 bước mà không cần graph DB.

### Kiểm chứng
Golden set thêm nhóm "summary/synthesis" · so nDCG **có vs không** RAPTOR levels.
⚠️ **Nếu không cải thiện → ghi kết luận âm tính vào README.** Điều này *tăng* uy tín kỹ thuật, không giảm.

### Kiến thức cần học
RAPTOR paper (Sarthi 2024) · GraphRAG paper (đọc để biết *khi nào không dùng*) · UMAP + GMM clustering · hierarchical summarization.

---

## Phase 6 — Production polish (tuần 17+)

**Mục tiêu:** demo được cho nhà tuyển dụng bấm thử mà không sập / không bị abuse.

### Việc cần làm
- [ ] API key auth (header) + rate limit (`slowapi`); CORS whitelist thay `allow_origins=["*"]` (`main.py:66-71`).
- [ ] Streaming: `/ask/stream` SSE với `graph.astream_events`.
- [ ] Streamlit refactor (hiện 609 dòng 1 file, ~230 dòng CSS inline): tách `ui/` modules, dùng `st.chat_message`/`st.chat_input`, `st.cache_data` cho `/papers` (hiện `check_server()` gọi blocking **mỗi rerun**), **bỏ `unsafe_allow_html` khi render answer** (vừa là lỗ XSS vừa làm markdown không render), CSS ra file riêng, chat lưu theo `thread_id` trong Supabase (hiện mất sạch khi refresh).
- [ ] Observability: Langfuse free tier — trace từng node LangGraph, latency, token cost.
- [ ] GitHub Actions cron ping `/health` (chống Supabase free pause sau 7 ngày không hoạt động).
- [ ] README: GIF demo + **bảng eval** + ADR ngắn giải thích các quyết định ở mục 1.

### Kiểm chứng
Load test nhẹ (`hey`/`locust`, 10 concurrent), đo p95 · trace Langfuse thấy đủ 4–5 node · XSS check bằng paper chứa `<script>`.

### Kiến thức cần học
SSE vs WebSocket · LangGraph `astream_events` · Langfuse/OpenTelemetry · **OWASP Top 10 for LLM** (prompt injection qua nội dung PDF — rủi ro có thật với use case này).

---

## ⚠️ Lưu ý quan trọng nhất

**Đừng bỏ qua Phase 3.** Phase 2 và 5 dễ kể hơn, nhưng thứ phân biệt *"biết build RAG"* với *"biết build RAG tốt"* là **có số đo**. Một bảng eval trong README đáng giá hơn cả RAPTOR.

---
---

# 📎 Phụ lục — Tư liệu tham khảo

## A. So sánh Embedding model (MTEB)

| Model | Chiều | Kích thước | MTEB | Ghi chú |
|---|---|---|---|---|
| `all-MiniLM-L6-v2` *(đang dùng)* | 384 | 22M | ~56 | ⚠️ Legacy (2021) |
| `BAAI/bge-m3` | 1024 | 570M | 63.0 | Dense + Sparse trong 1 model, nhưng cần chạy local — container free không gánh nổi |
| `jinaai/jina-embeddings-v3` | 1024 | 570M | 65.7 | Hỗ trợ Late Chunking |
| `dunzhang/stella_en_1.5B_v5` | 8192 | 1.5B | 71.0 | Chất lượng/kích thước tốt nhất |
| **`gemini-embedding-001`** | 768–3072 | API | **72.4** | ✅ **Đã chọn** — free, asymmetric task_type, 0MB RAM |
| `voyage-3-large` | 2048 | API | 69.4 | Tốt cho tài liệu kỹ thuật, nhưng trả phí |

## B. So sánh Reranker

| Model | Provider | Miễn phí? | Ghi chú |
|---|---|---|---|
| Cohere Rerank v3.5 | Cohere API | ❌ | Multilingual tốt |
| **JinaAI Rerank v2** | Jina API | ✅ 1M/tháng | ✅ **Đã chọn** cho Phase 3 |
| `mixedbread-ai/mxbai-rerank-large-v2` | HF | ✅ | Open-source tốt nhất, nhưng cần RAM |
| `BAAI/bge-reranker-v2-gemma` | HF | ✅ | Gemma-2B, reasoning tốt |
| FlashRank | Open-source | ✅ | Siêu nhẹ, <10ms CPU |

## C. LLM miễn phí đáng dùng

| Provider | Model | Context | Ghi chú |
|---|---|---|---|
| Groq | `openai/gpt-oss-120b` | 128K | Cực nhanh, đang dùng làm primary |
| Groq | `meta-llama/llama-4-scout-17b-16e` | 10M | Long-context, thử nghiệm RAG không chunking |
| Google | `gemini-2.5-flash` | 1M | ✅ Fallback khi Groq 429 |
| Google | `gemini-2.5-flash-lite` | 1M | Rẻ nhất — hợp cho grading node |

## D. Papers cần đọc (theo thứ tự phase)

| Phase | Paper |
|---|---|
| 3 | **"Reciprocal Rank Fusion"** — Cormack et al., 2009 |
| 3 | **"Corrective Retrieval Augmented Generation"** — Yan et al., 2024 |
| 3 | **"Self-RAG: Learning to Retrieve, Generate, and Critique"** — Asai et al., ICLR 2024 |
| 3 | **"Precise Zero-Shot Dense Retrieval without Relevance Labels" (HyDE)** — Gao et al., 2022 |
| 4 | **"Adaptive-RAG: Question Complexity Routing"** — Jeong et al., NAACL 2024 |
| 4 | **"Dense X Retrieval: What Retrieval Granularity Should We Use?"** — Chen et al., 2024 |
| 5 | **"RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval"** — Sarthi et al., ICLR 2024 |
| 5 | **"GraphRAG: Local to Global"** — Microsoft, arxiv 2404.16130 *(đọc để biết khi nào KHÔNG dùng)* |
| — | **"Contextual Retrieval"** — Anthropic blog, 2024 |
| — | **"Late Chunking: Contextual Chunk Embeddings"** — JinaAI, arxiv 2409.04701 |
| — | **"BGE M3-Embedding: Multi-Lingual, Multi-Functionality"** — arxiv 2402.03216 |
| — | **"Modular RAG: LEGO-Like Reconfigurable Frameworks"** — arxiv 2407.21059 |
