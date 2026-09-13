# 🗺️ ROADMAP — ArXiv Agentic RAG → Production-Grade

> **Phiên bản:** 3.0 · **Cập nhật:** 2026-09-12
> **Trạng thái:** MVP chạy được nhưng có 6 bug đã xác minh + không sống sót qua redeploy.
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

## 2. Sáu bug đã xác minh — thứ tự xử lý

| # | Bug | Vị trí | Quyết định |
|---|---|---|---|
| 1 | `to_markdown(page_chunks=True)` trả `list[dict]` nhưng hàm typed `-> str`, gọi `len()` rồi return → downstream regex `TypeError` | `app/ingestion/parser.py:43` | **Sửa ngay**, nhưng **giữ** `page_chunks=True` và trả `list[dict]` — Phase 2 cần page number. Đừng revert về `str`. |
| 2 | `_find_split_point` fallback #3: `space_pos = min(50, int(target*0.08))` trả index gần **đầu** chuỗi thay vì `rfind(" ")` gần `target` | `app/ingestion/chunker.py:89-91` | **Sửa ngay**, 1 dòng: `text.rfind(" ", int(target*0.9), target)`. |
| 3 | `sources` **luôn rỗng**: đọc `result.get("documents")` nhưng `AgentState` chỉ có `retrieved_chunks` (dict, không phải `Document`) | `app/api/routes.py:275-283` | **Sửa ngay** — ảnh hưởng trực tiếp demo. |
| 4 | Nhánh Gemini không bao giờ chạy khi có GROQ key; `_pick_best_groq_model()` gọi `models.list()` mỗi lần `get_llm()` (1 round-trip mạng / node); `langchain-google-genai` thiếu trong requirements | `app/llm/llm_factory.py:119-122, 138` | **Sửa ngay** — `@lru_cache`, fallback runtime Groq→Gemini khi 429, thêm dep. |
| 5 | `_rerank_local` cắt `text[:512]` — 512 **ký tự** không phải token (mất ~65% chunk 800 ký tự); mutate `candidates` in-place | `app/indexing/reranker.py:93-114` | **Sửa 2 dòng ngay.** Phase 3 thay bằng Jina rerank API. |
| 6 | `build_index()` reset `self._chunks_meta = []` → upload paper B **xoá sạch** BM25 của paper A, trong khi Chroma vẫn giữ → hybrid âm thầm tụt về dense-only | `app/indexing/bm25_store.py:111` | **Chỉ vá tạm** (~10 dòng: load meta cũ, merge theo `chunk_id`, rebuild). File này **bị xoá hoàn toàn ở Phase 2** — đừng refactor tử tế. |

---

## Phase 1 — Cầm máu + nền kỹ thuật (tuần 1–2)

**Mục tiêu:** pipeline chạy lại end-to-end; repo trông như repo của kỹ sư.
**CV claim:** *"engineering hygiene: typed config, pinned deps, CI, test suite"*

### Việc cần làm
- [ ] Sửa bug #1, #2, #3, #4, #5; vá tạm #6.
- [ ] Thêm `pyproject.toml` (ruff + pytest config), `.pre-commit-config.yaml`, `Makefile` (`make test/lint/run/eval`), `.dockerignore`.
- [ ] Pin toàn bộ `requirements.txt`. Thêm `huggingface_hub`, `numpy` (đang import nhưng **thiếu khai báo**), `langchain-google-genai`, `tenacity`. Xoá `upstash-redis`, `langgraph-checkpoint-redis`.
- [ ] `Dockerfile`: `CMD ["sh","-c","uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]` (kết thúc 4 commit churn về port), non-root user, `HEALTHCHECK`, multi-stage.
- [ ] `tests/` cho 4 hàm thuần không cần network: `split_parent_sections`, `_find_split_point`, `reciprocal_rank_fusion` (`hybrid_retriever.py:41`), `tokenize` (`bm25_store.py:36`).
- [ ] GitHub Actions: ruff + pytest.
- [ ] `README.md` (hiện **không tồn tại**) — sơ đồ kiến trúc + cách chạy.

### Kiểm chứng
`make test` xanh · CI xanh · `docker run -e PORT=9000` lên đúng cổng · upload 1 PDF → `/ask` trả `sources` **khác rỗng**.

### Kiến thức cần học
pytest fixtures/parametrize · ruff rule sets · Docker multi-stage & layer caching · 12-factor config.

---

## Phase 2 — Supabase là nguồn sự thật duy nhất (tuần 3–6) ⭐ *phase quan trọng nhất*

**Mục tiêu:** dữ liệu sống sót qua redeploy; chunk có page number; parent section **thật sự tồn tại** (hiện `ParentSection` được tạo rồi vứt đi — "parent-child" chỉ có trên tên).
**CV claim:** *"migrated from ephemeral file-based stores to a single Postgres+pgvector backend; zero data loss on deploy"*

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
- [ ] `ChildChunk` thêm `page_num`, `char_start`, `char_end`, `level`.
- [ ] `parser.py` trả `list[dict]` per-page có offset; `split_parent_sections` nhận input page-aware để map heading → trang.
- [ ] Viết `app/storage/repository.py` (asyncpg/SQLAlchemy) thay `_load_registry`/`_save_registry` (`routes.py:51-62`), `VectorStoreManager`, `BM25StoreManager` → **xoá `vector_store.py`, `bm25_store.py`, toàn bộ pickle**.
- [ ] `EmbeddingProvider` mới (Gemini) có retry + exponential backoff + timeout (`tenacity`). Hiện `HuggingFaceAPIEmbeddings` **không có retry nào** — 1 batch lỗi là abort cả ingest.
- [ ] `/upload` → `BackgroundTasks`, trả `202` + `status`, poll qua `GET /papers/{id}/status`. Hiện là thân **sync trong `async def`** → block event loop suốt parse+embed.
- [ ] Thêm `DELETE /papers/{id}` (cascade). Hiện chỉ có `reset_db()` xoá **tất cả** paper.
- [ ] Dense + sparse chạy song song bằng `asyncio.gather` (hiện tuần tự). Singleton retriever qua FastAPI `lifespan` (hiện mỗi `HybridRetriever()` re-init Chroma + HF client).
- [ ] Chuyển checkpointer SQLite → `AsyncPostgresSaver`.

### Kiểm chứng
Upload 3 paper → `railway redeploy` → `/papers` vẫn đủ 3, `/ask` trên paper đầu vẫn hit **cả** dense lẫn sparse · integration test với Postgres service container trong CI · **assert: sau khi upload paper B, số sparse-hit của paper A không đổi** (chính là bug #6).

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
