import { apiError, proxyJson } from "@/lib/backend";
import { checkQuestion, isLookupId } from "@/lib/validate";

export const maxDuration = 120; // CRAG: retrieve -> grade -> (rewrite)* -> generate, 10-30 s, co khi lau hon

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  const question = typeof body?.question === "string" ? body.question.trim() : "";
  const paperId = typeof body?.paper_id === "string" ? body.paper_id : "";
  const threadId = typeof body?.thread_id === "string" ? body.thread_id : "";
  if (checkQuestion(question) || !isLookupId(paperId) || !/^[A-Za-z0-9_-]{1,64}$/.test(threadId)) {
    return apiError("bad_request", 400);
  }
  return proxyJson("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, paper_id: paperId, thread_id: threadId }),
    timeoutMs: 115_000,
  });
}
