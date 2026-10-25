import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createSessionToken } from "@/lib/session";

vi.mock("server-only", () => ({}));
// next/headers khong chay ngoai request -> gia lap cookie phien (hop le mac dinh, doi cookieValue de thu 401).
const session = vi.hoisted(() => ({ cookieValue: undefined as string | undefined }));
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (n: string) => (session.cookieValue && n === "pr_session" ? { name: n, value: session.cookieValue } : undefined) }),
}));
const { errorFromStatus, proxyJson, backendFetch } = await import("@/lib/backend");

const SECRET = "x".repeat(40);
beforeEach(() => {
  process.env.SESSION_SECRET = SECRET;
  session.cookieValue = createSessionToken(SECRET);
});
afterEach(() => vi.unstubAllGlobals());

describe("errorFromStatus", () => {
  it.each([
    [413, "too_large", 413],
    [429, "quota_exhausted", 429],
    [404, "not_found", 404],
    [400, "bad_request", 400],
    [422, "bad_request", 400],
    [403, "server_error", 502],
    [401, "server_error", 502], // API key sai = loi cau hinh server, KHONG phai phien nguoi dung
    [504, "timeout", 504],
    [502, "backend_down", 502], // Vercel/Supabase tam dung -> client coi nhu offline
    [503, "backend_down", 502],
    [500, "server_error", 502],
  ])("%i -> %s", (status, code, out) => expect(errorFromStatus(status)).toEqual({ code, status: out }));
});

describe("proxyJson", () => {
  it("adds X-API-Key, joins /api/v1 and passes JSON through", async () => {
    process.env.API_BASE = "http://api.test/";
    process.env.APP_API_KEY = "k";
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ papers: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const res = await proxyJson("/papers");
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ papers: [] });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/papers");
    expect(new Headers(init.headers).get("X-API-Key")).toBe("k");
  });
  it("maps backend errors and network failures to the error shape", async () => {
    process.env.API_BASE = "http://api.test/api/v1";
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 413 })));
    const r1 = await proxyJson("/upload");
    expect(r1.status).toBe(413);
    expect((await r1.json()).error.code).toBe("too_large");
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("fetch failed"); }));
    const r2 = await proxyJson("/papers");
    expect(r2.status).toBe(502);
    expect((await r2.json()).error.code).toBe("backend_down");
  });
  it("maps a 200 with a non-JSON body to server_error", async () => {
    process.env.API_BASE = "http://api.test";
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>oops</html>", { status: 200 })));
    const r = await proxyJson("/papers");
    expect(r.status).toBe(502);
    expect((await r.json()).error.code).toBe("server_error");
  });
  it("returns 204 without a body", async () => {
    process.env.API_BASE = "http://api.test";
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));
    expect((await proxyJson("/papers/a", { method: "DELETE" })).status).toBe(204);
  });
  it("returns 401 without calling the backend when the session cookie is missing or invalid", async () => {
    process.env.API_BASE = "http://api.test";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    session.cookieValue = undefined;
    const r1 = await proxyJson("/papers");
    expect(r1.status).toBe(401);
    expect((await r1.json()).error.code).toBe("unauthorized");
    session.cookieValue = "123.sai";
    expect((await proxyJson("/papers")).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("backendFetch signal", () => {
  it("aborts the upstream request when the client signal aborts", async () => {
    process.env.API_BASE = "http://api.test";
    let upstream: AbortSignal | undefined;
    vi.stubGlobal("fetch", vi.fn(async (_u: string, init: RequestInit) => {
      upstream = init.signal ?? undefined;
      return new Response("{}");
    }));
    const client = new AbortController();
    await backendFetch("/ask", { signal: client.signal, timeoutMs: 5000 });
    expect(upstream?.aborted).toBe(false);
    client.abort();
    expect(upstream?.aborted).toBe(true);
  });
});
