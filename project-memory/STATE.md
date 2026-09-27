# State

> Cập nhật: 2026-09-23

## Đang ở đâu

**Phase 1 hoàn thành + đã push lên `origin/main`.** Đang bắt đầu Phase 2, giai đoạn scaffold (viết code chưa test được với DB thật).

- `main` đã sync với `origin` (user tự push từ máy họ — sandbox này không push được, không có credential GitHub, xem lại lịch sử chat nếu cần lý do).
- Working tree: kiểm tra lại bằng `git status`, đừng tin memory này nếu đã lâu.
- `make test` (20 test) xanh, `ruff check .` sạch — verify trong CI lẫn local, nhiều lần.

## Phase 2 — Postgres đã kết nối thật, `repository.py` verify xong

✅ **`DATABASE_URL`** (Supabase, Session pooler) hoạt động — verify bằng cách gọi thật `upsert_paper`/`get_paper`/`insert_sections`/`insert_chunks`/`delete_paper` trên DB thật, dọn sạch dữ liệu test sau đó.

✅ **`GEMINI_API_KEY`** đã có và verify xong — `embed_query`/`embed_documents` gọi API thật thành công, trả đúng 768-dim, cosine similarity đúng hướng (câu liên quan > câu không liên quan).

✅ **`repository.hybrid_search()`** viết xong + verify thật: index 4 chunk (embedding Gemini thật) vào Supabase, query thật → top-2 kết quả đúng chính xác 2 chunk liên quan, xếp hạng đúng theo RRF. Dense (pgvector cosine `<=>`) + sparse (Postgres FTS) chạy song song qua `asyncio.gather`, gộp bằng `reciprocal_rank_fusion()` tái dùng nguyên từ Phase 1 — không viết lại RRF.

✅ **Cutover hoàn tất và verify thật qua HTTP** (uvicorn thật, không mock): `/upload` ghi Postgres, `/papers` đọc Postgres, `/ask` dùng `rag_graph.py` (giờ full async) gọi `repository.hybrid_search()`. Test với PDF thật 182 chunks — 1 câu hỏi tổng quát trả lời đúng (`grade:"yes"`, 5 sources hợp lý), 1 câu hỏi số liệu cụ thể trong bảng bị từ chối đúng cách (`grade:"no"` — hành vi an toàn, không phải bug, ghi backlog Phase 3).

`rag_graph.py` **đã chuyển hẳn sang async** (bắt buộc vì `asyncpg` chỉ hỗ trợ async) — checkpointer đổi `SqliteSaver`→`AsyncSqliteSaver`→**`AsyncPostgresSaver` thật (2026-09-27)**, xem mục riêng bên dưới.

