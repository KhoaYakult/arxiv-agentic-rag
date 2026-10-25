import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/client-api";

afterEach(() => vi.unstubAllGlobals());

describe("client-api abort", () => {
  it("rethrows AbortError when Stop is pressed while the body is being read", async () => {
    const controller = new AbortController();
    const res = {
      status: 200,
      ok: true,
      json: async () => {
        controller.abort(); // bam Dung giua luc doc body
        return null;
      },
    };
    vi.stubGlobal("fetch", vi.fn(async () => res));
    await expect(api.ask({ question: "abc", paper_id: "p", thread_id: "t" }, controller.signal)).rejects.toMatchObject({
      name: "AbortError",
    });
  });
});
