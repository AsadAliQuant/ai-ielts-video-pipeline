// TS port of generate_test.py's parse_word_limit()/answer_shape() (lines 91-104).
// The word limit is already printed in group.instruction and shown to the
// student on the real exam paper - re-parsing it client-side leaks nothing;
// it just drives the soft "you've gone over the limit" warning.
import { norm } from "./grade";

const WORD_NUM: Record<string, number> = { one: 1, two: 2, three: 3, four: 4, five: 5 };

export function parseWordLimit(instruction: string | undefined): [number | null, boolean] {
  const text = (instruction ?? "").toUpperCase();
  const m = /NO MORE THAN (ONE|TWO|THREE|FOUR|FIVE) WORDS?/.exec(text);
  if (!m) return [null, true];
  return [WORD_NUM[m[1].toLowerCase()], text.includes("NUMBER")];
}

export function wordCount(answer: string): number {
  const toks = norm(answer).split(" ").filter(Boolean);
  const nums = toks.filter((t) => /^[0-9][0-9.,:/']*$/.test(t));
  return toks.length - nums.length;
}
