"use client";
import { usePapers } from "@/components/papers-context";

export function OfflineBanner() {
  const { offline } = usePapers();
  if (!offline) return null;
  return (
    <div role="status" className="border-b border-border bg-muted px-4 py-1.5 text-center text-[13px] text-muted-foreground">
      Không kết nối được máy chủ. Đang thử lại…
    </div>
  );
}
