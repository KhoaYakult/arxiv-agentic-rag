"use client";

import { Check, Copy, RotateCcw } from "lucide-react";
import { memo, useState } from "react";
import { MarkdownAnswer } from "@/components/markdown-answer";
import type { ChatMessage } from "@/lib/chat-store";
import { citationLabel, stripCitationMarkers, type CitationRef } from "@/lib/citations";

export function UserMessage({ msg }: { msg: ChatMessage }) {
  return (
    <div className="ml-auto w-fit max-w-[80%] whitespace-pre-wrap rounded-[14px] bg-user-bubble px-3.5 py-2.5 text-[15px] leading-[1.55]">
      {msg.content}
    </div>
  );
}

function metaLine(msg: ChatMessage): string {
  const parts = [`Đã đọc ${msg.sources?.length ?? 0} đoạn`];
  if (msg.rewriteCount) parts.push(`viết lại câu hỏi ${msg.rewriteCount} lần`);
  if (msg.elapsedMs != null) parts.push(`${Math.round(msg.elapsedMs / 1000)} giây`);
  return parts.join(" · ");
}

function AssistantMessageBase({
  msg, onOpenCitation, onRetry, onAskAgain,
}: {
  msg: ChatMessage;
  onOpenCitation: (r: CitationRef) => void;
  onRetry: (msg: ChatMessage) => void;
  onAskAgain: () => void;
}) {
  const [copied, setCopied] = useState(false);

  if (msg.error) {
    return (
      <div className="border-l-2 border-destructive pl-3 text-[14px] leading-relaxed">
        <p className="text-destructive">{msg.error}</p>
        <button onClick={() => onRetry(msg)} className="mt-1 flex min-h-11 items-center gap-1.5 text-[13px] font-medium text-foreground hover:underline md:min-h-6">
          <RotateCcw className="size-3.5" /> Thử lại
        </button>
      </div>
    );
  }
  if (msg.stopped) return <p className="text-[13px] text-faint">Đã dừng.</p>;

  const sources = msg.sources ?? [];
  const seen = new Set<string>();
  const sourceRows = sources
    .map((s, i) => ({ s, n: i + 1 }))
    .filter(({ s }) => {
      const k = `${s.page_num}|${s.section}`;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });

  return (
    <div>
      <div className="mb-2.5 flex items-center gap-2 text-[13px] text-faint">
        <span aria-hidden className={`size-1.5 rounded-full ${msg.grade === "no" ? "bg-faint" : "bg-jade"}`} />
        {metaLine(msg)}
      </div>
      <MarkdownAnswer text={msg.content} sources={sources} onOpenCitation={onOpenCitation} />
      {msg.grade === "no" && (
        <p className="mt-3 border-l-2 border-border-strong pl-3 text-[14px] leading-relaxed text-muted-foreground">
          Tài liệu tìm được có thể không đủ để trả lời chắc chắn.
        </p>
      )}
      {sourceRows.length > 0 && (
        <div className="mt-3.5 flex flex-wrap items-center gap-1.5 text-[13px] text-muted-foreground">
          <span>Nguồn</span>
          {sourceRows.map(({ s, n }) => (
            <button
              key={s.chunk_id}
              onClick={() => onOpenCitation({ n, source: s, label: citationLabel(s, n) })}
              className="flex min-h-11 max-w-full items-center gap-1 truncate rounded-[6px] border border-border bg-card px-2 py-[3px] hover:border-border-strong md:min-h-6"
            >
              <b className="font-mono text-[12px] font-medium text-foreground tabular-nums">{citationLabel(s, n)}</b> · {s.section}
            </button>
          ))}
        </div>
      )}
      <div className="mt-1.5 flex gap-4 text-[13px] text-faint">
        <button
          onClick={async () => {
            // Chi bao "Da chep" khi clipboard that su ghi duoc (http / bi chan quyen -> khong noi doi).
            try {
              await navigator.clipboard.writeText(stripCitationMarkers(msg.content));
            } catch {
              return;
            }
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
          className="flex min-h-11 items-center gap-1 px-1 hover:text-foreground md:min-h-6"
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />} {copied ? "Đã chép" : "Sao chép"}
        </button>
        <button onClick={onAskAgain} className="flex min-h-11 items-center gap-1 px-1 hover:text-foreground md:min-h-6">
          <RotateCcw className="size-3.5" /> Hỏi lại
        </button>
      </div>
    </div>
  );
}

export const AssistantMessage = memo(AssistantMessageBase);
