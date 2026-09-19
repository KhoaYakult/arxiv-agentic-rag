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
