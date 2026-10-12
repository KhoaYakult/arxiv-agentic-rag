# Giải thích thư mục `app/`

Tài liệu này đi từ **thư mục → file → từng hàm/class** trong `app/`. Nội dung bám đúng code hiện tại (sau khi hoàn tất backlog Phase 2, 2026-09-27). Muốn xem bức tranh kiến trúc và sơ đồ thì đọc `Architecture.md`; muốn biết *vì sao* thiết kế như vậy và các bug đã gặp thì đọc `Notebook.md`.

---

## 0. Bức tranh tổng thể

### Cây thư mục

```text
app/
├── __init__.py
├── config.py                  # Cấu hình toàn hệ thống (đọc .env)
├── ingestion/                 # PDF  → Markdown → Section → Chunk
│   ├── parser.py
│   └── chunker.py
├── indexing/                  # Embedding + Rerank
│   ├── embeddings.py
│   └── reranker.py
├── storage/                   # Đọc/ghi Postgres (Supabase)
│   └── repository.py
├── llm/                       # Khởi tạo LLM + prompt
│   ├── llm_factory.py
│   └── prompt_templates.py
├── agent/                     # Agent LangGraph (Corrective RAG)
│   └── rag_graph.py
└── api/                       # FastAPI: endpoint + schema
    ├── main.py
    ├── routes.py
    └── schemas.py
```

### Luồng 1 — Upload một bài báo (`POST /api/v1/upload`)

```text
routes.upload_paper()
  ├─ băm sha256 nội dung file ── trùng + status 'ready' ──► trả 200, dừng (không làm lại)
  ├─ lưu data/{paper_id}.pdf, ghi papers(status='processing'), trả 202 NGAY
  └─ (chạy nền) routes._process_and_index_paper()
        ├─ chunker.process_paper_ingestion()   # parser → split_parent_sections → create_child_chunks
        ├─ embeddings.embed_documents()        # Gemini, 768 chiều
        ├─ repository.insert_sections() + insert_chunks()
        └─ repository.set_paper_status('ready' | 'failed')
```

### Luồng 2 — Hỏi đáp (`POST /api/v1/ask`)

```text
routes.ask_agent() → rag_graph.ask()
   retrieve ──► grade ──(đủ tốt: yes)──────────────► generate ──► trả lời
      ▲           │
      └─ rewrite ◄┘ (no, và rewrite_count < 2)
   retrieve = embed_query → repository.hybrid_search (dense ∥ sparse → RRF) → RerankerManager.rerank (top 5)
```

### Quy ước chung của code trong `app/`

- Mọi module đều `from app.config import settings` thay vì tự đọc biến môi trường.
- Nhiều file có đoạn `sys.path.insert(0, BASE_DIR)` ở đầu: để chạy trực tiếp `python app/xxx/yyy.py` vẫn import được `app.*`.
- Mọi file có khối `if __name__ == "__main__":` là **bài test thủ công** gọi API/DB thật (khác với `tests/`, vốn không cần mạng).
- Import nặng (LLM, reranker, repository…) được đặt **bên trong hàm** (lazy import) để import module nhanh và tránh vòng phụ thuộc.

---

## 1. `app/__init__.py` và các `__init__.py` con

Mỗi thư mục (`agent`, `api`, `indexing`, `ingestion`, `llm`, `storage`) có 1 file `__init__.py` chỉ chứa dòng comment (riêng `storage/__init__.py` để trống). Chúng chỉ có tác dụng **đánh dấu thư mục là Python package** để `import app.xxx` hoạt động. Không có logic.

---

## 2. `app/config.py` — Cấu hình

**Vai trò:** nơi duy nhất đọc `.env` và giữ cấu hình dùng chung. Có **side effect khi import** (xem bên dưới), nên cần được import trước các thư viện đọc biến môi trường.

### Thực thi ngay khi import (không nằm trong hàm nào)

| Đoạn | Tác dụng |
|---|---|
| `BASE_DIR` | Thư mục gốc dự án (`app/..`). |
| `CACHE_DIR = BASE_DIR / "cache"` + `mkdir` | Tạo thư mục `cache/` trong repo. |
| `os.environ["HF_HOME"]`, `["OLLAMA_MODELS"]` | Chuyển cache của HuggingFace/Ollama vào `cache/` (không ghi ra ổ hệ thống). |
| `os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"` | Tắt cảnh báo symlink của HuggingFace trên Windows. |
| `settings = Settings()` | Tạo **instance cấu hình dùng chung toàn app**. |
| `if settings.hf_token: os.environ["HF_TOKEN"] = ...` | Đưa token vào môi trường để HuggingFace Hub không cảnh báo "unauthenticated". |
| `settings.data_dir.mkdir(...)` | Tự tạo thư mục `data/`. |

