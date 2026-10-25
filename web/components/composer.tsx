"use client";

import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef } from "react";
import { QUESTION_MAX } from "@/lib/validate";

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
  const canSend = !pending && !disabled && value.trim().length > 0;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSend();
      }}
      className="mx-auto flex w-full max-w-[720px] flex-col gap-2 rounded-composer border border-border-strong bg-card pb-2.5 pl-4 pr-2.5 pt-3 focus-within:ring-2 focus-within:ring-ring"
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
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          // Dang go tieng Viet bang IME: Enter dung de chot chu, KHONG gui.
          if (e.nativeEvent.isComposing || e.keyCode === 229) return;
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (canSend) onSend();
          }
        }}
        className="max-h-[200px] resize-none bg-transparent text-[16px] leading-6 outline-none placeholder:text-faint disabled:opacity-60"
      />
      <div className="flex items-center justify-between">
        <span className="hidden text-[12px] text-faint sm:inline">Enter để gửi · Shift + Enter xuống dòng</span>
        {pending ? (
          <button type="button" onClick={onStop} aria-label="Dừng" className="ml-auto grid size-8 place-items-center rounded-full border-[1.5px] border-foreground">
            <Square className="size-2.5 fill-current" />
          </button>
        ) : (
          <button type="submit" disabled={!canSend} aria-label="Gửi" className="ml-auto grid size-8 place-items-center rounded-full bg-primary text-primary-foreground transition-opacity disabled:opacity-30">
            <ArrowUp className="size-4" />
          </button>
        )}
      </div>
    </form>
  );
}
