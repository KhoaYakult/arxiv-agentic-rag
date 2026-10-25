"use client";

import { ChevronLeft, ChevronRight, Minus, Plus, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import type { PdfTarget } from "@/components/paper-view";
import { ApiCallError, api } from "@/lib/client-api";
import { findHighlight } from "@/lib/pdf-highlight";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const escapeHtml = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const ICON_BTN = "grid size-11 place-items-center rounded-[6px] hover:bg-accent md:size-8";
const FOOT_BTN = "flex min-h-11 items-center gap-1 px-2 hover:text-foreground disabled:opacity-40 md:min-h-6";

export function PdfPanel({
  paperId, target, onClose, fullscreen = false,
}: { paperId: string; target: PdfTarget; onClose: () => void; fullscreen?: boolean }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retried, setRetried] = useState(false);
  const [numPages, setNumPages] = useState(0);
  const [page, setPage] = useState(target.page);
  const [scale, setScale] = useState(1);
  // items gan voi so trang cua chung: sang trang khac roi quay lai khong duoc dung text cu.
  const [text, setText] = useState<{ page: number; items: string[] } | null>(null);
  const [width, setWidth] = useState(560);
  const [seenToken, setSeenToken] = useState(target.token);
  const scroller = useRef<HTMLDivElement>(null);

  // Bam trich dan khac (token moi) -> nhay ve trang cua trich dan do. Dieu chinh state ngay luc render
  // (cach React khuyen dung thay cho useEffect + setState).
  if (seenToken !== target.token) {
    setSeenToken(target.token);
    setPage(target.page);
    setText(null);
  }

  const loadUrl = useCallback(async () => {
    try {
      setUrl((await api.pdfUrl(paperId)).url);
      setError(null);
    } catch (e) {
      const err = e as ApiCallError;
      setError(err.code === "not_found" ? "Bài này không có bản PDF gốc." : err.message);
    }
  }, [paperId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadUrl();
  }, [loadUrl]);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(Math.max(280, el.clientWidth - 32)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const onTargetPage = page === target.page && target.quote.length > 0;
  const pageItems = text && text.page === page ? text.items : null;
  const highlight = useMemo(() => {
    if (!onTargetPage || !pageItems) return null;
    try {
      return findHighlight(pageItems, target.quote);
    } catch {
      return null; // khong bao gio de loi to lam hong panel: coi nhu khong tim thay
    }
  }, [onTargetPage, pageItems, target.quote]);
  const missed = onTargetPage && pageItems !== null && pageItems.length > 0 && highlight === null;

  const renderText = useCallback(
    ({ str, itemIndex }: { str: string; itemIndex: number }) =>
      highlight?.has(itemIndex) ? `<mark class="pdf-mark">${escapeHtml(str)}</mark>` : escapeHtml(str),
    [highlight],
  );

  return (
    <section
      aria-label="Bản PDF"
      className={`flex min-w-0 flex-col bg-muted ${fullscreen ? "fixed inset-0 z-50" : "h-full w-[45%] max-w-[760px] shrink-0 border-l border-border"}`}
    >
      <div className="flex h-[52px] shrink-0 items-center justify-between gap-2 border-b border-border px-4 text-[13px] text-muted-foreground">
        <div className="flex min-w-0 items-baseline gap-1.5">
          {target.section && <span className="min-w-0 truncate">{target.section} ·</span>}
          <b className="shrink-0 font-mono text-[12px] font-medium text-foreground tabular-nums">
            tr. {page}{numPages ? ` / ${numPages}` : ""}
          </b>
        </div>
        <div className="flex items-center gap-1">
          <button aria-label="Thu nhỏ" onClick={() => setScale((s) => Math.max(0.6, s - 0.15))} className={ICON_BTN}><Minus className="size-4" /></button>
          <button aria-label="Phóng to" onClick={() => setScale((s) => Math.min(2.5, s + 0.15))} className={ICON_BTN}><Plus className="size-4" /></button>
          <button aria-label="Đóng PDF" onClick={onClose} className={ICON_BTN}><X className="size-4" /></button>
        </div>
      </div>

      {missed && (
        <p role="status" className="border-b border-border bg-card px-4 py-2 text-[13px] leading-relaxed text-muted-foreground">
          Không tìm thấy vị trí chính xác của đoạn trích trên trang này. Đoạn trích:{" "}
          <span className="font-serif italic">“{target.quote.slice(0, 220)}{target.quote.length > 220 ? "…" : ""}”</span>
        </p>
      )}

      <div ref={scroller} className="min-h-0 flex-1 overflow-auto p-4">
        {error ? (
          <p className="mt-10 text-center text-[14px] text-muted-foreground">{error}</p>
        ) : !url ? (
          <p className="mt-10 text-center text-[14px] text-faint">Đang mở PDF…</p>
        ) : (
          <Document
            file={url}
            onLoadSuccess={({ numPages: n }) => setNumPages(n)}
            onLoadError={() => {
              // signed URL co the het han: lay lai dung 1 lan
              if (!retried) {
                setRetried(true);
                void loadUrl();
              } else setError("Không tải được PDF. Hãy thử lại sau.");
            }}
            loading={<p className="mt-10 text-center text-[14px] text-faint">Đang mở PDF…</p>}
          >
            <Page
              key={`${page}-${target.token}`}
              pageNumber={page}
              width={width * scale}
              className={`mx-auto w-fit shadow-[0_1px_3px_rgba(0,0,0,0.12)] ${missed ? "outline outline-2 outline-[var(--highlight)]" : ""}`}
              onGetTextSuccess={({ items: its }) => setText({ page, items: its.map((it) => ("str" in it ? it.str : "")) })}
              customTextRenderer={renderText}
              onRenderTextLayerSuccess={() => {
                scroller.current?.querySelector("mark.pdf-mark")?.scrollIntoView({ block: "center" });
              }}
            />
          </Document>
        )}
      </div>

      <div className="flex shrink-0 justify-between border-t border-border px-2 py-1 font-mono text-[12px] text-faint">
        <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className={FOOT_BTN}>
          <ChevronLeft className="size-3.5" /> tr. {Math.max(1, page - 1)}
        </button>
        <button disabled={numPages > 0 && page >= numPages} onClick={() => setPage((p) => p + 1)} className={FOOT_BTN}>
          tr. {page + 1} <ChevronRight className="size-3.5" />
        </button>
      </div>
    </section>
  );
}
