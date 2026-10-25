import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
const { errorFromStatus, proxyJson } = await import("@/lib/backend");

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
});
