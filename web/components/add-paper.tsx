"use client";

import { useRef, useState } from "react";
import { usePapers } from "@/components/papers-context";
import { MAX_UPLOAD_MB, checkPdfFile, extractArxivId } from "@/lib/validate";

export function AddPaper() {
  const { startUpload, startArxiv } = usePapers();
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [arxiv, setArxiv] = useState("");
  const arxivId = arxiv.trim() ? extractArxivId(arxiv) : null;

  async function take(file: File | undefined) {
    if (!file) return;
    const check = await checkPdfFile(file);
    if (!check.ok) {
      setFileError(check.message);
      return;
    }
    setFileError(null);
    await startUpload(file);
  }

  return (
    <div className="grid max-w-[720px] gap-4 sm:grid-cols-2">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          void take(e.dataTransfer.files[0]);
        }}
        className={`rounded-[10px] border-[1.5px] border-dashed bg-card p-5 transition-colors ${drag ? "border-jade" : "border-border-strong"}`}
      >
        <p className="text-[15px] font-medium">Kéo thả file PDF vào đây</p>
        <p className="mt-1 text-[13px] leading-relaxed text-faint">
          hoặc{" "}
          <button type="button" onClick={() => input.current?.click()} className="inline-flex min-h-11 items-center text-jade underline underline-offset-2 md:min-h-6">
            chọn file
          </button>{" "}
          · tối đa {MAX_UPLOAD_MB} MB
        </p>
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          aria-label="Chọn file PDF"
          onChange={(e) => {
            void take(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        {fileError && <p role="alert" className="mt-2 text-[13px] text-destructive">{fileError}</p>}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (arxivId) {
            void startArxiv(arxivId);
            setArxiv("");
          }
        }}
        className="rounded-[10px] border-[1.5px] border-dashed border-border-strong bg-card p-5"
      >
        <label htmlFor="arxiv" className="text-[15px] font-medium">Nhập từ arXiv</label>
        <p className="mt-1 text-[13px] text-faint">Dán mã hoặc link, kể cả bài lớn tới 30 MB</p>
        <div className="mt-3 flex gap-2">
          <input
            id="arxiv"
            value={arxiv}
            onChange={(e) => setArxiv(e.target.value)}
            placeholder="2401.15884"
            className="h-11 min-w-0 flex-1 rounded-[6px] border border-border-strong bg-background px-2.5 font-mono text-[16px] sm:h-10 sm:text-[14px]"
          />
          <button
            type="submit"
            disabled={!arxivId}
            className="h-11 rounded-[6px] bg-primary px-3.5 text-[14px] font-medium text-primary-foreground disabled:opacity-40 sm:h-10"
          >
            Thêm
          </button>
        </div>
        {arxiv.trim() && !arxivId && (
          <p role="alert" className="mt-2 text-[13px] text-destructive">
            Không nhận ra mã arXiv. Ví dụ đúng: 2401.15884 hoặc arxiv.org/abs/2401.15884
          </p>
        )}
      </form>
    </div>
  );
}
