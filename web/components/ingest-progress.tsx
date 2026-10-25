"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { usePapers, type IngestJob } from "@/components/papers-context";

const STEPS: { key: IngestJob["status"]; label: string }[] = [
  { key: "sending", label: "Gửi file lên máy chủ" },
  { key: "processing", label: "Đọc, tách đoạn và lập chỉ mục" },
  { key: "ready", label: "Sẵn sàng để hỏi" },
];

function stepState(job: IngestJob, i: number): "done" | "now" | "todo" {
  const order = ["sending", "processing", "ready"];
  const cur = job.status === "failed" ? order.indexOf(job.paperId ? "processing" : "sending") : order.indexOf(job.status);
  if (i < cur || job.status === "ready") return "done";
  return i === cur ? "now" : "todo";
}

export function IngestProgress() {
  const { ingests, dismissIngest } = usePapers();
  if (!ingests.length) return null;
  return (
    <section aria-label="Tiến trình thêm bài" className="mt-7 max-w-[720px] space-y-4 border-t border-border pt-4">
      {ingests.map((job) => (
        <div key={job.key} className="text-[14px]">
          <div className="flex items-start justify-between gap-3">
            <p className="font-medium">{job.title}</p>
            {(job.status === "failed" || job.status === "ready") && (
              <button
                onClick={() => dismissIngest(job.key)}
                aria-label="Ẩn"
                className="-my-2.5 -mr-2.5 grid size-11 shrink-0 place-items-center rounded-[6px] text-faint hover:bg-accent md:m-0 md:size-6"
              >
                <X className="size-3.5" />
              </button>
            )}
          </div>
          <ol className="mt-2 grid gap-1.5" aria-live="polite">
            {STEPS.map((s, i) => {
              const st = stepState(job, i);
              const failedHere = job.status === "failed" && st === "now";
              return (
                <li key={s.key} className={`flex items-center gap-2 ${st === "todo" ? "text-faint" : st === "now" ? "text-foreground" : "text-muted-foreground"}`}>
                  <span aria-hidden className={`w-3 text-center text-[12px] ${failedHere ? "text-destructive" : "text-jade"}`}>
                    {failedHere ? "×" : st === "done" ? "✓" : st === "now" ? "•" : "○"}
                  </span>
                  <span className={st === "now" && !failedHere ? "shimmer-text" : undefined}>{s.label}</span>
                </li>
              );
            })}
          </ol>
          {job.status === "ready" && job.paperId && (
            <Link
              href={`/p/${encodeURIComponent(job.paperId)}`}
              className="mt-2 inline-flex min-h-11 items-center text-[14px] text-jade underline underline-offset-2 md:min-h-6"
            >
              Mở bài báo
            </Link>
          )}
          {job.error && <p role="alert" className="mt-2 text-[13px] leading-relaxed text-destructive">{job.error}</p>}
        </div>
      ))}
    </section>
  );
}
