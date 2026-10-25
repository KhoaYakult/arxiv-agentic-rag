# Giao diện web (Next.js)

Giao diện đọc bài báo cho ArXiv Agentic RAG: thư viện bài, hội thoại hỏi đáp có trích dẫn, và khung xem PDF gốc với đoạn trích được tô sáng khi bấm vào số trang. Đây là bản thay thế cho giao diện Streamlit ở `ui/`.

Tên sản phẩm "Paper Reader" chỉ là **tên tạm**, nằm duy nhất ở `web/lib/brand.ts`. Đây chỉ là chỗ giữ tên (placeholder), phải đặt tên thật trước khi ra mắt công khai.

Công nghệ: Next.js 16.4 (App Router, `proxy.ts`), React 19, Tailwind 4, shadcn/ui (Radix), react-pdf 11, react-markdown.

## 1. Tổng quan

Đây là bản beta riêng tư: cả app dùng **một mật khẩu chung** (`ACCESS_PASSWORD`). Sau khi đăng nhập, trình duyệt giữ một cookie phiên `pr_session` (httpOnly, ký HMAC bằng `SESSION_SECRET`, sống 30 ngày).

```
Trình duyệt
   │  (cookie phiên httpOnly)
   ▼
web/  Next.js 16 · App Router · TypeScript      ← project Vercel riêng, Root Directory = web/
   ├─ trang: /login, / (thư viện), /p/[paperId] (hội thoại + PDF)
   ├─ proxy.ts: chặn mọi trang và /api/* khi chưa có cookie phiên hợp lệ
   │     (trừ /login, /api/login, file tĩnh)
   └─ /api/* route handlers: kiểm tra phiên → gắn X-API-Key → gọi FastAPI
   │
   │  HTTPS + X-API-Key (chỉ server Next.js biết API_BASE và APP_API_KEY)
   ▼
FastAPI trên Vercel (project API hiện có)
   ├─ Supabase Postgres (papers, sections, chunks, checkpoints)
   └─ Supabase Storage, bucket "papers" (private)

PDF: trình duyệt ──GET signed URL (1 giờ)──▶ Supabase Storage
     (không đi qua Vercel, vì Vercel cắt phản hồi lớn hơn 4.5 MB)
```

**Vì sao API key không bao giờ tới trình duyệt:** trình duyệt chỉ nói chuyện với `/api/*` của chính app Next.js. Chỉ code chạy trên server (route handlers và `proxy.ts`) đọc `API_BASE` và `APP_API_KEY`; `web/lib/backend.ts` import `"server-only"` nên build sẽ lỗi nếu ai lỡ import nó vào code client. Thứ duy nhất trình duyệt nhận từ Supabase là signed URL tạm thời (hết hạn sau 1 giờ) cho đúng một file PDF.

## 2. Chạy local

Cần Node.js 22 trở lên (khai báo trong `engines`; kiểm tra bằng `node -v`) và API đang chạy. Cài dependency một lần:

```bash
cd web && npm ci
```

```bash
# Terminal 1: API (từ thư mục gốc repo)
make run

# Terminal 2: web
cp web/.env.example web/.env.local
```

Điền `web/.env.local`:

| Biến | Giá trị |
| --- | --- |
| `API_BASE` | `http://127.0.0.1:8000` (không cần `/api/v1`) |
| `APP_API_KEY` | Giống `APP_API_KEY` của API (bỏ trống nếu API local không yêu cầu; API production luôn yêu cầu, xem phần Deploy) |
| `ACCESS_PASSWORD` | Mật khẩu chung để vào app |
| `SESSION_SECRET` | Chuỗi ngẫu nhiên từ 32 ký tự trở lên, tạo bằng lệnh bên dưới |

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

Sau đó chạy `make web-dev` (tương đương `cd web && npm run dev`) và mở `http://localhost:3000`.

Muốn xem khung PDF ở local, API cần thêm `SUPABASE_URL` và `SUPABASE_SERVICE_ROLE_KEY` (xem phần Deploy). Thiếu hai biến này thì API vẫn chạy bình thường, chỉ là bài mới không lưu PDF (`has_pdf=false`) và nút "Mở PDF" bị ẩn.

Các script trong `web/package.json`: `dev`, `build`, `start`, `lint`, `typecheck`, `test`, `e2e`.

## 3. Test

```bash
make web-test            # lint + typecheck + Vitest (cd web && npm run lint && npm run typecheck && npm test)
cd web && npm run e2e    # Playwright
```

Cần chạy `npm ci` trước (như trên). Bộ e2e chạy trên **mock backend** (`web/e2e/mock-backend.mjs`, cổng 8799) nên không gọi API thật, không tốn quota Gemini/Groq/Cohere và không đụng vào dữ liệu Supabase. Playwright tự chạy `next build` rồi `next start` ở cổng 3100 (nên lần đầu khá lâu); lần đầu cũng cần `npx playwright install chromium`.

