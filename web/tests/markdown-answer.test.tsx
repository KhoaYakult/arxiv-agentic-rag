// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MarkdownAnswer } from "@/components/markdown-answer";
import type { Source } from "@/lib/types";

const sources: Source[] = [{ chunk_id: "c1", section: "6 Results", content_preview: "p", text: "Transformer 38.1", page_num: 8 }];

describe("MarkdownAnswer", () => {
  it("renders markdown and turns valid markers into chips", () => {
    render(<MarkdownAnswer text={"**38.1 BLEU** [1] and [7]"} sources={sources} onOpenCitation={vi.fn()} />);
    expect(screen.getByText("38.1 BLEU").tagName).toBe("STRONG");
    expect(screen.getByRole("button", { name: /tr\. 8/ })).toBeInTheDocument();
    expect(screen.queryByText("[7]")).toBeNull();
  });
  it("keeps markers literal inside code and renders HTML as text", () => {
    const { container } = render(
      <MarkdownAnswer text={"`a[1]` <script>alert(1)</script><img src=x onerror=alert(2)>"} sources={sources} onOpenCitation={vi.fn()} />,
    );
    expect(container.querySelector("code")?.textContent).toBe("a[1]");
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });
});
