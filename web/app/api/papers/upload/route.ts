import { apiError, proxyJson } from "@/lib/backend";
import { checkPdfFile, isLookupId } from "@/lib/validate";

export const maxDuration = 60;

// Kiem tra lai o server (khong tin client): <= 4 MB va dung magic bytes %PDF.
export async function POST(request: Request) {
  const form = await request.formData().catch(() => null);
  const file = form?.get("file");
  if (!(file instanceof File)) return apiError("bad_request", 400);
  const check = await checkPdfFile(file);
  if (!check.ok) return check.code === "too_large" ? apiError("too_large", 413) : apiError("not_pdf", 400);
  const out = new FormData();
  out.append("file", file, file.name);
  const paperId = form?.get("paper_id");
  if (typeof paperId === "string" && paperId.trim()) {
    if (!isLookupId(paperId.trim())) return apiError("invalid_id", 400);
    out.append("paper_id", paperId.trim());
  }
  return proxyJson("/upload", { method: "POST", body: out, timeoutMs: 60_000 });
}