### `class Settings(BaseSettings)` (pydantic-settings)

Mỗi thuộc tính là một cấu hình, có thể ghi đè bằng biến môi trường/`.env` cùng tên (không phân biệt hoa thường).

| Thuộc tính | Mặc định | Ý nghĩa |
|---|---|---|
| `base_dir` | `BASE_DIR` | Thư mục gốc dự án. |
| `data_dir` | `BASE_DIR/"data"` | Nơi lưu PDF upload (`{paper_id}.pdf`) và cache chunk. |
| `ollama_llm_model` | `"qwen2.5:1.5b"` | Model Ollama khi chạy local. |
| `groq_model_name` | `"llama3-70b-8192"` | Model Groq dự phòng khi không hỏi được danh sách model từ Groq. |
| `chunk_size` | `800` | Số ký tự tối đa mỗi chunk. |
| `chunk_overlap` | `150` | Số ký tự gối đầu giữa 2 chunk liền kề. |
| `cohere_api_key`, `gemini_api_key`, `groq_api_key`, `hf_token` | `""` | API key các dịch vụ. Rỗng = coi như chưa cấu hình. |
| `database_url` | `""` | Chuỗi kết nối Postgres/Supabase (dùng **chung** cho `repository.py` và checkpointer của agent). |

`model_config`: đọc file `BASE_DIR/.env`, mã hoá UTF-8, `extra="ignore"` (biến thừa trong `.env` không gây lỗi).

Khối `__main__` in ra cấu hình hiện tại để kiểm tra nhanh.

---

## 3. `app/ingestion/` — Từ PDF đến Chunk

Biến file PDF thành các đoạn nhỏ sẵn sàng để embed. Luồng: `parser.py` → `chunker.py`, được nối lại bởi `chunker.process_paper_ingestion()`.

### 3.1. `app/ingestion/parser.py`

#### `parse_pdf_to_markdown(pdf_path) -> str`

Chuyển một PDF thành **một chuỗi Markdown**.

1. Kiểm tra file tồn tại, nếu không → `FileNotFoundError`.
2. **Đường chính:** `pymupdf4llm.to_markdown(..., page_chunks=True)`. Hàm này trả về `list[dict]` (mỗi phần tử là một trang), nên code nối các trang lại và **chèn marker `<!-- page:N -->` trước nội dung mỗi trang** (bỏ qua trang trống). Marker này là cách mang thông tin số trang xuống tầng chunk.
3. **Đường dự phòng:** nếu `pymupdf4llm` lỗi (ví dụ hết RAM trên server miễn phí), chuyển sang `fitz` (PyMuPDF thuần, rất nhẹ) đọc text thô từng trang. Nhánh này **không chèn marker**, nên `page_num` về sau sẽ là `None`.
4. Nếu cả hai đều lỗi → `RuntimeError`. Nếu kết quả rỗng/toàn khoảng trắng (PDF hỏng hoặc chỉ là ảnh scan) → `RuntimeError` rõ ràng thay vì đẩy dữ liệu rỗng đi tiếp.

Khối `__main__` parse thử file PDF đầu tiên trong `data/` và in 500 ký tự đầu.

### 3.2. `app/ingestion/chunker.py`

Thực hiện **Section-Based Parent-Child Chunking**: Markdown → `ParentSection` (theo mục lớn) → `ChildChunk` (đoạn nhỏ).

#### Dataclass

- **`ParentSection`** — một mục lớn của bài báo (Abstract, Introduction, Method…).
  Trường: `section_id` (vd `"sec_0"`), `section_name`, `text`.
- **`ChildChunk`** — đoạn nhỏ dùng để embed và tìm kiếm.
  Trường: `chunk_id` (`{paper_id}_chk_{n}`), `parent_section_id`, `parent_section_name`, `paper_id`, `text`, `is_table`, và 4 trường định vị:
  - `page_num` — trang PDF chứa ký tự đầu tiên của chunk (`None` nếu không có marker, hoặc chunk nằm trước marker đầu tiên của tài liệu).
  - `char_start`, `char_end` — vị trí trong text của section **sau khi đã bỏ marker** (để dành cho "small-to-big" sau này).
  - `level` — luôn `0` hiện nay; dành cho node tóm tắt RAPTOR ở Phase 5.

#### Hàm nội bộ

