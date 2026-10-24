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

`APP_API_KEY` phải trùng với biến `APP_API_KEY` đã đặt trên API; UI gửi nó trong header `X-API-Key` cho mọi lời gọi. Sai hoặc thiếu key thì API trả 401.

## Deploy lên Streamlit Community Cloud

1. Đẩy repo lên GitHub, vào https://share.streamlit.io và chọn **Create app**.
2. Chọn repo + nhánh, **Main file path** = `ui/streamlit_app.py`.
3. Mở **Advanced settings** và dán secrets (định dạng TOML):

   ```toml
   API_BASE = "https://ten-api.vercel.app"
   APP_API_KEY = "gia-tri-api-key-cua-backend"
   ```

4. Deploy. Community Cloud tìm file requirements trong thư mục chứa entrypoint trước (tức `ui/requirements.txt`), rồi mới tới thư mục gốc repo, nên UI không phải cài các thư viện nặng của backend.
5. Thêm URL của app (ví dụ `https://ten-app.streamlit.app`) vào biến `ALLOWED_ORIGINS` của API trên Vercel. UI gọi API từ server của Streamlit nên thường chưa cần, nhưng nên khai báo để không vướng CORS nếu sau này gọi từ trình duyệt.

## Theme và `.streamlit/config.toml`

File cấu hình theme nằm ở **thư mục gốc repo** (`.streamlit/config.toml`), *không* nằm trong `ui/`. Streamlit đọc nó theo thư mục chạy lệnh, nên hãy chạy `make ui` (hoặc `streamlit run ui/streamlit_app.py`) **từ thư mục gốc**; Streamlit Cloud cũng đọc đúng file này. File gồm:

- `[theme] base = "dark"` cùng bảng màu: CSS tuỳ chỉnh trong `ui/streamlit_app.py` được viết cho nền tối; để theme sáng mặc định thì vùng chính bị nền trắng và tiêu đề gần như vô hình.
- `[server] maxUploadSize = 4`: ô chọn file hiện "4MB per file" (thay vì 200MB mặc định), khớp với giới hạn của API.

Lưu ý: `APP_API_KEY` nằm trong server của Streamlit (không lộ ra trình duyệt) nhưng mọi người dùng UI đều dùng chung key này, nên chỉ phù hợp cho demo công khai có rate limit ở backend.

## Giới hạn phía người dùng

- **Upload PDF tối đa 4 MB** vì Vercel giới hạn body request ở 4.5 MB. Paper ID tùy chỉnh phải khớp `^[a-z0-9][a-z0-9_-]{0,63}$` (UI kiểm tra trước khi gửi).
- **PDF lớn hơn 4 MB: dùng "Nhập từ arXiv"** (tối đa 30 MB). Ô này nhận ID (`2401.15884`, có thể kèm `v2`) hoặc URL `arxiv.org/abs/...` / `arxiv.org/pdf/...`; UI chỉ gửi mã, còn *server API tự tải* PDF từ arxiv.org nên không vướng giới hạn 4 MB. Paper nhập từ arXiv có ID `arxiv-<mã>`; nhập lại bài đã có thì không xử lý lại.
- Index một bài mất vài phút (parse + embed, gói Gemini miễn phí giới hạn tốc độ); UI hỏi trạng thái định kỳ cho tới khi bài sang `ready`. Chỉ bài `ready` mới chọn để hỏi được.
- Mọi text không tin cậy (câu hỏi, trích đoạn PDF, tiêu đề bài) đều được `html.escape` trước khi chèn vào HTML; khi thêm phần hiển thị mới có `unsafe_allow_html=True`, hãy dùng helper `esc()`/`esc_multiline()`.
- Câu trả lời của agent được hiển thị bằng `st.markdown` *không* bật `unsafe_allow_html`: Markdown và công thức LaTeX hiện bình thường, còn HTML lạ trong câu trả lời chỉ hiện như chữ. Đừng nhét câu trả lời vào HTML tự dựng.

## Xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Thanh bên hiện **🔴 "Server chưa chạy"** kèm cảnh báo "Chưa cấu hình `API_BASE`..." (trên Streamlit Cloud) | Chưa đặt secret `API_BASE`, nên UI quay về gọi `http://127.0.0.1:8000`, mà trên Cloud không có server nào ở đó | Vào app → **Settings → Secrets**, thêm `API_BASE` (và `APP_API_KEY`), lưu rồi app tự khởi động lại |
| "Server chưa chạy" kèm "Không kết nối được tới API: ..." | `API_BASE` sai, API đang lỗi hoặc cold start chậm | Mở `<API_BASE>/api/v1/health` bằng trình duyệt; sửa `API_BASE` nếu sai |
| Gọi API báo 401 | `APP_API_KEY` thiếu hoặc khác giá trị trên API | Đặt lại secret cho khớp |
| Upload báo file quá lớn | PDF > 4 MB | Dùng "Nhập từ arXiv" nếu là bài trên arXiv |
| Nhập từ arXiv thất bại, lỗi liên quan 429 / `RESOURCE_EXHAUSTED` | Hết quota embedding miễn phí của Gemini (1.000 lượt/ngày) | Chờ quota reset rồi thử lại; không phải lỗi giao diện |
| Không thấy thanh bên để mở lại | Bản cũ của CSS đã ẩn nút mở sidebar | Đã sửa; đảm bảo dùng bản mới và đừng ẩn `header`/`stToolbar` bằng CSS |
