"use client";

import dynamic from "next/dynamic";
import type { PdfTarget } from "@/components/paper-view";

// react-pdf/pdf.js chi chay o trinh duyet.
export const PdfPanel = dynamic(() => import("@/components/pdf-panel").then((m) => m.PdfPanel), {
  ssr: false,
  loading: () => <div className="h-full w-[45%] border-l border-border bg-muted" />,
});

export type { PdfTarget };