| Hàm | Làm gì |
|---|---|
| `_is_table_chunk(text) -> bool` | `True` nếu text có bảng Markdown (cả dòng `\|...\|` lẫn dòng phân cách `\|---\|`). Dùng để gắn `is_table`. |
| `_strip_page_markers(text) -> (text_sạch, breakpoints)` | Gỡ mọi `<!-- page:N -->` khỏi text. `breakpoints` là danh sách `(offset, page)` ghi vị trí (trong text đã làm sạch) nơi mỗi trang bắt đầu. Không có marker → trả nguyên text và danh sách rỗng. |
| `_page_at(breakpoints, offset) -> int \| None` | Tra số trang đang hiệu lực tại một vị trí ký tự. `None` nếu danh sách rỗng hoặc vị trí nằm trước marker đầu tiên. |
| `_find_split_point(text, target) -> int` | Tìm chỗ cắt gần `target` mà **không cắt giữa từ/câu**. Ưu tiên: (1) ranh giới đoạn `\n\n`, (2) ranh giới câu `. ! ?`, (3) khoảng trắng, (4) cắt cứng tại `target`. Mỗi bước tìm lùi (`rfind`) trong một vùng phía trước `target`. |

#### Hàm công khai

- **`split_parent_sections(markdown_text) -> list[ParentSection]`**
  Dò tiêu đề bằng regex đa dạng: `# Title`, `**Title**`, và kiểu IEEE đánh số (`I. TITLE`, `1. TITLE`). Với mỗi tiêu đề:
  - làm sạch tên (bỏ `#`, `*`, `_`; rút gọn mô tả dài sau `—`/`–`/`:`; tối đa 60 ký tự);
  - cắt phần text từ tiêu đề này đến tiêu đề kế tiếp;
  - **bỏ** section có tên < 3 ký tự hoặc nội dung < 30 ký tự (thường là rác do bắt nhầm công thức/số trang).
  Phần trước tiêu đề đầu tiên (tác giả, đơn vị…) thành section `"Header"`. Không tìm thấy tiêu đề nào → trả 1 section `"Full_Document"`.

- **`create_child_chunks(sections, paper_id, max_chars, overlap_chars) -> list[ChildChunk]`**
  Với mỗi section: gỡ marker trang → nếu text ≤ `max_chars` thì giữ nguyên làm **1 chunk**; ngược lại dùng **cửa sổ trượt**: cắt tại `_find_split_point`, rồi lùi `overlap_chars` và nhích tới đầu từ kế tiếp để chunk mới luôn bắt đầu bằng từ trọn vẹn.
  **Điểm tinh tế:** biến `current_page` được **mang xuyên qua các section**. Lý do: marker trang thường nằm ngay *trước* tiêu đề nên bị gán vào cuối section liền trước; section kế tiếp (thực sự bắt đầu ở trang đó) không có marker nào ở vị trí 0. Nếu không mang trang sang thì phần lớn chunk bị `page_num=None`. `current_page` bắt đầu là `None` và **không bao giờ mặc định là 1** — nội dung trước marker đầu tiên giữ `None` trung thực.

- **`process_paper_ingestion(pdf_path, paper_id) -> (sections, chunks)`**
  Hàm bọc cả pipeline: `parse_pdf_to_markdown` → `split_parent_sections` → `create_child_chunks`, rồi in báo cáo (số section, số chunk, danh sách section, cờ `[TABLE]`). **Đây là hàm mà `routes.py` gọi.**

- **`save_chunks_to_file(chunks, paper_id) -> Path`** / **`load_chunks_from_file(paper_id) -> list \| None`**
  Ghi/đọc danh sách chunk dưới dạng JSON ở `data/chunks_cache/{paper_id}_chunks.json`. **Hiện upload không còn dùng** (cache chỉ lưu `ChildChunk`, không lưu `ParentSection`, nên dùng lại sẽ làm mất dữ liệu `sections`). Hai hàm này cũng chưa lưu 4 trường định vị mới (`page_num`…). Chỉ còn được gọi trong khối `__main__`.

---

## 4. `app/indexing/` — Embedding và Rerank

### 4.1. `app/indexing/embeddings.py`

Biến text thành vector bằng Gemini (`gemini-embedding-001`, cắt còn **768 chiều** nhờ MRL — Matryoshka Representation Learning).

Hằng số: `EMBEDDING_DIM = 768`; `_GEMINI_FREE_TIER_BATCH = 100`; `_GEMINI_FREE_TIER_COOLDOWN_SEC = 61`.
Lý do hai hằng số cuối: quota free tier của Gemini tính theo **số văn bản được embed mỗi phút**, không phải số lần gọi HTTP — nên batching không đủ, phải chủ động nghỉ giữa các batch.

