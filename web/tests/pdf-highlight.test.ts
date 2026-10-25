import { describe, expect, it } from "vitest";
import { findHighlight } from "@/lib/pdf-highlight";

const items = [
  "6 Results",
  "On the WMT 2014 English-to-French translation task, our big model achieves a BLEU score of 41.0,",
  "outperforming all of the previously published single models, at less than 1/4 the training",
  "cost of the previous state-of-the-art model. The Transformer (big) model trained for English-to-",
  "French used dropout rate P",
];

describe("findHighlight", () => {
  it("finds a quote spanning several items", () => {
    const q = "our big model achieves a BLEU score of 41.0, outperforming all of the previously published single models";
    expect([...(findHighlight(items, q) ?? [])].sort()).toEqual([1, 2]);
  });
  it("tolerates markdown, extra whitespace and case", () => {
    const q = "**Outperforming**   all of the previously   published single models, at less than 1/4 the training cost";
    expect([...(findHighlight(items, q) ?? [])].sort()).toEqual([2, 3]);
  });
  it("joins words hyphenated across line breaks", () => {
    const q = "The Transformer (big) model trained for English-to-French used dropout rate";
    const hit = findHighlight(items, q);
    expect(hit?.has(3)).toBe(true);
    expect(hit?.has(4)).toBe(true);
  });
  it("matches ligatures via NFKC", () => {
    expect(findHighlight(["the eﬃcient attention mechanism is used for all layers here"], "the efficient attention mechanism is used for all layers")?.has(0)).toBe(true);
  });
  it("uses the quote's tail when the chunk starts on the previous page", () => {
    const q = "text that was on page seven and is not here at all. " + "outperforming all of the previously published single models, at less than";
    expect(findHighlight(items, q)?.has(2)).toBe(true);
  });
  it("returns null when nothing matches or input is empty", () => {
    expect(findHighlight(items, "completely unrelated sentence about protein folding and cells")).toBeNull();
    expect(findHighlight([], "anything at all here for the test")).toBeNull();
    expect(findHighlight(items, "")).toBeNull();
  });
  it("never throws on odd input", () => {
    expect(findHighlight(["", "  ", "**"], "**__||``>>  ")).toBeNull();
    expect(findHighlight(["a"], "x".repeat(5000))).toBeNull();
    expect(findHighlight(["-", "-"], "- - - - - - - - - - - -")).toBeNull();
  });
});
