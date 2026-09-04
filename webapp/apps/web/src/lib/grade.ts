// Literal TS port of generate_test.py's norm()/matches_answer() (lines 75-141)
// and the IELTS Listening raw->band conversion table used across the pipeline.
// Divergence here silently mis-grades students - keep this in lockstep with
// the Python source, not "improved."

export interface AnswerRow {
  number: number;
  to?: number; // present only on collapsed multiple_response rows
  answer: string;
  alternatives: string[];
  type: string;
  group: string | null;
  max_words: number | null;
  number_allowed: boolean | null;
  letters_required: number | null;
}

const LETTER_TYPES = new Set(["multiple_choice", "multiple_response", "matching"]);

// mirrors norm(): NFKD, strip combining marks, curly->straight apostrophe,
// lowercase, replace [^a-z0-9' ] with space, collapse whitespace
export function norm(text: string): string {
  let s = String(text ?? "").normalize("NFKD");
  s = s.replace(/[̀-ͯ]/g, ""); // strip combining marks (U+0300-U+036F)
  s = s.replace(/[’‘]/g, "'"); // curly -> straight apostrophe
  s = s.toLowerCase();
  s = s.replace(/[^a-z0-9' ]+/g, " ");
  return s.replace(/\s+/g, " ").trim();
}

// mirrors matches_answer(): exact equality against answer or any alternative
export function matchesAnswer(
  given: string,
  expected: string,
  alternatives: string[] = []
): boolean {
  const candidates = [expected, ...alternatives];
  const g = norm(given);
  if (!g) return false;
  return candidates.some((c) => String(c ?? "").trim() && g === norm(c));
}

// mirrors the multiple_response/multiple_choice/matching letter comparison in
// validate_test(): split on commas/whitespace/slashes, uppercase, compare as a set.
function parseLetters(value: string): string[] {
  return String(value ?? "")
    .split(/[,\s/]+/)
    .map((p) => p.trim().toUpperCase())
    .filter(Boolean);
}

export interface QuestionResult {
  number: number;
  to?: number;
  correct: boolean;
  marks: number;
  maxMarks: number;
  given: unknown;
  expected: string;
  alternatives: string[];
}

export interface GradeResult {
  rawScore: number;
  maxScore: number;
  band: number;
  questions: QuestionResult[];
}

/**
 * Grades a submission against the server-held answer key.
 * `given` is keyed by the row's canonical `number` (group.from for a
 * collapsed multiple_response row, not every number in its span).
 * - Letter types (multiple_choice/matching): given is a single letter string.
 * - multiple_response: given is a string[] of chosen letters, capped at
 *   letters_required by the UI; scored per-letter up to letters_required marks.
 * - Written types: given is a string, compared via matchesAnswer.
 */
export function gradeSubmission(
  answers: AnswerRow[],
  given: Record<number, unknown>
): GradeResult {
  const questions: QuestionResult[] = [];
  let rawScore = 0;
  let maxScore = 0;

  for (const row of answers) {
    const studentValue = given[row.number];

    if (row.type === "multiple_response") {
      const maxMarks = row.letters_required ?? parseLetters(row.answer).length;
      const expectedLetters = new Set(parseLetters(row.answer));
      const givenLetters = Array.isArray(studentValue)
        ? parseLetters(studentValue.join(","))
        : parseLetters(String(studentValue ?? ""));
      const marks = givenLetters.filter((l) => expectedLetters.has(l)).length;
      const capped = Math.min(marks, maxMarks);

      maxScore += maxMarks;
      rawScore += capped;
      questions.push({
        number: row.number,
        to: row.to,
        correct: capped === maxMarks,
        marks: capped,
        maxMarks,
        given: studentValue,
        expected: row.answer,
        alternatives: row.alternatives,
      });
      continue;
    }

    maxScore += 1;

    let correct: boolean;
    if (LETTER_TYPES.has(row.type)) {
      const g = parseLetters(String(studentValue ?? "")).join(",");
      const expected = parseLetters(row.answer).join(",");
      correct = g === expected && g.length > 0;
    } else {
      correct = matchesAnswer(String(studentValue ?? ""), row.answer, row.alternatives);
    }

    if (correct) rawScore += 1;
    questions.push({
      number: row.number,
      correct,
      marks: correct ? 1 : 0,
      maxMarks: 1,
      given: studentValue,
      expected: row.answer,
      alternatives: row.alternatives,
    });
  }

  return { rawScore, maxScore, band: rawToBand(rawScore), questions };
}

// Published IELTS Listening raw/40 -> band conversion table.
const BAND_TABLE: Array<[number, number, number]> = [
  [39, 40, 9.0],
  [37, 38, 8.5],
  [35, 36, 8.0],
  [32, 34, 7.5],
  [30, 31, 7.0],
  [26, 29, 6.5],
  [23, 25, 6.0],
  [18, 22, 5.5],
  [16, 17, 5.0],
  [13, 15, 4.5],
  [11, 12, 4.0],
];

export function rawToBand(raw: number): number {
  for (const [lo, hi, band] of BAND_TABLE) {
    if (raw >= lo && raw <= hi) return band;
  }
  if (raw > 40) return 9.0;
  return raw > 0 ? 3.5 : 0;
}
