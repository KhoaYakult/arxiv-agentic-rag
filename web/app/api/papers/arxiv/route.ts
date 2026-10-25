import { apiError, proxyJson } from "@/lib/backend";
import { extractArxivId } from "@/lib/validate";

export const maxDuration = 120;

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { arxiv_id?: unknown } | null;
  const id = typeof body?.arxiv_id === "string" ? extractArxivId(body.arxiv_id) : null;
  if (!id) return apiError("invalid_id", 400);
  const res = await proxyJson("/papers/arxiv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ arxiv_id: id }),
    timeoutMs: 90_000, // server con tai PDF tu arxiv.org
  });
  // 413 o day = PDF tren arXiv > 30 MB, khong phai gioi han 4 MB cua o tai file len.
  return res.status === 413 ? apiError("arxiv_too_large", 413) : res;
}
