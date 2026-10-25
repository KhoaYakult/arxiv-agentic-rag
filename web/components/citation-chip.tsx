"use client";

import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import type { CitationRef } from "@/lib/citations";
import { useIsMobile } from "@/lib/use-is-mobile";

const chipClass =
  "relative mx-px inline-flex min-h-[22px] items-center rounded-[5px] bg-jade-soft px-[5px] align-[1px] font-mono text-[11.5px] font-medium leading-none text-jade tabular-nums hover:bg-jade hover:text-card focus-visible:bg-jade focus-visible:text-card before:absolute before:-inset-y-[11px] before:inset-x-0 before:content-[''] md:before:-inset-y-px";

export function CitationChip({ refItem, onOpen }: { refItem: CitationRef; onOpen: (r: CitationRef) => void }) {
  const mobile = useIsMobile();
  const button = (
    <button type="button" className={chipClass} onClick={() => onOpen(refItem)} aria-label={`Nguồn ${refItem.label}, mục ${refItem.source.section}`}>
      {refItem.label}
    </button>
  );
  if (mobile) return button; // cham -> tam truot (khong hover tren cam ung)
  const { source } = refItem;
  return (
    <HoverCard openDelay={150} closeDelay={100}>
      <HoverCardTrigger asChild>{button}</HoverCardTrigger>
      <HoverCardContent align="start" className="w-[380px] rounded-[10px] border border-border bg-popover p-4 shadow-[0_8px_24px_rgba(28,27,25,0.10)]">
        <div className="text-[12px] uppercase tracking-[0.06em] text-muted-foreground">{source.section}</div>
        <blockquote className="mt-2 line-clamp-[8] font-serif text-[15px] italic leading-[1.6]">
          “{source.text || source.content_preview}”
        </blockquote>
        <div className="mt-3 flex items-center justify-between text-[13px] text-faint">
          <span className="tabular-nums">{source.page_num != null ? `Trang ${source.page_num}` : `Đoạn ${refItem.n}`}</span>
          <button type="button" onClick={() => onOpen(refItem)} className="inline-flex min-h-11 items-center px-1 font-medium text-jade hover:underline md:min-h-6">
            {source.page_num != null ? `Mở trang ${source.page_num} →` : "Mở PDF →"}
          </button>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