## 4. Deploy

> **Chạy `db/migrations/2026-10-25_has_pdf.sql` trên Supabase TRƯỚC khi push/deploy phiên bản API này.** Push `main` sẽ tự deploy API, mà `upsert_paper` giờ ghi cột `has_pdf`; chưa migrate thì upload và nhập arXiv đều lỗi 500.

Thứ tự quan trọng: làm Supabase trước, rồi API, rồi mới tới web.

**a. Supabase**

1. Storage → New bucket, tên `papers`, để **Private**.
2. SQL Editor → chạy file `db/migrations/2026-10-25_has_pdf.sql` (thêm cột `papers.has_pdf`; chạy lại nhiều lần không lỗi).
3. Project Settings → API → copy `Project URL` và khóa `service_role`.

> **Cảnh báo:** khóa `service_role` có toàn quyền với database và Storage. Chỉ đặt nó trong project Vercel của **API**. Không bao giờ đưa vào project web, vào biến `NEXT_PUBLIC_*`, hay vào bất cứ thứ gì trình duyệt thấy.

**b. Vercel, project API (đã có)**

Thêm hai biến `SUPABASE_URL` (Project URL ở bước a.3) và `SUPABASE_SERVICE_ROLE_KEY`. Biến `STORAGE_BUCKET` mặc định là `papers`, chỉ cần thêm nếu bạn đặt tên bucket khác. Sau đó **Redeploy** để biến có hiệu lực.

**c. Vercel, project web (mới)**

1. Add New → Project → chọn cùng repo GitHub, đặt **Root Directory = `web`**, framework Next.js.
2. Thêm biến môi trường:
   - `API_BASE`: URL của project API, không có `/api/v1`.
   - `APP_API_KEY`: cùng giá trị với `APP_API_KEY` của API. API production bắt buộc có `APP_API_KEY` (không để trống), và project web phải dùng đúng giá trị đó.
   - `ACCESS_PASSWORD`: mật khẩu chung.
   - `SESSION_SECRET`: chuỗi ngẫu nhiên từ 32 ký tự trở lên.
3. Deploy. Web gọi API từ server nên không cần thêm gì vào `ALLOWED_ORIGINS` của API.

**d. Kiểm tra**

Đăng nhập, nhập bài `1706.03762` (Attention Is All You Need) bằng ô nhập arXiv, đợi trạng thái `ready`, đặt một câu hỏi, bấm vào chip `tr. N` trong câu trả lời và kiểm tra khung PDF mở đúng trang với đoạn trích được tô sáng.

- **Bài đã index từ trước lần deploy này không có PDF lưu sẵn** (`has_pdf=false`), và nhập lại cùng bài sẽ trả về đúng bài `ready` cũ mà không index lại. Muốn thử khung PDF, hãy xóa bài cũ rồi nhập lại, hoặc nhập một bài chưa có trong thư viện.
- Kiểm tra nhanh sau khi redeploy API: khi một bài mới nhập xong, `GET /api/v1/papers/{id}/status` phải có `"has_pdf": true`. Nếu là `false`, kiểm tra lại `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` và bucket `papers`.

**e. Đổi mật khẩu**

Đổi `ACCESS_PASSWORD` **và** `SESSION_SECRET` trong Vercel rồi redeploy. Đổi `SESSION_SECRET` làm mọi cookie cũ hết hiệu lực, nên mọi người phải đăng nhập lại.

## 5. Giới hạn cần biết

- **Tải lên tối đa 4 MB** (Vercel giới hạn body request 4.5 MB). PDF lớn hơn thì nhập qua arXiv, nơi server tự tải file với giới hạn **30 MB**.
- **Quota embedding Gemini miễn phí: 1.000 lượt mỗi ngày**, đặt lại vào nửa đêm giờ Pacific (khoảng 14:00, hoặc 15:00 sau khi Mỹ hết giờ mùa hè, theo giờ Việt Nam). Mỗi đoạn văn được embed một lần (khoảng vài chục đến vài trăm lượt mỗi bài), nên nhập vài bài liên tiếp có thể chạm trần; bài chạm quota khi embed có thể bị `failed` (thông báo trong app chỉ nêu các nguyên nhân thường gặp, vì API không trả lý do lỗi) và `/ask` trả 429 nếu quota AI hết.
- **Hàm Vercel tối đa 300 giây.** Nếu việc index bị cắt giữa chừng, bài kẹt ở `processing` và được báo `failed` sau 15 phút.
- **Chất lượng trích dẫn chưa đạt mục tiêu.** Xem phần Evaluation trong README gốc: mô hình không bịa số trích dẫn nhưng hay bỏ sót, nên không phải câu trả lời nào cũng có chip `[n]`. Hàng nguồn dưới mỗi câu trả lời luôn hiện đủ.
- **Tên "Paper Reader" là tên tạm** (`web/lib/brand.ts`), phải đổi trước khi công khai.
