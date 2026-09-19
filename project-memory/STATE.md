# State

> Cập nhật: 2026-09-19

## Đang ở đâu

**Phase 1 (docs/ROADMAP.md) — HOÀN THÀNH, đã verify end-to-end trên máy thật.** Sẵn sàng chuyển Phase 2.

- 10 commit trên `main`, **chưa push lên `origin`** (`ahead 10`) — hỏi user xem đã muốn push chưa, đừng tự ý push.
- Working tree sạch (kiểm tra lại bằng `git status` — đừng tin memory này nếu đã lâu, tự chạy lệnh).
- `make test` (20 test) xanh, `ruff check .` sạch — verify trong CI lẫn local, nhiều lần.

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