#### `class GeminiEmbeddingProvider`

| Phương thức | Làm gì |
|---|---|
| `__init__(api_key="", dim=768)` | Lấy key từ tham số hoặc `settings.gemini_api_key`; thiếu key → `ValueError`. Tạo client `GoogleGenerativeAIEmbeddings`. |
| `embed_documents(texts) -> list[list[float]]` | Embed danh sách chunk **lúc index** (`task_type=RETRIEVAL_DOCUMENT`). Tự chia batch ≤ 100; **chủ động `sleep(61s)` giữa các batch** (paper 182 chunk ⇒ 2 batch ⇒ chờ ~61s). Danh sách rỗng → `[]`. |
| `_embed_batch(texts)` | Gọi API cho 1 batch; có `@retry` (tối đa 3 lần, chờ lũy tiến 1–10s) cho lỗi mạng/429 lẻ tẻ. |
| `embed_query(text) -> list[float]` | Embed **một câu hỏi lúc tìm kiếm** (`task_type=RETRIEVAL_QUERY`); cũng có `@retry`. |

Dùng `task_type` **bất đối xứng** (document khác query) để đúng bài toán retrieval.

#### `get_embedding_provider() -> GeminiEmbeddingProvider`

Factory có `@lru_cache(maxsize=1)` → toàn app dùng chung 1 provider. Khối `__main__` gọi thử `embed_query`/`embed_documents`.

### 4.2. `app/indexing/reranker.py`

Giai đoạn 2 của retrieval: nhận ~20 ứng viên từ hybrid search, trả về top 5 chính xác nhất. Dùng **cross-encoder / reranker** (đọc cả cặp câu hỏi–đoạn văn cùng lúc nên chính xác hơn bi-encoder dùng để embed, nhưng chậm hơn nên chỉ chạy trên tập nhỏ).

#### `class RerankerManager`

- Hằng số `LOCAL_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"` (nhẹ, chạy được trên CPU).

| Phương thức | Làm gì |
|---|---|
| `__init__()` | Chọn `self.mode`: có `COHERE_API_KEY` → `"cohere"`, ngược lại `"local"`. In ra chế độ đang dùng. |
| `_get_cross_encoder()` | **Lazy load** model CrossEncoder (`max_length=512` token) ở lần dùng đầu tiên, tránh load model nặng ngay khi import. |
| `rerank(query, candidates, top_k=5) -> list[dict]` | Cổng vào: danh sách rỗng → `[]`; còn lại gọi `_rerank_cohere` hoặc `_rerank_local` theo `mode`. Kết quả mỗi phần tử có thêm `rerank_rank`, `rerank_score`. |
| `_rerank_local(...)` | Chấm điểm từng cặp `(query, text)` bằng CrossEncoder, sắp xếp giảm dần, lấy `top_k`. **Không cắt text theo ký tự** (tokenizer của model tự cắt theo token — từng có bug cắt 512 *ký tự* làm mất ~65% chunk). Làm việc trên bản sao, không sửa list gốc. |
| `_rerank_cohere(...)` | Gọi Cohere Rerank (`rerank-english-v3.0`), mỗi text cắt tối đa 2048 ký tự (giới hạn cứng của API). Nếu chưa cài thư viện `cohere` → in cảnh báo và **tự rơi về `_rerank_local`**. |

---

## 5. `app/storage/repository.py` — Lớp truy cập Postgres

**Vai trò:** nguồn sự thật duy nhất cho `papers` / `sections` / `chunks`, dùng `asyncpg` (chỉ hỗ trợ async nên mọi hàm đều `async`). Schema nằm ở `db/schema.sql` (4 bảng: `papers`, `sections`, `chunks`, `paper_cards`; `paper_cards` chưa dùng).

### Quản lý kết nối

| Hàm | Làm gì |
|---|---|
| `_register_vector_codec(conn)` | Dạy asyncpg đổi qua lại `list[float]` ↔ kiểu `vector` của Postgres. **Bắt buộc `schema="extensions"`** vì Supabase cài pgvector vào schema `extensions`, không phải `public` (thiếu sẽ lỗi `unknown type: public.vector`). Được truyền làm `init=` cho pool. |
| `get_pool()` | Pool kết nối **lazy singleton** (`min_size=1, max_size=5`). Thiếu `DATABASE_URL` → `ValueError`. |
| `close_pool()` | Đóng pool khi app shutdown (gọi trong `lifespan` của FastAPI). |

### Bảng `papers`

