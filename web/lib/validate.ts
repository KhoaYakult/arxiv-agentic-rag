// Kiem tra dau vao dung chung cho trinh duyet va route handler. Gioi han khop backend:
// max_upload_mb=4 (Vercel cat body 4.5 MB), AskRequest.question 3..1000, LOOKUP_ID_RE.
export const MAX_UPLOAD_MB = 4;
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;
export const QUESTION_MIN = 3;
export const QUESTION_MAX = 1000;

const LOOKUP_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const ARXIV_ID_RE = /^\d{4}\.\d{4,5}(v\d+)?$/;
const ARXIV_URL_RE =
  /^(?:https?:\/\/)?(?:www\.)?arxiv\.org\/(?:abs|pdf)\/(\d{4}\.\d{4,5}(?:v\d+)?)(?:\.pdf)?\/?(?:[?#].*)?$/i;

export function extractArxivId(raw: string): string | null {
  const s = (raw ?? "").trim().replace(/^arxiv:\s*/i, "");
  if (ARXIV_ID_RE.test(s)) return s;
  const m = ARXIV_URL_RE.exec(s);
  return m ? m[1] : null;
}

export function isLookupId(id: string): boolean {
  return LOOKUP_ID_RE.test(id) && !id.includes("..");
}

export type FileCheck = { ok: true } | { ok: false; code: "not_pdf" | "too_large"; message: string };

export async function checkPdfFile(file: Blob & { name?: string }): Promise<FileCheck> {
  if (file.name && !file.name.toLowerCase().endsWith(".pdf")) {
    return { ok: false, code: "not_pdf", message: "Chỉ nhận file PDF (.pdf)." };
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return {
      ok: false,
      code: "too_large",
      message: `File lớn hơn ${MAX_UPLOAD_MB} MB. Với bài trên arXiv, hãy dùng ô “Nhập từ arXiv”.`,
    };
  }
  const head = new Uint8Array(await file.slice(0, 4).arrayBuffer());
  if (String.fromCharCode(...head) !== "%PDF") {
    return { ok: false, code: "not_pdf", message: "File này không phải PDF hợp lệ." };
  }
  return { ok: true };
}

export function checkQuestion(q: string): string | null {
  const t = q.trim();
  if (t.length < QUESTION_MIN) return "Câu hỏi quá ngắn.";
  if (t.length > QUESTION_MAX) return `Câu hỏi dài quá ${QUESTION_MAX} ký tự.`;
  return null;
}

// Chi cho phep duong dan cung origin sau khi dang nhap (chong open redirect).
// Trinh duyet bo qua tab/CR/LF nen "/\t/evil.com" se thanh "//evil.com" -> chan ky tu dieu khien.
export function safeNextPath(p: string | null | undefined): string {
  if (!p || /[\u0000-\u001f\u007f]/.test(p)) return "/";
  if (!p.startsWith("/") || p.startsWith("//") || p.startsWith("/\\")) return "/";
  try {
    const u = new URL(p, "http://x");
    if (u.origin !== "http://x") return "/";
    return u.pathname + u.search + u.hash;
  } catch {
    return "/";
  }
}
