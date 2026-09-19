# Project Memory

Thư mục này giúp một session Claude Code **mới** (mất hết context cũ) đọc lại và tiếp tục công việc mà không phải hỏi lại từ đầu.

## Đọc theo thứ tự này khi bắt đầu session mới

1. **`STATE.md`** — trạng thái hiện tại: đang ở đâu, việc gì đang chờ, có gì đặc biệt về môi trường cần biết ngay.
2. **`FIXED_BUGS.md`** — lỗi đã sửa + lý do, để **không sửa lại theo hướng cũ đã sai**.
3. **`NEXT_STEPS.md`** — việc cần làm tiếp theo, theo thứ tự ưu tiên.

Muốn hiểu sâu kiến trúc/lý do quyết định kỹ thuật thì đọc `../CLAUDE.md` và `../docs/ROADMAP.md` + `../docs/Architecture.md`. Ba file trong thư mục này **không thay thế** các tài liệu đó — chúng chỉ là bản tóm tắt "để tiếp tục làm việc ngay", cập nhật thường xuyên hơn.

## Quy tắc cập nhật

- **`STATE.md`**: ghi đè (không phải log lịch sử) — luôn phản ánh đúng hiện tại. Cập nhật sau mỗi phiên làm việc có thay đổi đáng kể.
- **`FIXED_BUGS.md`**: chỉ thêm, không xoá — mỗi bug mới phát hiện + sửa thì thêm entry mới.
- **`NEXT_STEPS.md`**: ghi đè theo tiến độ thật — bỏ mục đã xong, thêm mục mới phát sinh.
- Đừng để 3 file này lệch với `docs/ROADMAP.md`/`docs/Architecture.md` — nếu quyết định kiến trúc thay đổi, sửa cả hai chỗ.
