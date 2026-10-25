import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

beforeEach(() => {
  process.env.API_BASE = "http://api.test";
  process.env.APP_API_KEY = "k";
});
afterEach(() => vi.unstubAllGlobals());

const ok = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe("POST /api/papers/upload", () => {
  it("rejects > 4 MB and non-PDF before calling the backend", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await import("@/app/api/papers/upload/route");
    const big = new FormData();
    big.append("file", new File(["%PDF" + "x".repeat(4 * 1024 * 1024)], "a.pdf"));
    const r1 = await POST(new Request("http://web/api/papers/upload", { method: "POST", body: big }));
    expect(r1.status).toBe(413);
    const bad = new FormData();
    bad.append("file", new File(["hello"], "a.pdf"));
    const r2 = await POST(new Request("http://web/api/papers/upload", { method: "POST", body: bad }));
    expect(r2.status).toBe(400);
    expect((await r2.json()).error.code).toBe("not_pdf");
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("forwards a valid PDF", async () => {
    const fetchMock = vi.fn(async () => ok({ paper_id: "p", title: "P", status: "processing", num_chunks: 0, message: "" }, 202));
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await import("@/app/api/papers/upload/route");
    const fd = new FormData();
    fd.append("file", new File(["%PDF-1.4 x"], "a.pdf"));
    const r = await POST(new Request("http://web/api/papers/upload", { method: "POST", body: fd }));
    expect(r.status).toBe(202);
    expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toBe("http://api.test/api/v1/upload");
  });
});

describe("POST /api/papers/arxiv", () => {
  it("normalises URLs to ids and rejects junk", async () => {
    const fetchMock = vi.fn(async () => ok({ paper_id: "arxiv-2401.15884", title: "T", status: "processing", num_chunks: 0, message: "" }, 202));
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await import("@/app/api/papers/arxiv/route");
    const r = await POST(new Request("http://web", { method: "POST", body: JSON.stringify({ arxiv_id: "https://arxiv.org/abs/2401.15884" }) }));
    expect(r.status).toBe(202);
    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(String(init.body))).toEqual({ arxiv_id: "2401.15884" });
    const bad = await POST(new Request("http://web", { method: "POST", body: JSON.stringify({ arxiv_id: "../x" }) }));
    expect(bad.status).toBe(400);
  });
});

describe("dynamic id routes", () => {
  it("reject traversal ids with 400", async () => {
    vi.stubGlobal("fetch", vi.fn());
    const { GET } = await import("@/app/api/papers/[id]/status/route");
    const r = await GET(new Request("http://web"), { params: Promise.resolve({ id: "a..b" }) });
    expect(r.status).toBe(400);
  });
});

describe("POST /api/ask", () => {
  it("validates question length and forwards", async () => {
    const fetchMock = vi.fn(async () => ok({ answer: "A [1]", thread_id: "t", grade: "yes", rewrite_count: 0, sources: [] }));
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await import("@/app/api/ask/route");
    const short = await POST(new Request("http://web", { method: "POST", body: JSON.stringify({ question: "a", paper_id: "p", thread_id: "t" }) }));
    expect(short.status).toBe(400);
    const r = await POST(new Request("http://web", { method: "POST", body: JSON.stringify({ question: "Bài nói gì?", paper_id: "p", thread_id: "t" }) }));
    expect(r.status).toBe(200);
  });
});
