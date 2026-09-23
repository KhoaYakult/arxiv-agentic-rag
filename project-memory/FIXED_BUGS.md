# Fixed Bugs — đừng sửa lại theo hướng cũ

Danh sách chỉ **thêm**, không xoá. Mỗi bug: triệu chứng → nguyên nhân → đã sửa thế nào → vì sao đừng quay lại cách cũ. Chi tiết đầy đủ + rationale kiến trúc ở `docs/ROADMAP.md` mục 2.

Tất cả đã sửa trong Phase 1 (commit `f535a4e`, `0277d86`), verify bằng test + import smoke-test thật (venv sạch).

---

### #1 — `parser.py` trả sai kiểu khi `page_chunks=True`
- **Triệu chứng:** `TypeError` ở downstream regex khi parse markdown.
- **Nguyên nhân:** `pymupdf4llm.to_markdown(..., page_chunks=True)` trả `list[dict]` (mỗi trang 1 dict), code cũ xử lý như `str`.
- **Đã sửa:** join lại thành 1 chuỗi markdown, chèn marker `<!-- page:N -->` giữa các trang.
- **Đừng:** revert về gọi `to_markdown()` không có `page_chunks=True` — Phase 2 cần marker số trang này để trích `page_num`.

### #2 — `chunker._find_split_point` fallback #3 cắt sai vị trí
- **Triệu chứng:** chunk có thể bị cắt ngay gần đầu chuỗi thay vì gần `target`.
- **Nguyên nhân:** `space_pos = min(50, int(target * 0.08))` — đây là 1 con số cố định, không phải kết quả tìm kiếm.
- **Đã sửa:** `text.rfind(" ", int(target * 0.08), target)` — tìm khoảng trắng thật trong vùng đó.
- **Đừng:** dùng số cố định làm "vị trí cắt" — luôn phải là kết quả của `rfind`/`find` trên `text`. Có test hồi quy: `tests/test_chunker.py::test_fallback_space_is_near_target_not_near_start`.

### #3 — `/ask` trả `sources` luôn rỗng
- **Triệu chứng:** UI không bao giờ hiện được nguồn trích dẫn.
- **Nguyên nhân:** `routes.py` đọc `result.get("documents")` — key này **không tồn tại** trong `AgentState` (thực tế là `retrieved_chunks`, list of dict chứ không phải LangChain `Document`).
- **Đã sửa:** đọc đúng `result["retrieved_chunks"]`, map field `chunk_id`/`parent_section_name`/`text`.
- **Đừng:** giả định `AgentState` trả về LangChain `Document` object ở bất kỳ đâu — nó là plain dict xuyên suốt pipeline retrieval.

### #4 — LLM factory: Gemini fallback chết, cache thiếu, dep thiếu
- **Triệu chứng:** khi có cả `GROQ_API_KEY` và `GEMINI_API_KEY`, nhánh Gemini không bao giờ chạy được (kể cả khi Groq lỗi); mỗi lần `get_llm()` tốn 1 round-trip mạng gọi `Groq().models.list()`.
- **Nguyên nhân:** auto-detect chỉ chọn 1 provider tĩnh lúc khởi tạo, không có cơ chế fallback runtime; `_pick_best_groq_model()` không cache; `langchain-google-genai` chưa khai báo trong `requirements.txt` (nhánh Gemini sẽ `ImportError` nếu chạy tới).
- **Đã sửa:** `@lru_cache` cho cả `get_llm()` và `_pick_best_groq_model()`; khi provider tự động chọn là Groq và có sẵn Gemini key, wrap bằng `.with_fallbacks([gemini_llm])` (LangChain runnable fallback) để tự chuyển sang Gemini lúc invoke nếu Groq lỗi (429/timeout/model bị gỡ).
- **Đừng:** gọi thẳng `ChatGroq`/`ChatGoogleGenerativeAI`/`ChatOllama` ở module khác — luôn qua `get_llm()`.

### #5 — Reranker cắt chunk theo ký tự, mutate list gốc
- **Triệu chứng:** CrossEncoder chấm điểm dựa trên phần đầu chunk bị cắt cụt (~65% nội dung 1 chunk 800 ký tự bị bỏ).
- **Nguyên nhân:** code cũ tự cắt `text[:512]` theo **ký tự** trước khi đưa vào model, trong khi `CrossEncoder(max_length=512)` đã tự cắt theo **token** ở tầng tokenizer rồi — cắt 2 lần, lần đầu (theo ký tự) sai và thừa.
- **Đã sửa:** bỏ cắt ký tự thủ công, để tokenizer tự xử lý; đồng thời không mutate `candidates` gốc nữa mà tạo bản sao (`{**candidate, ...}`).
- **Đừng:** thêm lại bất kỳ `text[:N]` nào trước khi đưa text vào model rerank/embedding — luôn để model/tokenizer tự truncate, trừ khi có lý do cụ thể khác (ví dụ giới hạn API như Cohere `text[:2048]` — đó là giới hạn cứng của API, không phải lỗi).

