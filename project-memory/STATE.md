# State

> Cập nhật: 2026-09-19

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

`rag_graph.py` **đã chuyển hẳn sang async** (bắt buộc vì `asyncpg` chỉ hỗ trợ async) — checkpointer đổi `SqliteSaver`→`AsyncSqliteSaver` (vẫn SQLite, chưa phải Postgres, đó là bước riêng).

⚠️ `app/indexing/vector_store.py`/`bm25_store.py`/`hybrid_retriever.py` **không còn được dùng nữa** (routes.py/rag_graph.py đã trỏ hết sang Postgres) nhưng **cố ý CHƯA xoá file** — giữ lại phòng cần rollback nhanh, chờ user xác nhận ổn định vài ngày rồi mới xoá hẳn.

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
