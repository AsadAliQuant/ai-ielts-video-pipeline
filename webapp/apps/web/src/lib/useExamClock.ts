import { useCallback, useEffect, useRef, useState } from "react";
import type { Timeline, TimelineSegment } from "./types";

export interface ExamClockState {
  started: boolean;
  ended: boolean;
  currentTime: number;
  activeSegment: TimelineSegment | null;
  remaining: number | null; // seconds left in the active countdown segment, if any
  start: () => void;
}

const OVERLAY_KINDS = new Set(["prep", "mid_break", "checking"]);

/**
 * Owns a single <audio> element and derives the active timeline segment from
 * its playback position via a requestAnimationFrame loop. Strict mode: no
 * pause/seek/replay UI is ever rendered, and any seeking that does occur
 * (e.g. OS media keys) is snapped back to the last known position.
 */
export function useExamClock(
  audioRef: React.RefObject<HTMLAudioElement | null>,
  timeline: Timeline | null,
  onEndTest: () => void
): ExamClockState {
  const [started, setStarted] = useState(false);
  const [ended, setEnded] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [activeSegment, setActiveSegment] = useState<TimelineSegment | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);

  const lastPositionRef = useRef(0);
  const lastSegmentKindRef = useRef<string | null>(null);
  const rafRef = useRef<number | null>(null);

  const start = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || started) return;
    audio.play();
    setStarted(true);
  }, [audioRef, started]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onSeeking = () => {
      if (Math.abs(audio.currentTime - lastPositionRef.current) > 0.25) {
        audio.currentTime = lastPositionRef.current;
      }
    };
    audio.addEventListener("seeking", onSeeking);
    return () => audio.removeEventListener("seeking", onSeeking);
  }, [audioRef]);

  useEffect(() => {
    if (!started || !timeline) return;
    const audio = audioRef.current;
    if (!audio) return;

    const tick = () => {
      const t = audio.currentTime;
      lastPositionRef.current = t;
      setCurrentTime(t);

      const segment =
        timeline.segments.find((s) => t >= s.start && t < s.end) ??
        timeline.segments[timeline.segments.length - 1] ??
        null;

      if (segment && segment.kind !== lastSegmentKindRef.current) {
        lastSegmentKindRef.current = segment.kind + segment.start;
        setActiveSegment(segment);
      }

      if (segment && OVERLAY_KINDS.has(segment.kind)) {
        setRemaining(Math.max(0, Math.ceil(segment.end - t)));
      } else {
        setRemaining(null);
      }

      if (segment && segment.kind === "end_test" && t >= segment.end - 0.15 && !ended) {
        setEnded(true);
        onEndTest();
        return;
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [started, timeline, ended]);

  return { started, ended, currentTime, activeSegment, remaining, start };
}