✅ **Checkpointer → `AsyncPostgresSaver` thật — verify thật (2026-09-27).** Chat history giờ nằm trong CÙNG Supabase Postgres DB với papers/chunks (bảng `checkpoints`/`checkpoint_writes`/`checkpoint_blobs`, do `AsyncPostgresSaver.setup()` tự tạo), thay vì file SQLite trên đĩa ephemeral của Railway — sống sót qua redeploy. Dùng 1 kết nối `psycopg` riêng (KHÔNG dùng chung `asyncpg` pool của `repository.py` vì `langgraph-checkpoint-postgres` chỉ hỗ trợ driver `psycopg`), `prepare_threshold=0` bắt buộc vì Supabase Session pooler (PgBouncer) không hỗ trợ prepared statement đa client. Không còn `except Exception` rồi fallback im lặng như bản SQLite cũ (bug #7) — lỗi kết nối Postgres giờ raise ngay và rõ ràng lúc khởi động. Verify 2 lớp: (1) `python app/agent/rag_graph.py` in `[INFO] Checkpointer: AsyncPostgresSaver (Postgres)`, Turn 2 `Messages: 4`; (2) verify riêng khả năng sống sót qua **process restart thật** (mô phỏng Railway redeploy, không chỉ trong 1 process) — chạy `ask()` cùng `thread_id` ở 2 lệnh `python -c` riêng biệt: lần 1 `messages so far: 2`, lần 2 (process hoàn toàn mới) `messages so far: 4`. Đã dọn sạch dữ liệu test khỏi 3 bảng checkpoint sau đó. `close_checkpointer()` mới thêm, gọi trong `app/api/main.py::lifespan` cùng `repository.close_pool()`. `requirements.txt`/`.gitignore` cập nhật theo (bỏ `langgraph-checkpoint-sqlite`/3 dòng `data/chat_memory.db*`, thêm `langgraph-checkpoint-postgres`/`psycopg[binary]`/`psycopg-pool`/`orjson`).

✅ **Page-aware chunking end-to-end — verify thật (2026-09-27).** `ChildChunk` có thêm `page_num`/`char_start`/`char_end`/`level`. `app/ingestion/chunker.py::create_child_chunks()` giờ gỡ marker `<!-- page:N -->` (parser.py đã chèn sẵn từ Phase 1, xem `FIXED_BUGS.md` #1, nhưng trước đây không ai dùng tới) qua 2 helper thuần mới `_strip_page_markers()`/`_page_at()`, tính `page_num` theo vị trí ký tự bắt đầu của chunk trong text ĐÃ làm sạch marker — marker không còn lọt vào text cuối cùng đem đi embed/generate nữa. `char_start`/`char_end` tính theo cùng hệ toạ độ (dùng cho small-to-big expansion sau này, chưa làm). `app/storage/repository.py::insert_chunks()` giờ ghi 4 cột này thay vì để NULL; `_DENSE_SEARCH_SQL`/`_SPARSE_SEARCH_SQL` thêm `c.page_num` vào SELECT; `app/api/schemas.py::SourceChunk` thêm field `page_num`; `app/api/routes.py::ask_agent()` truyền qua. TDD: viết 11 test mới (`TestStripPageMarkers`/`TestPageAt`/`TestCreateChildChunksPageAwareness`) trong `tests/test_chunker.py` trước, verify đỏ (`ImportError`) rồi mới implement, verify xanh — `pytest tests/` 31/31 pass, `ruff check .` sạch. Verify thật qua HTTP (uvicorn port 8013): upload `data/sample_cortexODE.pdf` dưới `paper_id=task2_probe` → status `ready` (181 chunks) → `/ask "What is this paper about?"` → response có nhiều `sources[].page_num` khác null (chunk ở REFERENCES section trả `page_num: 14`) — chứng minh round trip chunker → Postgres → API hoạt động trên nội dung PDF thật, không phải giả lập. Đã `DELETE /papers/task2_probe` dọn sạch, xác nhận `404` và file PDF trên đĩa bị xoá đúng (file mẫu `data/sample_cortexODE.pdf` được giữ nguyên, không đụng tới).

✅ **File hash dedup trên `/upload` — verify thật (2026-09-27).** `upload_paper()` giờ đọc content, tính `sha256`, gọi `repository.get_paper_by_hash()` TRƯỚC khi lưu file/tạo paper mới. Helper thuần `_should_reuse_by_hash(existing)` (ở `app/api/routes.py`, có test mới `tests/test_routes.py`, 4 test) quyết định có tái sử dụng hay không - chỉ reuse khi paper cũ `status='ready'`; match với `'processing'`/`'failed'` bị coi như chưa có gì đáng tin, xử lý như upload mới bình thường (không short-circuit). Khi reuse: trả về `200` (không phải `202`) với thông tin paper CŨ (paper_id/title/num_chunks gốc), không parse/embed lại, không ghi file PDF mới lên đĩa. TDD: viết test trước, verify đỏ (`ImportError`), rồi implement, verify xanh. Verify thật qua HTTP (uvicorn thật, port 8014, Supabase + Gemini thật): upload `data/sample_cortexODE.pdf` dưới `paper_id=dedup_probe_a` → ready 181 chunks → upload lại CÙNG byte dưới `paper_id=dedup_probe_b` khác → `HTTP 200`, body trả về `paper_id=dedup_probe_a` (bản gốc, không phải `dedup_probe_b`) → xác nhận `data/dedup_probe_b.pdf` KHÔNG tồn tại trên đĩa → xác nhận `GET /papers/dedup_probe_b/status` trả `404` (không có row Postgres nào được tạo cho `dedup_probe_b`). Dọn sạch: `DELETE /papers/dedup_probe_a` → `204`, sample PDF gốc (`data/sample_cortexODE.pdf`) không bị đụng tới. `pytest tests/` 35/35 pass, `ruff check .` sạch.

⚠️→✅ **Bug thật #13 tìm được ở review, đã sửa cùng ngày (2026-09-27):** nhánh "fresh upload" fallback (khi paper cũ cùng `file_hash` đang `'processing'`/`'failed'`, không reuse) từng crash `500` (`asyncpg.exceptions.UniqueViolationError`) vì `papers.file_hash UNIQUE` trong `db/schema.sql` áp cho **toàn bảng**, không riêng `status='ready'` — để lại file PDF mồ côi trên đĩa, cùng dạng lỗi với bug #12. Đã sửa bằng `repository.clear_stale_file_hash()` (gỡ claim `file_hash` cũ trước khi ghi row mới) + bọc `upsert_paper()` trong `try/except asyncpg.exceptions.UniqueViolationError` cụ thể (an toàn kép cho race condition thật, xoá file vừa ghi nếu vẫn đụng constraint). Verify thật: tạo trực tiếp 1 row `status='failed'` giữ `file_hash=H` (không qua API, để chủ động ép trạng thái `'failed'` thay vì chờ race), rồi `POST /upload` thật qua HTTP cùng byte dưới `paper_id` mới → `202` (không phải `500`) → poll → `ready`, 181 chunks → xác nhận row cũ đã bị gỡ `file_hash` (`NULL`) còn row mới giữ đúng `file_hash=H`. Xem chi tiết đầy đủ ở `FIXED_BUGS.md` #13. `pytest tests/` 39/39 pass (thêm 4 test `TestShouldClearStaleHash`), `ruff check .` sạch.

⚠️ `app/indexing/vector_store.py`/`bm25_store.py`/`hybrid_retriever.py` **không còn được dùng nữa** (routes.py/rag_graph.py đã trỏ hết sang Postgres) nhưng **cố ý CHƯA xoá file** — giữ lại phòng cần rollback nhanh, chờ user xác nhận ổn định vài ngày rồi mới xoá hẳn.

✅ **`/upload` đã chuyển sang `BackgroundTasks` — verify thật qua HTTP (2026-09-23).** Response `202` trả về gần như tức thì (không còn block event loop suốt parse+embed+rate-limit-cooldown); parse/embed/index chạy nền trong `_process_and_index_paper()`, lỗi được bắt và ghi `papers.status='failed'` thay vì raise. Thêm `GET /papers/{paper_id}/status` để poll. `repository.list_papers()` giờ lọc `WHERE status='ready'` (fix theo đúng docstring cũ, không phải feature mới — cutover trước không cần lọc vì `/upload` đồng bộ nên client chưa từng thấy paper `processing`). `streamlit_app.py` cập nhật theo (poll status thay vì đọc `num_chunks` ngay trong response upload). Test thật: upload 182-chunk PDF → 202 ngay lập tức → status `processing` → `/papers` rỗng đúng lúc đó → ~10s sau `ready`, `num_chunks=182` → `/ask` trả lời đúng.

✅ **`DELETE /papers/{paper_id}` + FastAPI `lifespan` — verify thật qua HTTP (2026-09-23).** CASCADE xoá `sections`/`chunks`/`paper_cards` qua FK có sẵn trong schema, xoá thêm file PDF trên đĩa, idempotent (`404` nếu gọi lại). `app/api/main.py` thêm `lifespan` gọi `repository.close_pool()` lúc shutdown. Verify: upload → chờ ready → DELETE → `204` → `/papers/{id}/status` sau đó `404` → `/papers` rỗng lại → DELETE lần 2 → `404` (không crash). Cũng test xoá **trong lúc đang processing**: background task fail ở bước insert (FK `paper_id` không còn), bị bắt bởi `except Exception` có sẵn, ghi log `[ERROR]`, không crash server, không tạo lại row.

⚠️ **Bug thật #12 xảy ra trong lúc verify DELETE — đã sửa, xem `FIXED_BUGS.md`:** `/upload` từng lưu PDF theo **tên file gốc** (`file.filename`) thay vì `paper_id`. Upload 2 `paper_id` khác nhau nhưng trùng tên file gốc → ghi đè cùng 1 file trên đĩa → `DELETE` 1 trong 2 paper đã **xoá vĩnh viễn** file PDF mẫu `data/sample_test_cortexODE.pdf` (gitignored, không có bản backup, không phục hồi được). Đã sửa: cả `/upload` và `DELETE` giờ dùng `f"{paper_id}.pdf"` làm đường dẫn đĩa. Đã tải 1 PDF public khác (arXiv 1706.03762) để verify lại fix, rồi xoá sau khi test xong — **thư mục `data/` hiện không còn PDF mẫu nào**, cần upload 1 PDF thật bất kỳ trước khi test tay các endpoint khác.

Bug #11 mới tìm: Gemini free tier quota tính theo **số embedding/phút** (không phải số HTTP call) — `embed_documents()` giờ tự chia batch + nghỉ 61s. Nghĩa là **upload paper nhiều chunk (>100) giờ chậm hơn hẳn** (100 chunk đầu tức thì, mỗi 100 chunk tiếp theo +61s chờ) — đây là lý do BackgroundTasks cho `/upload` (item cũ trong NEXT_STEPS) giờ quan trọng hơn trước, không chỉ là "nice to have".

### 3 bug thật đã tìm và sửa trong lúc test kết nối Supabase (không đoán được nếu không có DB thật)

1. **Direct connection host chỉ có DNS IPv6 (AAAA), không có IPv4** → sandbox/nhiều môi trường không route được. Fix: dùng **Session pooler** (`aws-0-<region>.pooler.supabase.com`) thay vì Direct connection.
2. **Password chứa ký tự `@` chưa encode** làm `asyncpg` tách sai host trong connection string (rơi vào lớp lỗi y hệt như 1 script debug của tôi tự mắc phải trước đó). Fix: đổi password sang chỉ chữ+số.
3. **Supabase cài extension `pgvector` vào schema `extensions`, không phải `public`** (khác mặc định của thư viện Python `pgvector`, `register_vector()` mặc định `schema='public'`). Lỗi `unknown type: public.vector` dù extension đã bật và bảng đã tạo xong. Fix: `app/storage/repository.py` → `register_vector(conn, schema="extensions")`. **Đây là bug dễ tái diễn nhất nếu ai đó viết lại đoạn code này — nhớ kỹ.**

Chi tiết đầy đủ trong `FIXED_BUGS.md` (mục #8, #9, #10).

⚠️ Pipeline Phase 1 (ChromaDB + BM25 + HF embedding) **vẫn là pipeline đang chạy thật** — chưa đụng vào `routes.py`/`vector_store.py`/`bm25_store.py`, chưa cutover. Đừng xoá 2 file đó cho đến khi đã wire `repository.py` vào và test lại end-to-end như đã làm ở Phase 1.

## Đã verify xong trên máy thật (macOS, Docker Desktop)

Trước đó bị chặn vì Docker Desktop chưa mở (`failed to connect to the docker API`) — user tự mở app, daemon lên bình thường. Sau đó verify đủ:

1. ✅ `docker build -t arxiv-rag .` build thành công.
2. ✅ `docker run` → `docker ps -a` báo `Up ... (healthy)` — `HEALTHCHECK` hoạt động đúng.
3. ✅ `curl /api/v1/health` qua HTTP thật trả `{"status":"ok",...}`.
4. ✅ `docker exec ... whoami` → `appuser` — xác nhận chạy non-root, không phải `root`.
5. ✅ `$PORT` tuỳ chỉnh: chạy với `-e PORT=9000 -p 9000:9000`, health check trả lời đúng ở port 9000 — xác nhận Dockerfile không còn hardcode port.
6. ✅ Upload PDF thật (`sample_test_cortexODE.pdf`) → 182 chunks index thành công.
7. ✅ `/ask` thật trả lời đúng nội dung (câu hỏi về CortexODE, `grade: "yes"`), và **field `sources` có 5 phần tử** đầy đủ `chunk_id`/`section`/`content_preview` — xác nhận **bug #3 hết thật ngoài đời**, không chỉ trong unit test.

⚠️ Lưu ý cho session sau: đừng nhầm 2 môi trường — **sandbox của Claude không có Docker daemon** (kiến trúc vốn vậy, không phải lỗi cần fix, Claude không tự build/run Docker được), còn **máy Mac của user** có Docker Desktop nhưng phải tự mở app trước khi dùng.

## Việc gần nhất đã làm (không lặp lại)

- Dọn sạch repo (xoá cache rác, sửa `.gitignore` thiếu `.venv/`, gộp skill trùng lặp `.agents/` vào `.claude/skills/`).
- Cài skill `caveman` và `find-skills` vào `.claude/skills/` (project-scoped) — track trong `skills-lock.json` ở root.
- Được yêu cầu cài plugin `superpowers@superpowers-marketplace` qua `/plugin` — **không cài được**, `/plugin` không khả dụng trong môi trường VSCode extension này, `claude` CLI cũng không có trên PATH của sandbox. Đề xuất cài dưới dạng skill thay thế nhưng **user từ chối** (thấy rắc rối hơn cài plugin thật) — đừng đề xuất lại hướng "cài skill thay plugin" trừ khi user tự hỏi lại.
- `docs/tracking.md` (Vietnamese checklist) đã được **gộp vào `project-memory/`** (thư mục này) để tránh 2 nơi track trùng lặp — file `docs/tracking.md` không còn được cập nhật, xem `NEXT_STEPS.md` thay thế.
