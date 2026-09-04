import { useEffect, useMemo, useState } from "react";
import { Badge } from "@workspace/ui/components/badge";
import { Separator } from "@workspace/ui/components/separator";
import type { GradeResult, QuestionResult } from "../../lib/grade";
import type { TranscriptPayload } from "../../lib/types";

export function ResultsView({ slug }: { slug: string }) {
  const [result, setResult] = useState<GradeResult | null>(null);
  const [transcript, setTranscript] = useState<TranscriptPayload | null>(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const ts = localStorage.getItem(`ielts:results:${slug}:latest`);
    const raw = ts ? localStorage.getItem(`ielts:results:${slug}:${ts}`) : null;
    if (raw) setResult(JSON.parse(raw));
  }, [slug]);

  useEffect(() => {
    if (!result) return;
    fetch(`/api/tests/${slug}/transcript`)
      .then((r) => r.json() as Promise<TranscriptPayload>)
      .then(setTranscript);
  }, [result, slug]);

  const byPart = useMemo(() => {
    if (!result) return new Map<number, QuestionResult[]>();
    const map = new Map<number, QuestionResult[]>();
    for (const q of result.questions) {
      const part = Math.min(4, Math.max(1, Math.ceil(q.number / 10)));
      if (!map.has(part)) map.set(part, []);
      map.get(part)!.push(q);
    }
    return map;
  }, [result]);

  if (!result) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        No result found for this test on this device. Take the test first.
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-6">
      <div className="text-center space-y-1">
        <p className="text-sm text-muted-foreground">Your score</p>
        <p className="text-5xl font-semibold">
          {result.rawScore}/{result.maxScore}
        </p>
        <p className="text-lg text-muted-foreground">Band {result.band.toFixed(1)}</p>
      </div>

      {Array.from(byPart.entries())
        .sort((a, b) => a[0] - b[0])
        .map(([part, questions]) => (
          <section key={part} className="space-y-2">
            <h2 className="font-medium">Part {part}</h2>
            <div className="divide-y rounded-lg border">
              {questions
                .sort((a, b) => a.number - b.number)
                .map((q) => (
                  <div key={q.number} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                    <span className="font-medium w-10 shrink-0">
                      {q.number}
                      {q.to ? `–${q.to}` : ""}
                    </span>
                    <span className="flex-1 truncate text-muted-foreground">
                      you: {formatGiven(q.given)}
                    </span>
                    <span className="flex-1 truncate">correct: {q.expected}</span>
                    <Badge variant={q.correct ? "default" : "destructive"}>
                      {q.marks}/{q.maxMarks}
                    </Badge>
                  </div>
                ))}
            </div>
          </section>
        ))}

      <Separator />

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Transcript</h2>
          <button
            className="text-sm text-primary underline underline-offset-4"
            onClick={() => setRevealed((v) => !v)}
          >
            {revealed ? "Hide" : "Reveal"} transcript
          </button>
        </div>
        {revealed && transcript && (
          <div className="space-y-6 text-sm">
            {transcript.parts.map((p) => (
              <div key={p.part} className="space-y-1">
                <h3 className="font-medium text-muted-foreground">Part {p.part}</h3>
                {p.transcript.map((line, i) => (
                  <p key={i}>
                    <span className="font-medium">{line.speaker}:</span> {line.line}
                  </p>
                ))}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function formatGiven(given: unknown): string {
  if (Array.isArray(given)) return given.join(", ") || "—";
  return String(given ?? "").trim() || "—";
}
