"use client";

import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { CitationChip } from "@/components/citation-chip";
import { resolveCitations, type CitationRef } from "@/lib/citations";
import { remarkCitations } from "@/lib/remark-citations";
import type { Source } from "@/lib/types";

// KHONG rehype-raw: HTML trong cau tra loi LLM luon hien dang chu (chong XSS, FIXED_BUGS #21/#25).
export function MarkdownAnswer({
  text, sources, onOpenCitation,
}: { text: string; sources: Source[]; onOpenCitation: (r: CitationRef) => void }) {
  return (
    <div className="answer-prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath, remarkCitations]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
          ),
          // eslint-disable-next-line @typescript-eslint/no-unused-vars
          span: ({ node: _node, className, children, ...props }) => {
            if (typeof className === "string" && className.includes("cite-ref")) {
              const nums = String((props as Record<string, unknown>)["data-nums"] ?? "")
                .split(",").map(Number).filter(Boolean);
              const refs = resolveCitations(nums, sources);
              if (!refs.length) return null; // so ngoai pham vi -> an
              return (
                <>
                  {refs.map((r) => (
                    <CitationChip key={r.n} refItem={r} onOpen={onOpenCitation} />
                  ))}
                </>
              );
            }
            return <span className={className} {...props}>{children}</span>;
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