| Hàm | Làm gì |
|---|---|
| `upsert_paper(paper_id, title, filename, file_hash=None, num_pages=None, status="processing")` | `INSERT ... ON CONFLICT (paper_id) DO UPDATE` — tạo mới hoặc cập nhật (cho phép upload lại cùng `paper_id`). |
| `set_paper_status(paper_id, status, num_chunks=None)` | Cập nhật trạng thái (`processing`/`ready`/`failed`); có `num_chunks` thì cập nhật luôn. |
| `get_paper_by_hash(file_hash)` | Tìm paper theo hash nội dung — phục vụ chống upload trùng. Trả `dict` hoặc `None`. |
| `clear_stale_file_hash(paper_id)` | Đặt `file_hash = NULL` cho paper **chưa `ready`**. Cần vì cột `file_hash` là `UNIQUE` trên toàn bảng: paper cũ đang `processing`/`failed` vẫn "giữ" hash và sẽ làm insert paper mới bị `UniqueViolationError`. Điều kiện `status != 'ready'` được Postgres kiểm tra lại ngay lúc UPDATE nên không thể gỡ nhầm hash của paper vừa kịp thành `ready`. |
| `get_paper(paper_id)` | Lấy 1 paper (`dict` hoặc `None`). |
| `list_papers()` | Chỉ trả paper `status='ready'`, mới nhất trước (để UI không cho chọn paper chưa index xong). |
| `delete_paper(paper_id)` | Xoá paper; `sections`/`chunks`/`paper_cards` tự xoá theo nhờ `ON DELETE CASCADE`. |

### Bảng `sections` và `chunks`

- **`insert_sections(paper_id, sections) -> dict[str, int]`** — ghi các `ParentSection` trong **1 transaction**, trả về map `{section_id chuỗi (vd "sec_0") → khoá chính int}`; `insert_chunks` dùng map này làm khoá ngoại.
- **`insert_chunks(paper_id, chunks, embeddings, section_pk_map)`** — ghi `ChildChunk` + embedding trong **1 transaction** (kể cả `page_num`, `char_start`, `char_end`, `level`). Cột `fts` do Postgres tự sinh. Số chunk khác số embedding → `ValueError`. Upsert theo `chunk_id`.

### Hybrid search

| Thành phần | Làm gì |
|---|---|
| `reciprocal_rank_fusion(dense_results, bm25_results, k=60)` | Gộp 2 danh sách xếp hạng bằng công thức `Σ 1/(k + rank)` (Cormack et al., 2009). Tài liệu xuất hiện ở cả hai danh sách được cộng điểm cả hai. Không quan tâm danh sách đến từ đâu — vì thế khi chuyển từ BM25 sang Postgres FTS vẫn dùng nguyên được (tên khoá `bm25_rank` được giữ để khỏi sửa hàm). Thêm `rrf_score`, `rrf_rank` vào mỗi kết quả. |
| `_DENSE_SEARCH_SQL` | Lọc `paper_id`, sắp xếp theo `embedding <=> $query` (khoảng cách cosine pgvector, có chỉ mục HNSW), join `sections` để lấy `parent_section_name`. |
| `_SPARSE_SEARCH_SQL` | Lọc `paper_id` và `fts @@ websearch_to_tsquery('english', ...)`, xếp theo `ts_rank_cd`. |
| `dense_search(paper_id, query_embedding, top_k=20)` | Chạy SQL dense, gắn `dense_rank` (1, 2, 3…). |
| `sparse_search(paper_id, query_text, top_k=20)` | Chạy SQL sparse, gắn `bm25_rank`. Lưu ý: `websearch_to_tsquery` ngầm hiểu **AND** giữa các từ nên câu hỏi dài có thể không khớp đoạn chỉ chứa một vài từ. |
| `hybrid_search(paper_id, query_text, query_embedding, top_k=20)` | Chạy dense và sparse **song song** (`asyncio.gather`), gộp bằng RRF, trả về `top_k` ứng viên **chưa rerank**. |

---

## 6. `app/llm/` — LLM và Prompt

### 6.1. `app/llm/llm_factory.py`

**Quy tắc:** các module khác chỉ được lấy LLM qua `get_llm()`; không import `ChatGroq`/`ChatGoogleGenerativeAI`/`ChatOllama` trực tiếp.

