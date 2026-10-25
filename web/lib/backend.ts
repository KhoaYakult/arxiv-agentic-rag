// Goi FastAPI tu SERVER Next.js. Day la cho DUY NHAT doc API_BASE / APP_API_KEY.
import "server-only";
import { NextResponse } from "next/server";

export type ApiErrorCode =
  | "quota_exhausted" | "too_large" | "not_pdf" | "invalid_id" | "not_found" | "timeout"
  | "backend_down" | "unauthorized" | "bad_request" | "server_error" | "bad_password";

export const ERROR_MESSAGES: Record<ApiErrorCode, string> = {
  quota_exhausted: "Hết lượt xử lý miễn phí hôm nay. Hãy thử lại sau 14:00.",
  too_large: "File lớn hơn 4 MB. Với bài trên arXiv, hãy dùng ô “Nhập từ arXiv”.",
  not_pdf: "File này không phải PDF hợp lệ.",
  invalid_id: "Mã bài báo không hợp lệ.",
  not_found: "Không tìm thấy bài báo.",
  timeout: "Máy chủ phản hồi quá lâu. Hãy thử lại.",
  backend_down: "Không kết nối được máy chủ. Hãy thử lại sau ít phút.",
  unauthorized: "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.",
  bad_request: "Yêu cầu không hợp lệ.",
  server_error: "Máy chủ gặp lỗi. Hãy thử lại.",
  bad_password: "Sai mật khẩu, thử lại.",
};

export function apiError(code: ApiErrorCode, status: number): NextResponse {
  return NextResponse.json({ error: { code, message: ERROR_MESSAGES[code] } }, { status });
}

export function errorFromStatus(status: number): { code: ApiErrorCode; status: number } {
  if (status === 413) return { code: "too_large", status: 413 };
  if (status === 429) return { code: "quota_exhausted", status: 429 };
  if (status === 404) return { code: "not_found", status: 404 };
  if (status === 400 || status === 422) return { code: "bad_request", status: 400 };
  if (status === 504) return { code: "timeout", status: 504 };
  // 401/403 tu FastAPI = APP_API_KEY cua web sai -> loi cau hinh server, khong phai loi phien.
  return { code: "server_error", status: 502 };
}

function backendUrl(path: string): string {
  const base = (process.env.API_BASE ?? "").replace(/\/+$/, "");
  return `${base}${base.endsWith("/api/v1") ? "" : "/api/v1"}${path}`;
}

export async function backendFetch(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<Response> {
  const { timeoutMs = 30_000, ...rest } = init;
  const headers = new Headers(rest.headers);
  if (process.env.APP_API_KEY) headers.set("X-API-Key", process.env.APP_API_KEY);
  return fetch(backendUrl(path), { ...rest, headers, cache: "no-store", signal: AbortSignal.timeout(timeoutMs) });
}

export async function proxyJson(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<NextResponse> {
  let r: Response;
  try {
    r = await backendFetch(path, init);
  } catch (err) {
    const timedOut = err instanceof Error && (err.name === "TimeoutError" || err.name === "AbortError");
    return timedOut ? apiError("timeout", 504) : apiError("backend_down", 502);
  }
  if (r.status === 204) return new NextResponse(null, { status: 204 });
  if (r.ok) {
    try {
      return NextResponse.json(await r.json(), { status: r.status });
    } catch (err) {
      const timedOut = err instanceof Error && (err.name === "TimeoutError" || err.name === "AbortError");
      if (!timedOut) console.error(`[backend] ${path} -> HTTP ${r.status} nhung body khong phai JSON`);
      return timedOut ? apiError("timeout", 504) : apiError("server_error", 502);
    }
  }
  const e = errorFromStatus(r.status);
  if (e.code === "server_error") console.error(`[backend] ${path} -> HTTP ${r.status}`);
  return apiError(e.code, e.status);
}
