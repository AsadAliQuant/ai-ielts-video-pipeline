import { Fragment } from "react";
import { Input } from "@workspace/ui/components/input";
import { RadioGroup, RadioGroupItem } from "@workspace/ui/components/radio-group";
import { Checkbox } from "@workspace/ui/components/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@workspace/ui/components/select";
import { ChevronDown } from "lucide-react";
import { parseLayout } from "../../lib/layout";
import { parseWordLimit, wordCount } from "../../lib/wordLimit";
import type { Question, QuestionGroup, Visual } from "../../lib/types";

export type AnswerValue = string | string[];

interface LayoutRendererProps {
  group: QuestionGroup;
  questions: Question[];
  answers: Record<number, AnswerValue>;
  onAnswer: (number: number, value: AnswerValue) => void;
  visual?: Visual;
  currentQuestion: number | null;
}

const TEXT_INPUT_TYPES = new Set([
  "form_completion",
  "note_completion",
  "table_completion",
  "flow_chart_completion",
  "sentence_completion",
  "summary_completion",
]);

/** Split a flowchart layout on ASCII/Unicode arrow delimiters or double-newlines. */
function splitFlowchartSteps(layout: string): string[] {
  // Match: \n  (optional spaces)  | or │  \n  (optional spaces)  v or ▼  \n
  const arrowRe = /\n\s*[|│]\s*\n\s*[v▼]\s*\n/u;
  let steps = layout.split(arrowRe);
  // Fallback: double-newline separated (Step N: style)
  if (steps.length <= 1) {
    steps = layout.split(/\n{2,}/);
  }
  return steps.map((s) => s.trim()).filter(Boolean);
}

