"use client";

import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import type { CitationRef } from "@/lib/citations";
import { plainQuote } from "@/lib/plain-quote";

// Luon co nut mo PDF: has_pdf co the chua kip cap nhat (PDF upload sau khi 'ready'); panel tu bao 404.
export function PdfSheet({
  refItem, onOpenPdf, onClose,
}: { refItem: CitationRef | null; onOpenPdf: () => void; onClose: () => void }) {
  return (
    <Sheet open={refItem !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="bottom" className="h-[58dvh] rounded-t-[18px] px-5 pb-[max(20px,env(safe-area-inset-bottom))] pt-3">
        <div aria-hidden className="mx-auto mb-3 h-1 w-9 rounded-full bg-border-strong" />
        <SheetTitle className="text-[12px] font-normal uppercase tracking-[0.06em] text-muted-foreground">
          {refItem?.source.section}
          {refItem?.source.page_num != null && <> · trang {refItem.source.page_num}</>}
        </SheetTitle>
        <blockquote className="mt-2 max-h-[30dvh] overflow-y-auto font-serif text-[15px] italic leading-[1.6]">
          “{plainQuote(refItem?.source.text || refItem?.source.content_preview || "")}”
        </blockquote>
        <button onClick={onOpenPdf} className="mt-4 h-12 w-full rounded-[10px] bg-primary text-[15px] font-medium text-primary-foreground">
          {refItem?.source.page_num != null ? `Mở trang ${refItem.source.page_num}` : "Mở PDF"}
        </button>
      </SheetContent>
    </Sheet>
  );
}
