interface QuestionNavigatorProps {
  totalQuestions: number;
  answered: Set<number>;
  flagged: Set<number>;
  activeRange: [number, number] | null;
  onJump: (number: number) => void;
}

export function QuestionNavigator({
  totalQuestions,
  answered,
  flagged,
  activeRange,
  onJump,
}: QuestionNavigatorProps) {
  return (
    <div className="sticky bottom-0 z-30 border-t bg-background/95 backdrop-blur-sm px-2 py-2">
      <div className="flex flex-wrap gap-1 justify-center">
        {Array.from({ length: totalQuestions }, (_, i) => i + 1).map((n) => {
          const isActive = activeRange && n >= activeRange[0] && n <= activeRange[1];
          const isAnswered = answered.has(n);
          const isFlagged = flagged.has(n);
          return (
            <button
              key={n}
              type="button"
              onClick={() => onJump(n)}
              className={[
                "relative flex size-7 items-center justify-center rounded text-xs font-medium border transition-colors",
                isActive
                  ? "border-primary bg-primary text-primary-foreground"
                  : isAnswered
                    ? "border-transparent bg-emerald-500/20 text-emerald-700 dark:text-emerald-400"
                    : "border-transparent bg-muted text-muted-foreground",
              ].join(" ")}
            >
              {n}
              {isFlagged && (
                <span className="absolute -top-1 -end-1 size-2 rounded-full bg-amber-500" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
