// Splits a question_group.layout string on {N} blanks into renderable runs.
// Covers all six completion types plus plan_map_labelling, whose layout is
// just "11. {11}\n12. {12}...".

export type LayoutToken = { kind: "text"; value: string } | { kind: "blank"; number: number };

export function parseLayout(layout: string): LayoutToken[] {
  const tokens: LayoutToken[] = [];
  const re = /\{(\d+)\}/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(layout)) !== null) {
    if (m.index > last) tokens.push({ kind: "text", value: layout.slice(last, m.index) });
    tokens.push({ kind: "blank", number: Number(m[1]) });
    last = re.lastIndex;
  }
  if (last < layout.length) tokens.push({ kind: "text", value: layout.slice(last) });
  return tokens;
}
