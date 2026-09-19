# State

> Cập nhật: 2026-09-19

## Đang ở đâu

**Phase 1 (docs/ROADMAP.md) — code đã xong, đang kẹt ở bước verify thủ công.**

- 8 commit trên `main`, **chưa push lên `origin`** (`ahead 8`) — chưa push vì đang chờ user verify Docker/e2e trước, tránh push code chưa test thật.
- Working tree sạch, không có gì uncommitted (kiểm tra lại bằng `git status` — đừng tin memory này nếu đã lâu, tự chạy lệnh).
- `make test` (20 test) xanh, `ruff check .` sạch — verify trong CI lẫn local, nhiều lần.

## Đang chờ (blocker hiện tại)

User đang verify Phase 1 trên máy thật (macOS), bị chặn ở: **Docker daemon không chạy**.

```
failed to connect to the docker API at unix:///var/run/docker.sock: connect: no such file or directory
```

- Docker CLI có cài, nhưng Docker Desktop **chưa mở** trên máy user.
- Đã hướng dẫn user mở Docker Desktop app, chờ daemon lên rồi `docker info` để confirm trước khi `docker build` lại.
- **Chưa biết kết quả** — session tiếp theo cần hỏi lại user đã mở Docker Desktop / build được chưa, đừng giả định đã xong.

⚠️ Phân biệt 2 môi trường khác nhau, đừng nhầm:
- **Sandbox của Claude (nơi code được viết/test)**: không có Docker daemon, kiến trúc vốn vậy, không phải lỗi cần fix — Claude không tự build/run Docker được ở đây, phải hướng dẫn user làm trên máy họ.
- **Máy Mac của user**: có Docker CLI + Docker Desktop, nhưng phải tự mở app trước khi `docker build`/`docker run` chạy được.

## 2 việc cần user tự verify để đóng Phase 1 hẳn

1. `docker build -t arxiv-rag .` (nhớ dấu `.` cuối — user từng quên) + `docker run` với `-e PORT=9000` tuỳ chỉnh + kiểm tra `docker ps` báo `healthy`.
2. Upload PDF thật qua `/upload` → gọi `/ask` thật → kiểm tra field `sources` trong response **khác rỗng** (xác nhận bug #3 hết thật ngoài đời, không chỉ trong unit test).

Lệnh cụ thể nằm trong lịch sử chat + có thể tái tạo từ `README.md` (mục Setup/Running) và `Makefile`.

## Việc gần nhất đã làm (không lặp lại)

- Dọn sạch repo (xoá cache rác, sửa `.gitignore` thiếu `.venv/`, gộp skill trùng lặp `.agents/` vào `.claude/skills/`).
- Cài skill `caveman` và `find-skills` vào `.claude/skills/` (project-scoped) — track trong `skills-lock.json` ở root.
- Được yêu cầu cài plugin `superpowers@superpowers-marketplace` qua `/plugin` — **không cài được**, `/plugin` không khả dụng trong môi trường VSCode extension này, `claude` CLI cũng không có trên PATH của sandbox. Đề xuất cài dưới dạng skill thay thế nhưng **user từ chối** (thấy rắc rối hơn cài plugin thật) — đừng đề xuất lại hướng "cài skill thay plugin" trừ khi user tự hỏi lại.
- `docs/tracking.md` (Vietnamese checklist) đã được **gộp vào `project-memory/`** (thư mục này) để tránh 2 nơi track trùng lặp — file `docs/tracking.md` không còn được cập nhật, xem `NEXT_STEPS.md` thay thế.
