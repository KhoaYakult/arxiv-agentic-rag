# State

> Cập nhật: 2026-09-19

## Đang ở đâu

**Phase 1 hoàn thành + đã push lên `origin/main`.** Đang bắt đầu Phase 2, giai đoạn scaffold (viết code chưa test được với DB thật).

- `main` đã sync với `origin` (user tự push từ máy họ — sandbox này không push được, không có credential GitHub, xem lại lịch sử chat nếu cần lý do).
- Working tree: kiểm tra lại bằng `git status`, đừng tin memory này nếu đã lâu.
- `make test` (20 test) xanh, `ruff check .` sạch — verify trong CI lẫn local, nhiều lần.

## Phase 2 — đang chờ 2 credential trước khi test được thật

1. **`DATABASE_URL`** (Supabase Postgres) — user đang tạo project, chưa xong.
2. **`GEMINI_API_KEY`** — đang **rỗng** trong `.env` (không phải chỉ chưa set, đã check trực tiếp bằng code). Cần key thật (aistudio.google.com/apikey, free) để test `GeminiEmbeddingProvider`.

Đã scaffold xong phần không cần 2 credential trên để test cú pháp/logic cơ bản (`db/schema.sql`, `app/storage/repository.py`, `app/indexing/embeddings.py`) — verify bằng compile + ruff + import smoke-test, **CHƯA** verify bằng cách gọi thật Postgres/Gemini API. Xem `NEXT_STEPS.md` mục Phase 2 để biết chính xác cái gì đã xong/chưa.

⚠️ Pipeline Phase 1 (ChromaDB + BM25 + HF embedding) **vẫn là pipeline đang chạy thật** — chưa đụng vào `routes.py`/`vector_store.py`/`bm25_store.py`, chưa cutover. Đừng xoá 2 file đó cho đến khi Postgres thật hoạt động và đã test lại end-to-end như đã làm ở Phase 1.

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
