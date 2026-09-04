import { useEffect, useMemo, useRef, useState } from "react";
import { Flag, Volume1, Volume2, VolumeX } from "lucide-react";
import { Button } from "@workspace/ui/components/button";
import { Tabs, TabsList, TabsTrigger } from "@workspace/ui/components/tabs";
import { Badge } from "@workspace/ui/components/badge";
import { LayoutRenderer } from "./LayoutRenderer";
import { CountdownOverlay } from "./CountdownOverlay";
import { QuestionNavigator } from "./QuestionNavigator";
import { useExamClock } from "../../lib/useExamClock";
import type { AnswerValue } from "./LayoutRenderer";
import type { TestDetailResponse } from "../../lib/types";

interface StoredAttempt {
  answers: Record<number, AnswerValue>;
  flagged: number[];
}

export function ExamPlayer({ slug }: { slug: string }) {
  const [test, setTest] = useState<TestDetailResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<number, AnswerValue>>({});
  const [flagged, setFlagged] = useState<Set<number>>(new Set());
  const [viewedPart, setViewedPart] = useState<number>(1);
  const [volume, setVolume] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const restoredRef = useRef(false);

  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    fetch(`/api/tests/${slug}`)
      .then((r) => {
        if (!r.ok) throw new Error("test not found");
        return r.json() as Promise<TestDetailResponse>;
      })
      .then((data) => setTest(data))
      .catch((e) => setLoadError(String(e)));
  }, [slug]);

  // restore an in-progress attempt after a refresh/crash
  useEffect(() => {
    if (!test || restoredRef.current) return;
    restoredRef.current = true;
    try {
      const raw = localStorage.getItem(`ielts:attempt:${slug}`);
      if (raw) {
        const stored: StoredAttempt = JSON.parse(raw);
        setAnswers(stored.answers ?? {});
        setFlagged(new Set(stored.flagged ?? []));
      }
    } catch {
      // corrupt localStorage entry - start fresh
    }
  }, [test, slug]);

  useEffect(() => {
    if (!restoredRef.current) return;
    const payload: StoredAttempt = { answers, flagged: Array.from(flagged) };
    try {
      localStorage.setItem(`ielts:attempt:${slug}`, JSON.stringify(payload));
    } catch {
      // storage full/unavailable - answers still live in memory for this session
    }
  }, [answers, flagged, slug]);

  const submitGrade = async () => {
    setSubmitting(true);
    try {
      const res = await fetch(`/api/tests/${slug}/grade`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ answers }),
      });
      const result = await res.json();
      const ts = Date.now();
      localStorage.setItem(`ielts:results:${slug}:${ts}`, JSON.stringify(result));
      localStorage.setItem(`ielts:results:${slug}:latest`, String(ts));
      window.location.href = `/practice/${slug}/results`;
    } finally {
      setSubmitting(false);
    }
  };

  const clock = useExamClock(audioRef, test?.timeline ?? null, () => {
    submitGrade();
  });

  useEffect(() => {
    if (clock.activeSegment?.part) setViewedPart(clock.activeSegment.part);
  }, [clock.activeSegment?.part]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = volume;
  }, [volume]);

  const answeredNumbers = useMemo(() => {
    if (!test) return new Set<number>();
    const set = new Set<number>();
    for (const part of test.student.parts) {
      for (const group of part.question_groups) {
        if (group.type === "multiple_response") {
          const v = answers[group.from] as string[] | undefined;
          if (v && v.length > 0) {
            for (let n = group.from; n <= group.to; n++) set.add(n);
          }
        }
      }
    }
    for (const [key, value] of Object.entries(answers)) {
      const n = Number(key);
      const nonEmpty = Array.isArray(value) ? value.length > 0 : String(value ?? "").trim().length > 0;
      if (nonEmpty) set.add(n);
    }
    return set;
  }, [test, answers]);

  const activeRange: [number, number] | null =
    clock.activeSegment?.q_from != null && clock.activeSegment?.q_to != null
      ? [clock.activeSegment.q_from, clock.activeSegment.q_to]
      : null;

  if (loadError) {
    return <div className="p-8 text-center text-destructive">Could not load this test.</div>;
  }
  if (!test) {
    return <div className="p-8 text-center text-muted-foreground">Loading exam…</div>;
  }

  const totalQuestions = test.student.metadata.total_questions;
  const currentPart = test.student.parts.find((p) => p.part === viewedPart) ?? test.student.parts[0];

  return (
    <div className="flex min-h-svh flex-col">
      <audio ref={audioRef} src={test.audio_url} preload="auto" />

      {!clock.started ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 p-8 text-center">
          <h1 className="text-2xl font-semibold">{test.student.metadata.title}</h1>
          <p className="max-w-md text-muted-foreground">
            Once you click Start, the recording plays once, uninterrupted, start to finish. There
            is no pause, seek, or replay.
          </p>
          <Button size="lg" onClick={clock.start}>
            Start test
          </Button>
        </div>
      ) : (
        <>
          {clock.activeSegment && clock.remaining !== null && (
            <CountdownOverlay kind={clock.activeSegment.kind} remaining={clock.remaining} />
          )}

          <header className="sticky top-0 z-20 flex items-center justify-between gap-4 border-b bg-background px-4 py-2">
            <Tabs value={String(viewedPart)} onValueChange={(v) => setViewedPart(Number(v))}>
              <TabsList>
                {test.student.parts.map((p) => (
                  <TabsTrigger
                    key={p.part}
                    value={String(p.part)}
                    disabled={clock.activeSegment?.part != null && p.part > clock.activeSegment.part}
                  >
                    Part {p.part}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <VolumeControl volume={volume} onChange={setVolume} />
          </header>

          <main className="mx-auto w-full max-w-3xl flex-1 space-y-8 p-4 pb-24">
            <div>
              <h2 className="text-lg font-semibold">Part {currentPart.part}</h2>
              <p className="text-sm text-muted-foreground">{currentPart.situation}</p>
            </div>

            {currentPart.question_groups.map((group) => (
              <section key={group.id} className="space-y-2 rounded-lg border p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    {group.heading && <h3 className="font-medium">{group.heading}</h3>}
                    <p className="text-sm text-muted-foreground whitespace-pre-line">
                      {group.instruction}
                    </p>
                  </div>
                  <FlagRangeButton
                    from={group.from}
                    to={group.to}
                    flagged={flagged}
                    onToggle={(n) =>
                      setFlagged((prev) => {
                        const next = new Set(prev);
                        next.has(n) ? next.delete(n) : next.add(n);
                        return next;
                      })
                    }
                  />
                </div>
                <LayoutRenderer
                  group={group}
                  questions={currentPart.questions.filter((q) => q.group === group.id)}
                  answers={answers}
                  onAnswer={(n, v) => setAnswers((prev) => ({ ...prev, [n]: v }))}
                  visual={currentPart.visuals.find((vv) => vv.id === group.visual_id)}
                  currentQuestion={activeRange ? activeRange[0] : null}
                />
              </section>
            ))}
          </main>

          <QuestionNavigator
            totalQuestions={totalQuestions}
            answered={answeredNumbers}
            flagged={flagged}
            activeRange={activeRange}
            onJump={(n) => {
              const part = test.student.parts.find((p) => n >= p.part * 10 - 9 && n <= p.part * 10);
              if (part && (clock.activeSegment?.part == null || part.part <= clock.activeSegment.part)) {
                setViewedPart(part.part);
              }
            }}
          />

          {submitting && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80">
              <Badge variant="secondary">Submitting…</Badge>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function FlagRangeButton({
  from,
  to,
  flagged,
  onToggle,
}: {
  from: number;
  to: number;
  flagged: Set<number>;
  onToggle: (n: number) => void;
}) {
  const isFlagged = flagged.has(from);
  return (
    <button
      type="button"
      onClick={() => onToggle(from)}
      className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      title={`Flag Q${from}${to !== from ? `-${to}` : ""} for review`}
    >
      <Flag className={`size-3.5 ${isFlagged ? "fill-amber-500 text-amber-500" : ""}`} />
    </button>
  );
}

function VolumeControl({ volume, onChange }: { volume: number; onChange: (v: number) => void }) {
  const Icon = volume === 0 ? VolumeX : volume < 0.5 ? Volume1 : Volume2;
  return (
    <div className="flex items-center gap-2">
      <Icon className="size-4 text-muted-foreground" />
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={volume}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-24"
        aria-label="Volume"
      />
    </div>
  );
}
