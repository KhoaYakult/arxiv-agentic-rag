"use client";

import { usePapers } from "@/components/papers-context";

// Loi tai /papers (khong phai mat mang): hien ro de khong bi nham voi "thu vien trong" hay "mat du lieu".
export function LibraryError({ className = "" }: { className?: string }) {
  const { error, refresh } = usePapers();
  if (!error) return null;
  return (
    <div role="alert" className={`text-[13px] leading-relaxed text-destructive ${className}`}>
      Không tải được thư viện: {error}{" "}
      <button
        onClick={() => void refresh()}
        className="inline-flex min-h-11 items-center rounded-[6px] px-1 font-medium underline underline-offset-2 md:min-h-6"
      >
        Thử lại
      </button>
    </div>
  );
}