### #6 — BM25 xoá sạch dữ liệu paper cũ khi upload paper mới
- **Triệu chứng:** hybrid search cho các paper cũ âm thầm tụt về dense-only sau khi upload thêm paper mới.
- **Nguyên nhân:** `build_index()` làm `self._chunks_meta = []` rồi build lại **chỉ từ chunks của paper đang upload** — trong khi ChromaDB (dense) vẫn giữ nguyên tất cả paper cũ.
- **Đã sửa (vá tạm, không phải fix triệt để):** merge theo `chunk_id` với corpus đã load từ disk trong `__init__`, thay vì reset về rỗng.
- **Đừng:** "dọn dẹp" đoạn merge này về lại 1 dòng rebuild đơn giản — nhìn tưởng thừa nhưng chính là fix. **Và đừng đầu tư thêm vào file `bm25_store.py`** — nó sẽ bị xoá hoàn toàn ở Phase 2 khi chuyển sang Postgres FTS.

### #7 — Thiếu dependency `langgraph-checkpoint-sqlite` → mất chat history mỗi lần restart
- **Triệu chứng:** import `app.agent.rag_graph` in ra `[WARN] SqliteSaver loi: No module named 'langgraph.checkpoint.sqlite'` rồi fallback `MemorySaver` — nghĩa là lịch sử chat mất **mỗi lần process restart**, không chỉ khi Railway redeploy như tài liệu cũ ghi.
- **Nguyên nhân:** `_get_checkpointer()` có `except Exception` quá rộng, nuốt luôn `ModuleNotFoundError` và âm thầm fallback thay vì báo lỗi rõ ràng. Dependency `langgraph-checkpoint-sqlite` chưa từng có trong `requirements.txt`.
- **Đã sửa:** thêm `langgraph-checkpoint-sqlite==3.1.1` vào `requirements.txt`. Verify bằng cách import trực tiếp: trước fix in `[WARN]`, sau fix in `[INFO] Checkpointer: SqliteSaver (...)`.
- **Đừng:** tin tưởng log `[SUCCESS]`/`[INFO]` mà không biết `except Exception` rộng có thể đang che giấu lỗi thật — nếu sửa code liên quan đến checkpointer, luôn test bằng cách import trực tiếp và đọc log, đừng chỉ đọc code.

### #8 — Supabase Direct Connection chỉ có DNS IPv6, không route được từ nhiều môi trường
- **Triệu chứng:** `asyncpg`/Python `socket.getaddrinfo()` báo `gaierror: nodename nor servname provided, or not known` khi connect tới host `db.<project-ref>.supabase.co`, dù `dig`/`host` từ shell khác vẫn resolve được.
- **Nguyên nhân:** host "Direct connection" của Supabase chỉ có bản ghi **AAAA (IPv6)**, không có **A (IPv4)**. Môi trường không có route IPv6 ra ngoài (sandbox, nhiều serverless platform) sẽ luôn fail ở bước này, bất kể connection string đúng hay sai.
- **Đã sửa:** dùng **Session pooler** thay vì Direct connection — lấy URI ở Supabase → Connect → đổi tab từ "Direct connection" sang "Session pooler". Host dạng `aws-0-<region>.pooler.supabase.com` có cả A và AAAA.
- **Đừng:** dùng Direct connection host (`db.*.supabase.co`) cho bất kỳ môi trường nào không chắc có IPv6 — luôn ưu tiên pooler cho app code, chỉ dùng Direct connection cho công cụ chạy trên máy có IPv6 (vd `psql` từ Mac cá nhân thường có sẵn IPv6).

### #9 — Password chứa ký tự `@` chưa encode làm sai connection string
- **Triệu chứng:** `asyncpg.connect()` báo `gaierror` với host bị lẫn ký tự lạ (`@@db...`), dù dùng đúng pooler host.
- **Nguyên nhân:** password Postgres chứa 2 ký tự `@` chưa được percent-encode (`%40`). URI dạng `postgres://user:PASS@HOST` mà `PASS` có `@` sẽ làm nhiều parser (kể cả code debug tự viết bằng regex đơn giản) tách nhầm ranh giới `userinfo`/`host` nếu không tách theo dấu `@` **cuối cùng** (theo đúng RFC 3986) — `urllib.parse.urlsplit()` tách đúng, nhưng không phải thư viện nào cũng vậy.
- **Đã sửa:** đổi password Supabase sang chỉ gồm chữ + số, không ký tự đặc biệt.
- **Đừng:** tự chọn password chứa `@`, `:`, `/`, `#`, `?`, `%` cho bất kỳ service nào sẽ dùng qua connection-string URI, trừ khi chắc chắn đã percent-encode đúng. Khi debug lỗi tương tự, dùng `urllib.parse.urlsplit()` để tách host/user/password, đừng tự viết regex tách theo dấu `@` đầu tiên (chính tôi đã mắc lỗi y hệt này khi viết script debug).

