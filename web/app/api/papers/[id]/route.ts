import { apiError, proxyJson } from "@/lib/backend";
import { isLookupId } from "@/lib/validate";

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isLookupId(id)) return apiError("invalid_id", 400);
  return proxyJson(`/papers/${encodeURIComponent(id)}`, { method: "DELETE" });
}
