import { apiError, proxyJson } from "@/lib/backend";
import { extractArxivId } from "@/lib/validate";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { arxiv_id?: unknown } | null;
  const id = typeof body?.arxiv_id === "string" ? extractArxivId(body.arxiv_id) : null;
  if (!id) return apiError("invalid_id", 400);
  return proxyJson("/papers/arxiv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ arxiv_id: id }),
    timeoutMs: 90_000, // server con tai PDF tu arxiv.org
  });
}