| Thành phần | Làm gì |
|---|---|
| `_GROQ_PREFERRED_MODELS` | Danh sách model Groq theo thứ tự ưu tiên (mạnh trước, nhẹ sau). |
| `_pick_best_groq_model(api_key) -> str` | Hỏi Groq danh sách model **đang thực sự hoạt động**, chọn model đầu tiên trong danh sách ưu tiên mà Groq còn có. Không có model ưu tiên nào → lấy model đầu theo bảng chữ cái. Lỗi mạng/key → rơi về `settings.groq_model_name`. Có `@lru_cache` để không gọi API Groq lặp lại. |
| `_build_llm(provider, temperature, max_tokens)` | Dựng đúng **một** LLM cho một provider (`"groq"`, `"gemini"` → `gemini-2.0-flash`, `"ollama"`). Thiếu key → `ValueError`; provider lạ → `ValueError`. Không tự dò, không fallback. |
| `get_llm(provider=None, temperature=0.2, max_tokens=5096)` | Hàm công khai (có `@lru_cache`). `provider=None` → tự dò theo key: **Groq → Gemini → Ollama**. Khi tự dò ra Groq *và* có `GEMINI_API_KEY`, LLM trả về được bọc `.with_fallbacks([gemini])`: Groq lỗi lúc chạy (429, timeout, model bị gỡ) sẽ tự chuyển sang Gemini. Nếu truyền `provider="groq"` rõ ràng thì **không** gắn fallback (vì đó là lựa chọn có chủ đích). |

Khối `__main__` chạy 4 bài test thủ công (khởi tạo, hỏi đơn giản, giả lập RAG, xem token usage).

### 6.2. `app/llm/prompt_templates.py`

Ba chuỗi prompt (dùng cú pháp `{biến}` của LangChain):

| Hằng số | Biến cần truyền | Dùng ở | Nhiệm vụ |
|---|---|---|---|
| `RAG_ANSWER_TEMPLATE` | `context`, `chat_history`, `question` | `generate_node` | Tổng hợp câu trả lời **chỉ dựa trên context**; thiếu thông tin thì nói rõ không tìm thấy; trả lời cùng ngôn ngữ với câu hỏi (Việt/Anh). |
| `GRADE_DOCS_TEMPLATE` | `context`, `question` | `grade_node` | Bắt LLM làm "giám khảo": chỉ trả `yes`/`no` xem context có đủ để trả lời không (yêu cầu nghiêm khắc). |
| `REWRITE_QUERY_TEMPLATE` | `question` | `rewrite_node` | Viết lại câu hỏi cụ thể hơn, mở rộng viết tắt, thêm thuật ngữ kỹ thuật; chỉ trả đúng câu hỏi mới. |

File này không có hàm; khối `__main__` in các biến của từng template và thử nối với LLM thật.

---

## 7. `app/agent/rag_graph.py` — Agent Corrective RAG (LangGraph)

### Trạng thái và hằng số

- **`AgentState` (TypedDict)** — dữ liệu chạy qua đồ thị: `question`, `paper_id`, `retrieved_chunks`, `grade`, `rewrite_count`, `answer`, `messages`. Riêng `messages` dùng reducer `add_messages` nên mỗi lượt được **nối thêm** vào lịch sử thay vì ghi đè.
- `MAX_REWRITES = 2` — tối đa viết lại câu hỏi 2 lần.
- `FIRST_STAGE_K = 20` — số ứng viên lấy từ hybrid search trước khi rerank còn 5.

### Các node (đều `async`)

| Node | Làm gì |
|---|---|
| `retrieve_node` | Embed câu hỏi (`embed_query`) → `repository.hybrid_search(top_k=20)` → `RerankerManager().rerank(top_k=5)`. Ghi vào `retrieved_chunks`. |
| `grade_node` | Ghép các chunk (mỗi chunk cắt 400 ký tự) thành context, hỏi LLM theo `GRADE_DOCS_TEMPLATE`. **Một lần gọi cho cả batch** (không chấm từng chunk). Ghi `grade` = `"yes"` nếu câu trả lời chứa "yes", ngược lại `"no"`. |
| `rewrite_node` | Gọi LLM theo `REWRITE_QUERY_TEMPLATE`, thay `question` bằng bản viết lại, tăng `rewrite_count` thêm 1. |
| `generate_node` | Lấy **6 tin nhắn gần nhất** làm lịch sử, ghép context từ các chunk, gọi LLM theo `RAG_ANSWER_TEMPLATE`. Trả về `answer` và thêm cặp (`HumanMessage` câu hỏi, `AIMessage` câu trả lời) vào `messages`. |

### Cạnh điều kiện

**`decide_after_grade(state) -> str`** — sau `grade`: `yes` → `"generate"`; `no` mà `rewrite_count < MAX_REWRITES` → `"rewrite"`; hết lượt rewrite → vẫn `"generate"` (trả lời với những gì tìm được).

Đồ thị: `START → retrieve → grade → (generate → END | rewrite → retrieve → …)`.

