# Giao diện Streamlit

Giao diện chat cho ArXiv Agentic RAG. Chỉ gọi API FastAPI qua HTTP nên có thể deploy tách riêng khỏi backend. File chính là `ui/streamlit_app.py`, dependency riêng nằm ở `ui/requirements.txt` (chỉ `streamlit` và `requests`).

## Chạy local

```bash
# Terminal 1: API (từ thư mục gốc repo)
make run                      # uvicorn app.api.main:app --reload --port 8000

# Terminal 2: UI
make ui                       # streamlit run ui/streamlit_app.py
```

Cấu hình (UI đọc theo thứ tự: biến môi trường, rồi `st.secrets`, rồi mặc định):

| Tên | Ý nghĩa | Mặc định |
| --- | --- | --- |
| `API_BASE` | URL gốc của API (không cần thêm `/api/v1`) | `http://127.0.0.1:8000` |
| `APP_API_KEY` | API key gửi kèm header `X-API-Key` (bỏ trống nếu API không yêu cầu) | không có |

Ví dụ trỏ UI tới API khác: `API_BASE=https://ten-api.vercel.app APP_API_KEY=xxx make ui`. Khi chạy local có thể đặt trong `.streamlit/secrets.toml` (file này chứa bí mật, tuyệt đối không commit).

## Deploy lên Streamlit Community Cloud

1. Đẩy repo lên GitHub, vào https://share.streamlit.io và chọn **Create app**.
2. Chọn repo + nhánh, **Main file path** = `ui/streamlit_app.py`.
3. Mở **Advanced settings** và dán secrets (định dạng TOML):

   ```toml
   API_BASE = "https://ten-api.vercel.app"
   APP_API_KEY = "gia-tri-api-key-cua-backend"
   ```

4. Deploy. Community Cloud tìm file requirements trong thư mục chứa entrypoint trước (tức `ui/requirements.txt`), rồi mới tới thư mục gốc repo, nên UI không phải cài các thư viện nặng của backend.

Lưu ý: `APP_API_KEY` nằm trong server của Streamlit (không lộ ra trình duyệt) nhưng mọi người dùng UI đều dùng chung key này, nên chỉ phù hợp cho demo công khai có rate limit ở backend.

## Giới hạn phía người dùng

- Upload PDF tối đa 4 MB, Paper ID tùy chỉnh phải khớp `^[a-z0-9][a-z0-9_-]{0,63}$` (UI kiểm tra trước khi gửi).
- "Nhập từ arXiv" nhận ID (`2401.15884`, có thể kèm `v2`) hoặc URL `arxiv.org/abs/...` / `arxiv.org/pdf/...`.
- Mọi text không tin cậy (câu hỏi, câu trả lời, trích đoạn PDF, tiêu đề bài) đều được `html.escape` trước khi chèn vào HTML; khi thêm phần hiển thị mới có `unsafe_allow_html=True`, hãy dùng helper `esc()`/`esc_multiline()`.
