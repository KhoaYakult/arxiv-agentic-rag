// web/lib/client-api.ts - goi /api/* tu trinh duyet (KHONG bao gio goi thang FastAPI).
import type { AskResult, Paper, StatusResult, UploadResult } from "@/lib/types";

export class ApiCallError extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message);
  }
}

async function call<T>(input: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(input, init);
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiCallError("backend_down", "Không kết nối được máy chủ. Kiểm tra mạng và thử lại.", 0);
  }
  if (r.status === 401) {
    // Can tai lai toan trang (xoa state) nen khong dung router.push.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign(`/login?next=${encodeURIComponent(location.pathname + location.search)}`);
    throw new ApiCallError("unauthorized", "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.", 401);
  }
  if (r.status === 204) return undefined as T;
  const body = await r.json().catch(() => null);
  if (!r.ok) {
    throw new ApiCallError(body?.error?.code ?? "server_error", body?.error?.message ?? "Máy chủ gặp lỗi. Hãy thử lại.", r.status);
  }
  return body as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  papers: () => call<{ papers: Paper[]; total: number }>("/api/papers"),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return call<UploadResult>("/api/papers/upload", { method: "POST", body: fd });
  },
  importArxiv: (arxivId: string) => call<UploadResult>("/api/papers/arxiv", json({ arxiv_id: arxivId })),
  status: (id: string) => call<StatusResult>(`/api/papers/${encodeURIComponent(id)}/status`),
  remove: (id: string) => call<void>(`/api/papers/${encodeURIComponent(id)}`, { method: "DELETE" }),
  pdfUrl: (id: string) => call<{ url: string; expires_in: number }>(`/api/papers/${encodeURIComponent(id)}/pdf-url`),
  ask: (body: { question: string; paper_id: string; thread_id: string }, signal?: AbortSignal) =>
    call<AskResult>("/api/ask", { ...json(body), signal }),
  logout: () => call<{ ok: true }>("/api/logout", { method: "POST" }),
};