### Dựng đồ thị và bộ nhớ hội thoại

| Hàm | Làm gì |
|---|---|
| `_get_checkpointer()` | Tạo `AsyncPostgresSaver` lưu lịch sử chat **trong cùng Postgres** với papers/chunks (sống sót qua redeploy). Dùng một `psycopg_pool.AsyncConnectionPool(min_size=1, max_size=1)` riêng vì thư viện chỉ hỗ trợ driver `psycopg`, không hỗ trợ `asyncpg`; pool tự kết nối lại nếu kết nối rớt (`check_connection`), và giữ tổng ngân sách kết nối ở mức 6 (5 asyncpg + 1). `prepare_threshold=0` giữ cho an toàn nếu sau này đổi sang pooler chế độ *transaction*. Thiếu `DATABASE_URL` → `ValueError`. Không có `except` nuốt lỗi rồi lùi về bộ nhớ RAM (bài học bug #7); nếu `setup()` lỗi thì đóng pool rồi raise lại. |
| `close_checkpointer()` | Đóng pool checkpointer và xoá app đã cache; được gọi trong `lifespan` của `main.py`. |
| `_build_rag_app()` | Khai báo các node/cạnh và `compile(checkpointer=...)`. |
| `_get_rag_app()` | **Lazy singleton có khoá** (`asyncio.Lock`, kiểm tra hai lần): lần `ask()` đầu tiên mới build, các request đồng thời chỉ build một lần. Hệ quả: `DATABASE_URL` sai chỉ lộ ra ở lần `/ask` đầu, không phải lúc khởi động. |

### Hàm công khai duy nhất

**`ask(question, paper_id, thread_id="default") -> dict`** — điểm vào mà các module khác phải dùng (không gọi node trực tiếp). Cùng `thread_id` thì agent nhớ các lượt trước. Trả về toàn bộ `AgentState` cuối cùng.

Khối `__main__` chạy thử 2 lượt hỏi trên cùng một `thread_id` để kiểm tra bộ nhớ (lượt 2 phải có 4 messages).

---

## 8. `app/api/` — FastAPI

### 8.1. `app/api/main.py` — Điểm khởi động server

| Thành phần | Làm gì |
|---|---|
| `lifespan(app)` | Context manager: khi app **tắt** thì gọi `close_checkpointer()` và `repository.close_pool()` để đóng sạch kết nối Postgres. |
| `app = FastAPI(...)` | Tạo ứng dụng (title, mô tả hiển thị trong Swagger, `docs_url=/docs`, `redoc_url=/redoc`). |
| `CORSMiddleware` | Cho phép Streamlit (localhost:8501, `*.streamlit.app`) gọi API. Hiện còn `"*"` (mở cho dev, nên thu hẹp khi production). |
| `app.include_router(router, prefix="/api/v1")` | Gắn toàn bộ endpoint trong `routes.py` dưới tiền tố `/api/v1`. |
| `root()` | `GET /` chuyển hướng sang `/docs`. |

Chạy server: `uvicorn app.api.main:app --reload --port 8000` (hoặc `make run`).

### 8.2. `app/api/schemas.py` — Cấu trúc dữ liệu vào/ra (Pydantic)

Quy ước tên: `*Request` = client gửi lên, `*Response` = server trả về. Pydantic tự kiểm tra kiểu và sinh tài liệu Swagger.

| Class | Dùng ở đâu | Trường chính |
|---|---|---|
| `UploadResponse` | `POST /upload` | `paper_id`, `title`, `status` (`processing`/`ready`/`failed`), `num_chunks`, `message`. `processing` ứng với HTTP 202, `ready` ứng với 200 (trùng file). |
| `AskRequest` | `POST /ask` (đầu vào) | `question` (3–1000 ký tự), `paper_id`, `thread_id` (tuỳ chọn). |
| `SourceChunk` | trong `AskResponse` | `chunk_id`, `section`, `content_preview`, `page_num` (có thể `None`). |
| `AskResponse` | `POST /ask` (đầu ra) | `answer`, `thread_id`, `grade` (`yes`/`no`), `rewrite_count`, `sources`. |
| `PaperInfo` | trong `PapersResponse` | `paper_id`, `title`, `num_chunks`. |
| `PapersResponse` | `GET /papers` | `papers`, `total`. |
| `PaperStatusResponse` | `GET /papers/{id}/status` | `paper_id`, `title`, `status`, `num_chunks`. |
| `HealthResponse` | `GET /health` | `status` (`ok`/`error`), `version`, `message`. |

### 8.3. `app/api/routes.py` — Các endpoint

Tất cả nằm dưới `/api/v1`.

| Endpoint | Hàm | Làm gì |
|---|---|---|
| `GET /health` | `health_check()` | Trả `status="ok"` để UI/load balancer kiểm tra server sống (không kiểm tra DB). |
| `GET /papers` | `list_papers()` | Danh sách paper đã `ready` (cho dropdown trên UI). |
| `POST /upload` | `upload_paper()` | Xem chi tiết bên dưới. |
| `GET /papers/{paper_id}/status` | `get_paper_status()` | Cho client **poll** sau upload; khác `/papers` ở chỗ trả cả paper `processing`/`failed`. Không có → 404. |
| `DELETE /papers/{paper_id}` | `delete_paper()` | Xoá khỏi Postgres (cascade) và xoá file `data/{paper_id}.pdf` nếu còn. Trả 204; không có → 404. |
| `POST /ask` | `ask_agent()` | Xem bên dưới. |

#### `upload_paper()` — luồng chi tiết

1. Chỉ nhận tên file `.pdf`, sai → 400.
2. Đọc toàn bộ nội dung, tính `sha256`.
3. `get_paper_by_hash`: nếu trùng và paper đó đã `ready` → **trả 200** kèm thông tin paper cũ (`paper_id` gốc), không xử lý lại (tiết kiệm quota Gemini).
4. Nếu trùng nhưng paper cũ đang `processing`/`failed` → `clear_stale_file_hash` để gỡ "quyền giữ hash" rồi xử lý như upload mới.
5. Không truyền `paper_id` → tự sinh slug từ tên file.
6. Lưu file ở `data/{paper_id}.pdf` — **luôn dùng `paper_id`, không dùng tên file client gửi** (từng có bug: hai paper trùng tên file ghi đè nhau và xoá nhầm file).
7. `upsert_paper(status="processing")`. Nếu dính `UniqueViolationError` (race hiếm) thì xoá file vừa ghi và trả 500 để không để lại file mồ côi.
8. Đăng ký `BackgroundTasks` chạy `_process_and_index_paper`, **trả 202 ngay**.

#### Hàm phụ trong `routes.py`

| Hàm | Làm gì |
|---|---|
| `_process_and_index_paper(pdf_path, paper_id)` | Chạy **nền** sau khi đã trả 202: `process_paper_ingestion` → `embed_documents` → `insert_sections` → `insert_chunks` → `set_paper_status("ready", num_chunks)`. Mọi lỗi được bắt và ghi `status='failed'` (không raise, vì không còn request nào để nhận lỗi). |
| `_should_reuse_by_hash(existing) -> bool` | `True` chỉ khi có paper trùng hash **và** `status == 'ready'`. |
| `_should_clear_stale_hash(existing) -> bool` | `True` khi có paper trùng hash nhưng **không** dùng lại được (đang `processing`/`failed`). |

Hai hàm `_should_*` là hàm thuần (không đụng DB) nên có unit test trong `tests/test_routes.py`.

#### `ask_agent()` — luồng chi tiết

1. Kiểm tra paper tồn tại, không có → 404.
2. `thread_id` không gửi → server tự sinh (`auto_xxxxxxxx`).
3. Gọi `rag_graph.ask(...)`; lỗi nào cũng bọc thành 500 `"Loi Agent: ..."`.
4. Lấy câu trả lời từ tin nhắn cuối trong `messages`, dựng danh sách `sources` từ `retrieved_chunks` (preview 150 ký tự đầu + `page_num`).
5. Trả `AskResponse`.

---

## 9. Bảng tra nhanh: ai gọi ai

| Module | Được gọi bởi |
|---|---|
| `config.settings` | gần như mọi module |
| `parser.parse_pdf_to_markdown` | `chunker.process_paper_ingestion` |
| `chunker.process_paper_ingestion` | `routes._process_and_index_paper` |
| `embeddings.get_embedding_provider` | `routes._process_and_index_paper` (index), `rag_graph.retrieve_node` (query) |
| `repository.insert_sections/insert_chunks/set_paper_status` | `routes._process_and_index_paper` |
| `repository.hybrid_search` | `rag_graph.retrieve_node` |
| `RerankerManager.rerank` | `rag_graph.retrieve_node` |
| `llm_factory.get_llm` | `grade_node`, `rewrite_node`, `generate_node` |
| `prompt_templates.*` | `grade_node`, `rewrite_node`, `generate_node` |
| `rag_graph.ask` | `routes.ask_agent` |
| `rag_graph.close_checkpointer`, `repository.close_pool` | `main.lifespan` |
| `routes.router` | `main.app` |
