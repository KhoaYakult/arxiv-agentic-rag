import { describe, expect, it } from "vitest";
import { citationLabel, expandMarker, resolveCitations, splitCitations, stripCitationMarkers } from "@/lib/citations";
import type { Source } from "@/lib/types";

const src = (page: number | null, i = 0): Source => ({
  chunk_id: `c${i}`, section: `S${i}`, content_preview: "p", text: `t${i}`, page_num: page,
});

describe("expandMarker", () => {
  it("parses lists, ranges, en dash and dedupes", () => {
    expect(expandMarker("1, 3")).toEqual([1, 3]);
    expect(expandMarker("2-4")).toEqual([2, 3, 4]);
    expect(expandMarker("2–3,2")).toEqual([2, 3]);
  });
  it("drops absurd ranges", () => expect(expandMarker("1-500")).toEqual([]));
});

describe("splitCitations", () => {
  it("splits text and markers", () => {
    expect(splitCitations("BLEU 38.1 [1]. Cost [2, 3].")).toEqual([
      { type: "text", value: "BLEU 38.1 " },
      { type: "cite", nums: [1], raw: "[1]" },
      { type: "text", value: ". Cost " },
      { type: "cite", nums: [2, 3], raw: "[2, 3]" },
      { type: "text", value: "." },
    ]);
  });
  it("leaves non-markers alone", () => {
    expect(splitCitations("a[i] and [x]")).toEqual([{ type: "text", value: "a[i] and [x]" }]);
  });
});

describe("resolveCitations", () => {
  it("maps 1-based to sources and drops out-of-range", () => {
    const sources = [src(8, 0), src(null, 1)];
    const refs = resolveCitations([1, 2, 9], sources);
    expect(refs.map((r) => [r.n, r.label])).toEqual([[1, "tr. 8"], [2, "đoạn 2"]]);
  });
  it("labels", () => expect(citationLabel(src(3), 1)).toBe("tr. 3"));
});

describe("stripCitationMarkers", () => {
  it("removes markers for copy", () => expect(stripCitationMarkers("A [1]. B [2, 3].")).toBe("A. B."));
  it("keeps list indentation and strips trailing spaces per line", () => {
    expect(stripCitationMarkers("- a [1]\n  - b [2]\n    - c  \n")).toBe("- a\n  - b\n    - c\n");
  });
  it("leaves inline code untouched", () => {
    expect(stripCitationMarkers("`x = a[1]` rồi [2]")).toBe("`x = a[1]` rồi");
    expect(stripCitationMarkers("gọi `f(a[1])`  [3] xong")).toBe("gọi `f(a[1])` xong");
  });
  it("leaves fenced code blocks untouched", () => {
    const text = "Mã [1]:\n```py\nx = [2]\n    y  =  a[3]  \n```\nxong [4]";
    expect(stripCitationMarkers(text)).toBe("Mã:\n```py\nx = [2]\n    y  =  a[3]  \n```\nxong");
  });
});
