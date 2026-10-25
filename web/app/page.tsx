import { BRAND } from "@/lib/brand";

export default function Page() {
  return (
    <main className="mx-auto max-w-[720px] px-6 py-16">
      <h1 className="font-serif text-[30px] font-semibold tracking-[-0.01em]">{BRAND.name}</h1>
      <p className="mt-2 text-muted-foreground">{BRAND.tagline}</p>
      <p className="answer-prose mt-6">
        Tiếng Việt có dấu chồng: ắ ặ ẫ ỡ ữ ự — Transformer đạt <strong>38,1 BLEU</strong>{" "}
        <span className="rounded-sm bg-jade-soft px-1.5 py-px font-mono text-xs text-jade tabular-nums">tr. 8</span>
      </p>
    </main>
  );
}
