"use client";

import { useEffect, useState } from "react";

// API chua streaming -> khong biet buoc that; hien 1 dong trung thuc + dong ho giay.
export function Thinking({ startedAt }: { startedAt: number }) {
  const [visible, setVisible] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const show = setTimeout(() => setVisible(true), 200); // khong nhay khi tra loi nhanh
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearTimeout(show);
      clearInterval(tick);
    };
  }, []);
  if (!visible) return null;
  const secs = Math.max(0, Math.floor((now - startedAt) / 1000));
  return (
    <div role="status" aria-live="polite" className="mt-1">
      <div className="flex items-center gap-2.5 text-[14px] text-muted-foreground">
        <span className="shimmer-text">Đang tìm và đọc các đoạn liên quan trong bài…</span>
        <span className="font-mono text-[12px] text-faint tabular-nums">{secs} giây</span>
      </div>
      <div className="mt-4 grid gap-2.5" aria-hidden>
        {["92%", "86%", "64%"].map((w) => (
          <span key={w} className="block h-3 rounded-[4px] bg-muted" style={{ width: w }} />
        ))}
      </div>
    </div>
  );
}
