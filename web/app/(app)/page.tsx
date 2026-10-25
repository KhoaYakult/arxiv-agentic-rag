"use client";

import { Menu } from "lucide-react";
import { AddPaper } from "@/components/add-paper";
import { useShell } from "@/components/app-shell";
import { IngestProgress } from "@/components/ingest-progress";
import { usePapers } from "@/components/papers-context";
import { BRAND } from "@/lib/brand";

export default function LibraryPage() {
  const { papers, loading } = usePapers();
  const { openSidebar } = useShell();
  const empty = !loading && papers.length === 0;
  return (
    <main className="h-full overflow-y-auto">
      <div className="flex h-12 items-center px-3 md:hidden">
        <button onClick={openSidebar} aria-label="Mở thư viện" className="grid size-11 place-items-center rounded-[6px]">
          <Menu className="size-5" />
        </button>
      </div>
      <div className="px-5 pb-16 pt-6 md:px-16 md:pt-[72px]">
        <h1 className="font-serif text-[26px] font-semibold tracking-[-0.01em] md:text-[30px]">
          {empty ? "Thêm một bài báo để bắt đầu" : "Thêm bài báo"}
        </h1>
        <p className="mt-2 max-w-[560px] text-[16px] leading-relaxed text-muted-foreground">
          {empty ? BRAND.tagline : "Hoặc chọn một bài trong thư viện ở thanh bên để hỏi tiếp."}
        </p>
        <div className="mt-7">
          <AddPaper />
        </div>
        <IngestProgress />
      </div>
    </main>
  );
}
