"use client";

import { memo, useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { CitationChip } from "@/components/citation-chip";
import { resolveCitations, type CitationRef } from "@/lib/citations";
import { remarkCitations } from "@/lib/remark-citations";
import type { Source } from "@/lib/types";

// Hoist ra ngoai render: mang plugin on dinh -> react-markdown khong dung lai pipeline.
const REMARK_PLUGINS = [remarkGfm, remarkMath, remarkCitations];
const REHYPE_PLUGINS = [rehypeKatex];

// KHONG rehype-raw: HTML trong cau tra loi LLM luon hien dang chu (chong XSS, FIXED_BUGS #21/#25).
// Anh markdown cung bi chan: <img src> se bao URL cua nguoi dung cho server la (tracking/exfil).
function MarkdownAnswerBase({
  text, sources, onOpenCitation,
}: { text: string; sources: Source[]; onOpenCitation: (r: CitationRef) => void }) {
  const components = useMemo<Components>(
    () => ({
      a: ({ href, children }) => (
        <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
      ),
      img: () => null,
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      span: ({ node: _node, className, children, ...props }) => {
        if (typeof className === "string" && className.includes("cite-ref")) {
          const nums = String((props as Record<string, unknown>)["data-nums"] ?? "")
            .split(",").map(Number).filter(Boolean);
          const seen = new Set<string>();
          // Cung nhan (vd 2 doan cung trang 1) -> 1 chip, giu cai dau.
          const refs = resolveCitations(nums, sources).filter((r) => !seen.has(r.label) && !!seen.add(r.label));
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
    }),
    [sources, onOpenCitation],
  );
  return (
    <div className="answer-prose">
      <ReactMarkdown remarkPlugins={REMARK_PLUGINS} rehypePlugins={REHYPE_PLUGINS} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
}

export const MarkdownAnswer = memo(MarkdownAnswerBase);
