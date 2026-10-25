import { describe, expect, it } from "vitest";
import {
  MAX_UPLOAD_BYTES, checkPdfFile, checkQuestion, extractArxivId, isLookupId, safeNextPath,
} from "@/lib/validate";

const pdf = (bytes: number, head = "%PDF-1.4") =>
  new File([head + "x".repeat(Math.max(0, bytes - head.length))], "paper.pdf", { type: "application/pdf" });

describe("extractArxivId", () => {
  it.each([
    ["2401.15884", "2401.15884"],
    ["2401.15884v2", "2401.15884v2"],
    ["arXiv:1706.03762", "1706.03762"],
    [" https://arxiv.org/abs/2401.15884 ", "2401.15884"],
    ["arxiv.org/pdf/2401.15884v3.pdf", "2401.15884v3"],
  ])("%s -> %s", (raw, id) => expect(extractArxivId(raw)).toBe(id));
  it.each(["", "abc", "../etc/passwd", "https://evil.com/abs/2401.15884"])("rejects %s", (raw) =>
    expect(extractArxivId(raw)).toBeNull());
});

describe("isLookupId", () => {
  it("accepts backend ids and rejects traversal", () => {
    expect(isLookupId("arxiv-1706.03762")).toBe(true);
    expect(isLookupId("test_cortex_ode")).toBe(true);
    expect(isLookupId("a..b")).toBe(false);
    expect(isLookupId("../x")).toBe(false);
    expect(isLookupId("a/b")).toBe(false);
    expect(isLookupId("x".repeat(65))).toBe(false);
  });
});

describe("checkPdfFile", () => {
  it("accepts a small PDF", async () => expect(await checkPdfFile(pdf(1000))).toEqual({ ok: true }));
  it("rejects > 4 MB", async () =>
    expect(await checkPdfFile(pdf(MAX_UPLOAD_BYTES + 1))).toMatchObject({ ok: false, code: "too_large" }));
  it("rejects wrong magic bytes and wrong extension", async () => {
    expect(await checkPdfFile(pdf(100, "GIF89a"))).toMatchObject({ ok: false, code: "not_pdf" });
    expect(await checkPdfFile(new File(["%PDF-1.4"], "a.txt"))).toMatchObject({ ok: false, code: "not_pdf" });
  });
});

describe("checkQuestion", () => {
  it("enforces 3..1000 chars after trim", () => {
    expect(checkQuestion("  hi ")).not.toBeNull();
    expect(checkQuestion("Bài này nói gì?")).toBeNull();
    expect(checkQuestion("a".repeat(1001))).not.toBeNull();
  });
});

describe("safeNextPath", () => {
  it("only allows same-origin paths", () => {
    expect(safeNextPath("/p/arxiv-1706.03762?x=1")).toBe("/p/arxiv-1706.03762?x=1");
    expect(safeNextPath("//evil.com")).toBe("/");
    expect(safeNextPath("/\\evil.com")).toBe("/");
    expect(safeNextPath("https://evil.com")).toBe("/");
    expect(safeNextPath(null)).toBe("/");
  });
  it("rejects control characters that browsers strip (tab/CR/LF)", () => {
    expect(safeNextPath("/\t/evil.com")).toBe("/");
    expect(safeNextPath("/\n/evil.com")).toBe("/");
    expect(safeNextPath("/\r/evil.com")).toBe("/");
  });
  it("rejects dot-segment paths that normalise to a protocol-relative URL", () => {
    expect(safeNextPath("/.//evil.com")).toBe("/");
    expect(safeNextPath("/a/..//evil.com")).toBe("/");
    expect(safeNextPath("/./\\evil.com")).toBe("/");
  });
  it("keeps an encoded tab as a same-origin path", () => {
    const out = safeNextPath("/%09/x");
    expect(new URL(out, "http://x").origin).toBe("http://x");
    expect(out.startsWith("//")).toBe(false);
  });
});
