import { describe, expect, it } from "vitest";
import { plainQuote } from "@/lib/plain-quote";

describe("plainQuote", () => {
  it("strips heading markers and bold", () => {
    expect(plainQuote("### **5.1 Training Data and Batching** We trained")).toBe("5.1 Training Data and Batching We trained");
  });
  it("flattens table rows and drops separator rows", () => {
    expect(plainQuote("| Model | BLEU |\n|---|---|\n| Base | 27.3 |")).toBe("Model BLEU Base 27.3");
    expect(plainQuote("a | b\n--- | ---\nc | d")).toBe("a b c d");
  });
  it("keeps single underscores, citations and math", () => {
    expect(plainQuote("the snake_case var w_q and [3] with $x_i$")).toBe("the snake_case var w_q and [3] with $x_i$");
  });
  it("strips double underscores and backticks", () => {
    expect(plainQuote("__bold__ and `code`")).toBe("bold and code");
  });
  it("handles the empty string", () => {
    expect(plainQuote("")).toBe("");
  });
  it("leaves plain text unchanged", () => {
    expect(plainQuote("Sentences were encoded using byte-pair encoding.")).toBe("Sentences were encoded using byte-pair encoding.");
  });
  it("collapses multi-line input to one line", () => {
    expect(plainQuote("line one\n\n  line two\n# Title\nline three")).toBe("line one line two Title line three");
  });
});