### #10 — `pgvector` Python package mặc định tìm type ở schema `public`, Supabase cài ở `extensions`
- **Triệu chứng:** `register_vector(conn)` báo `ValueError: unknown type: public.vector`, dù `SELECT extname FROM pg_extension` xác nhận extension đã bật và các bảng dùng cột `vector(768)` đã tạo thành công.
- **Nguyên nhân:** DDL (`CREATE TABLE ... vector(768)`) chạy được vì Postgres tra cứu type theo `search_path` (Supabase đã cấu hình sẵn gồm `extensions`). Nhưng `pgvector.asyncpg.register_vector()` tra cứu type theo schema **chỉ định rõ ràng** (mặc định `schema='public'`), không dùng `search_path` — Supabase cài extension `vector` vào schema `extensions`, không phải `public`.
- **Đã sửa:** `app/storage/repository.py::_register_vector_codec()` gọi `register_vector(conn, schema="extensions")` thay vì để mặc định.
- **Đừng:** bỏ tham số `schema="extensions"` này nếu sau này refactor lại `_register_vector_codec()` — nhìn tưởng thừa/không cần thiết nhưng chính là fix. Nếu sau này tự host Postgres (không phải Supabase) và extension nằm ở `public` thật, thì mới cần đổi lại — kiểm tra bằng `SELECT extname, nspname FROM pg_extension JOIN pg_namespace ON pg_namespace.oid = extnamespace WHERE extname='vector'` trước khi đổi.

### #11 — Gemini free tier: quota tính theo SỐ LƯỢNG EMBED/PHÚT, không phải số HTTP request
- **Triệu chứng:** Upload paper thật (182 chunks) báo `429 RESOURCE_EXHAUSTED: Quota exceeded for metric: embed_content_free_tier_requests, limit: 100`, dù `GoogleGenerativeAIEmbeddings.embed_documents()` đã tự gom batch (chỉ 2 lần gọi API cho 182 text, không phải 182 lần gọi).
- **Nguyên nhân:** quota free tier Gemini đếm theo **số văn bản được embed trong 1 phút** (kể cả khi gom nhiều văn bản vào 1 batch/1 HTTP call), không phải đếm theo số lần gọi API. 2 batch gọi liên tiếp không nghỉ vẫn cộng dồn vượt quota trong cùng 1 phút.
- **Đã sửa:** `GeminiEmbeddingProvider.embed_documents()` tự chia batch ≤100 text, và **chủ động** `time.sleep(61)` giữa các batch (không chỉ dựa vào retry/backoff phản ứng khi đã lỗi — quota reset theo phút nên phải chờ đủ, backoff ngắn không đủ). Paper càng nhiều chunk, upload càng lâu — đây là đánh đổi thật của free tier, không phải bug cần "tối ưu" biến mất.
- **Đừng:** tưởng batching (`batch_size` param) là đủ để tránh rate limit — batching chỉ giảm số HTTP round-trip, không giảm số đơn vị quota bị tính. Nếu sau này đổi provider/API khác, kiểm tra lại đơn vị tính quota là gì (per-call hay per-item) trước khi giả định batching giải quyết được rate limit.

### #12 — `/upload` lưu PDF theo tên file gốc → 2 paper_id trùng tên file ghi đè nhau trên đĩa, DELETE xoá nhầm file paper khác
- **Triệu chứng:** upload 2 file PDF khác nhau nhưng **cùng tên gốc** (vd cùng tải về là `sample_test_cortexODE.pdf`) dưới 2 `paper_id` khác nhau → cả 2 record Postgres đều tồn tại đúng, nhưng chỉ có **1 file PDF duy nhất** trên đĩa (bản upload sau ghi đè bản trước). Khi thêm `DELETE /papers/{id}` (dọn file PDF theo `paper["filename"]`), xoá 1 trong 2 `paper_id` đó sẽ xoá luôn file PDF mà `paper_id` còn lại đang "sở hữu" trên danh nghĩa — **đã thực sự làm mất file mẫu `data/sample_test_cortexODE.pdf`** trong lúc verify tính năng DELETE (file này nằm trong `.gitignore` → `data/*.pdf`, không có bản backup nào, không phục hồi được).
- **Nguyên nhân:** `pdf_path = settings.data_dir / file.filename` dùng **tên file người dùng upload lên**, không dùng `paper_id` (định danh thật sự duy nhất trong hệ thống) làm tên file trên đĩa.
- **Đã sửa:** đổi thành `pdf_path = settings.data_dir / f"{paper_id}.pdf"` ở cả `/upload` và `DELETE /papers/{id}` — mỗi `paper_id` giờ có đúng 1 file cố định, không phụ thuộc tên gốc client gửi lên. Verify lại bằng cách upload cùng 1 file dưới 2 `paper_id` khác nhau → xác nhận có 2 file `.pdf` riêng biệt trên đĩa, xoá 1 cái không ảnh hưởng cái còn lại.
- **Đừng:** dùng bất kỳ giá trị nào từ client (tên file gốc, header, v.v.) làm đường dẫn lưu trữ trên đĩa khi hệ thống đã có sẵn 1 định danh duy nhất (`paper_id`) — luôn dùng định danh nội bộ làm khoá cho tài nguyên trên filesystem, tên gốc chỉ nên lưu làm metadata hiển thị (cột `filename`).