export function LayoutRenderer({
  group,
  questions,
  answers,
  onAnswer,
  visual,
  currentQuestion,
}: LayoutRendererProps) {
  const [maxWords] = parseWordLimit(group.instruction);

  // Flowchart: render steps as bordered cards with arrow connectors
  if (group.type === "flow_chart_completion" && group.layout) {
    const steps = splitFlowchartSteps(group.layout);
    if (steps.length > 1) {
      return (
        <div className="flex flex-col items-center gap-0">
          {steps.map((step, si) => {
            const tokens = parseLayout(step);
            return (
              <Fragment key={si}>
                <div className="w-full rounded-lg border bg-muted/30 px-4 py-2.5 text-sm leading-7">
                  {tokens.map((tok, ti) =>
                    tok.kind === "text" ? (
                      <Fragment key={ti}>{tok.value}</Fragment>
                    ) : (
                      <BlankInput
                        key={ti}
                        number={tok.number}
                        value={(answers[tok.number] as string) ?? ""}
                        onChange={(v) => onAnswer(tok.number, v)}
                        maxWords={maxWords}
                        active={currentQuestion === tok.number}
                      />
                    )
                  )}
                </div>
                {si < steps.length - 1 && (
                  <div className="flex items-center justify-center py-1 text-muted-foreground">
                    <ChevronDown className="h-5 w-5" />
                  </div>
                )}
              </Fragment>
            );
          })}
        </div>
      );
    }
  }

  if (TEXT_INPUT_TYPES.has(group.type) && group.layout) {
    const tokens = parseLayout(group.layout);
    return (
      <div className="space-y-1 whitespace-pre-wrap font-mono text-sm leading-8">
        {tokens.map((tok, i) =>
          tok.kind === "text" ? (
            <Fragment key={i}>{tok.value}</Fragment>
          ) : (
            <BlankInput
              key={i}
              number={tok.number}
              value={(answers[tok.number] as string) ?? ""}
              onChange={(v) => onAnswer(tok.number, v)}
              maxWords={maxWords}
              active={currentQuestion === tok.number}
            />
          )
        )}
      </div>
    );
  }

  if (group.type === "short_answer") {
    return (
      <div className="space-y-4">
        {questions.map((q) => (
          <div key={q.number} className="flex flex-col gap-1.5">
            <div className="flex gap-2 text-sm">
              <span className="font-medium">{q.number}.</span>
              <span>{q.text}</span>
            </div>
            <BlankInput
              number={q.number}
              value={(answers[q.number] as string) ?? ""}
              onChange={(v) => onAnswer(q.number, v)}
              maxWords={maxWords}
              active={currentQuestion === q.number}
            />
          </div>
        ))}
      </div>
    );
  }

  if (group.type === "multiple_choice") {
    return (
      <div className="space-y-6">
        {questions.map((q) => (
          <div key={q.number} className="space-y-2">
            <div className="flex gap-2 text-sm font-medium">
              <span>{q.number}.</span>
              <span>{q.text}</span>
            </div>
            <RadioGroup
              value={(answers[q.number] as string) ?? null}
              onValueChange={(v) => onAnswer(q.number, String(v))}
              className="gap-2 ps-6"
            >
              {q.options.map((opt) => (
                <label
                  key={opt.letter}
                  className="flex items-center gap-2 text-sm cursor-pointer"
                >
                  <RadioGroupItem value={opt.letter} />
                  <span className="font-medium">{opt.letter}.</span>
                  <span>{opt.text}</span>
                </label>
              ))}
            </RadioGroup>
          </div>
        ))}
      </div>
    );
  }

  if (group.type === "multiple_response") {
    const cap = group.letters_required ?? 2;
    const canonicalNumber = group.from;
    const selected = new Set((answers[canonicalNumber] as string[]) ?? []);
    const options = uniqueOptions(questions);

    const toggle = (letter: string) => {
      const next = new Set(selected);
      if (next.has(letter)) {
        next.delete(letter);
      } else {
        if (next.size >= cap) return;
        next.add(letter);
      }
      onAnswer(canonicalNumber, Array.from(next));
    };

    return (
      <div className="space-y-2">
        <p className="text-sm text-muted-foreground">
          Questions {group.from}
          {group.to !== group.from ? `–${group.to}` : ""}: choose {cap} letter
          {cap > 1 ? "s" : ""}.
        </p>
        <div className="space-y-2 ps-1">
          {options.map((opt) => (
            <label key={opt.letter} className="flex items-center gap-2 text-sm cursor-pointer">
              <Checkbox
                checked={selected.has(opt.letter)}
                onCheckedChange={() => toggle(opt.letter)}
              />
              <span className="font-medium">{opt.letter}.</span>
              <span>{opt.text}</span>
            </label>
          ))}
        </div>
        {selected.size === cap && (
          <p className="text-xs text-muted-foreground">
            {cap} of {cap} selected
          </p>
        )}
      </div>
    );
  }

  if (group.type === "matching" || group.type === "plan_map_labelling") {
    const showBoxedOptions = group.options && group.options.length > 0;
    return (
      <div className="grid gap-6 md:grid-cols-[1fr_auto]">
        <div className="space-y-3">
          {showBoxedOptions && (
            <div className="rounded-lg border bg-muted/30 p-3 text-sm space-y-1">
              {group.options.map((opt) => (
                <div key={opt.letter}>
                  <span className="font-medium">{opt.letter}.</span> {opt.text}
                </div>
              ))}
            </div>
          )}
          {questions.map((q) => (
            <div key={q.number} className="flex items-center gap-3 text-sm">
              <span className="font-medium">{q.number}.</span>
              <span className="flex-1">{q.text}</span>
              {showBoxedOptions ? (
                <Select
                  value={(answers[q.number] as string) ?? null}
                  onValueChange={(v) => onAnswer(q.number, String(v))}
                >
                  <SelectTrigger className="w-20">
                    <SelectValue placeholder="-" />
                  </SelectTrigger>
                  <SelectContent>
                    {group.options.map((opt) => (
                      <SelectItem key={opt.letter} value={opt.letter}>
                        {opt.letter}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <BlankInput
                  number={q.number}
                  value={(answers[q.number] as string) ?? ""}
                  onChange={(v) => onAnswer(q.number, v)}
                  maxWords={maxWords}
                  active={currentQuestion === q.number}
                />
              )}
            </div>
          ))}
        </div>
        {visual?.image_url && (
          <img
            src={visual.image_url}
            alt={visual.title}
            className="max-w-xs rounded-lg border object-contain"
          />
        )}
      </div>
    );
  }

  return null;
}

function uniqueOptions(questions: Question[]) {
  const seen = new Map<string, { letter: string; text: string }>();
  for (const q of questions) {
    for (const opt of q.options) {
      if (!seen.has(opt.letter)) seen.set(opt.letter, opt);
    }
  }
  return Array.from(seen.values()).sort((a, b) => a.letter.localeCompare(b.letter));
}

function BlankInput({
  number,
  value,
  onChange,
  maxWords,
  active,
}: {
  number: number;
  value: string;
  onChange: (v: string) => void;
  maxWords: number | null;
  active: boolean;
}) {
  const over = maxWords !== null && wordCount(value) > maxWords;
  return (
    <span className="inline-flex flex-col align-middle">
      <Input
        id={`q-${number}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`inline-block h-7 w-40 px-2 py-0 text-sm ${
          active ? "ring-2 ring-ring" : ""
        } ${over ? "border-destructive" : ""}`}
      />
      {over && <span className="text-[11px] text-destructive">over word limit</span>}
    </span>
  );
}
