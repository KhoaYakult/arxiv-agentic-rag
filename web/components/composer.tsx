"use client";

import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { QUESTION_MAX, checkQuestion } from "@/lib/validate";

export function Composer({
  value, onChange, onSend, onStop, pending, disabled, placeholder = "Hỏi tiếp về bài báo này…",
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  pending: boolean;
  disabled: boolean;
  placeholder?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 8 * 24 + 8)}px`; // gian toi 8 dong
  }, [value]);

  // Cau hoi qua ngan: KHONG nuot im lang -> hien thong bao duoi o nhap (xoa khi nguoi dung go tiep).
  const [hint, setHint] = useState<string | null>(null);
  const empty = value.trim().length === 0;
  const attempt = () => {
    if (pending || disabled || empty) return;
    const problem = checkQuestion(value);
    if (problem) {
      setHint(problem);
      return;
    }
    setHint(null);
    onSend();
  };

  return (
    <div className="mx-auto w-full max-w-[720px]">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          attempt();
        }}
        className="flex w-full flex-col gap-2 rounded-composer border border-border-strong bg-card pb-2.5 pl-4 pr-2.5 pt-3 focus-within:ring-2 focus-within:ring-ring"
      >
        <label htmlFor="composer" className="sr-only">Câu hỏi</label>
        <textarea
          id="composer"
          ref={ref}
          rows={1}
          value={value}
          maxLength={QUESTION_MAX}
          disabled={disabled}
          placeholder={placeholder}
          onChange={(e) => {
            setHint(null);
            onChange(e.target.value);
          }}
          onKeyDown={(e) => {
            // Dang go tieng Viet bang IME: Enter dung de chot chu, KHONG gui.
            if (e.nativeEvent.isComposing || e.keyCode === 229) return;
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              attempt();
            }
          }}
          className="max-h-[200px] resize-none bg-transparent text-[16px] leading-6 outline-none placeholder:text-faint disabled:opacity-60"
        />
        <div className="flex items-center justify-between">
          <span className="hidden text-[12px] text-faint sm:inline">Enter để gửi · Shift + Enter xuống dòng</span>
          {pending ? (
            <button type="button" onClick={onStop} aria-label="Dừng" className="ml-auto grid size-11 place-items-center rounded-full border-[1.5px] border-foreground md:size-8">
              <Square className="size-2.5 fill-current" />
            </button>
          ) : (
            <button type="submit" disabled={disabled || empty} aria-label="Gửi" className="ml-auto grid size-11 place-items-center rounded-full bg-primary text-primary-foreground transition-opacity disabled:opacity-30 md:size-8">
              <ArrowUp className="size-4" />
            </button>
          )}
        </div>
      </form>
      {hint && (
        <p role="alert" className="mt-1.5 px-2 text-[13px] text-destructive">{hint}</p>
      )}
    </div>
  );
}
