// Marker trich dan [n] do LLM viet (app/llm/prompt_templates.py). CUNG grammar voi
// app/agent/rag_graph.py::CITATION_MARKER_RE va eval/metrics.py::citation_markers.
import type { Source } from "@/lib/types";

const MARKER_RE = /\[(\d{1,3}(?:\s*[,–-]\s*\d{1,3})*)\]/g;
const MAX_RANGE = 10;

export type Segment = { type: "text"; value: string } | { type: "cite"; nums: number[]; raw: string };

export function expandMarker(inner: string): number[] {
  const out: number[] = [];
  for (const raw of inner.split(",")) {
    const part = raw.trim();
    const m = /^(\d+)\s*[–-]\s*(\d+)$/.exec(part);
    if (m) {
      const a = Number(m[1]);
      const b = Number(m[2]);
      if (b >= a && b - a < MAX_RANGE) for (let i = a; i <= b; i++) out.push(i);
    } else if (/^\d+$/.test(part)) {
      out.push(Number(part));
    }
  }
  return [...new Set(out)];
}

export function splitCitations(text: string): Segment[] {
  const segs: Segment[] = [];
  let last = 0;
  for (const m of text.matchAll(MARKER_RE)) {
    const nums = expandMarker(m[1]);
    if (!nums.length) continue; // vd [1-500]: khong phai marker hop le, de nguyen chu
    const idx = m.index ?? 0;
    if (idx > last) segs.push({ type: "text", value: text.slice(last, idx) });
    segs.push({ type: "cite", nums, raw: m[0] });
    last = idx + m[0].length;
  }
  if (last < text.length) segs.push({ type: "text", value: text.slice(last) });
  return segs;
}

export interface CitationRef {
  n: number;
  source: Source;
  label: string;
}

export function citationLabel(source: Source, n: number): string {
  return source.page_num != null ? `tr. ${source.page_num}` : `đoạn ${n}`;
}

export function resolveCitations(nums: number[], sources: Source[]): CitationRef[] {
  return nums
    .filter((n) => n >= 1 && n <= sources.length)
    .map((n) => ({ n, source: sources[n - 1], label: citationLabel(sources[n - 1], n) }));
}

// Bao ve code (fenced + inline) bang placeholder khong-phai-whitespace, roi chay CUNG cac regex
// voi app/agent/rag_graph.py::strip_citation_markers (chi gom khoang trang GIUA dong, giu indent list).
const CODE_RE = /```[\s\S]*?(?:```|$)|`[^`\n]+`/g;

export function stripCitationMarkers(text: string): string {
  const kept: string[] = [];
  const guarded = text.replace(CODE_RE, (m) => `\uE000${kept.push(m) - 1}\uE001`);
  const out = guarded
    .replace(MARKER_RE, "")
    .replace(/[ \t]+([.,;:!?])/g, "$1")
    .replace(/(?<=\S)[ \t]{2,}/g, " ")
    .replace(/[ \t]+$/gm, "");
  return out.replace(/\uE000(\d+)\uE001/g, (_, i) => kept[Number(i)]);
}
