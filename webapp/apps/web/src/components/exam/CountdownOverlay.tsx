import type { SegmentKind } from "../../lib/types";

// Real CBT IELTS never covers the paper during prep/checking time - the whole
// point is the student reads/reviews questions while the clock runs. This is
// a sticky banner, not a blocking overlay.
const LABELS: Partial<Record<SegmentKind, string>> = {
  prep: "Preparation time — read the questions before you listen",
  mid_break: "Preparation time — read the next questions",
  checking: "Check your answers",
};

export function CountdownOverlay({ kind, remaining }: { kind: SegmentKind; remaining: number }) {
  const label = LABELS[kind];
  if (!label) return null;

  return (
    <div className="sticky top-0 z-30 flex items-center justify-between gap-4 border-b bg-primary/10 px-4 py-2 text-sm">
      <span>{label}</span>
      <span className="text-lg font-semibold tabular-nums">{remaining}s</span>
    </div>
  );
}
