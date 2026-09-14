"use client";

import * as React from "react";
import { Check, Loader2 } from "lucide-react";

import type { ProgressState, QueryTimings } from "@/components/chat/types";
import { cn } from "@/lib/utils";

const COMPLETE_STAGES: Array<{ key: keyof QueryTimings; label: string }> = [
  { key: "semanticLookupMs", label: "Matching your semantic layer" },
  { key: "llmGenerationMs", label: "Generating SQL" },
  { key: "sqlValidationMs", label: "Validating query" },
  { key: "sqlAutoRepairMs", label: "SQL auto-repair" },
  { key: "executionMs", label: "Crunching the data" },
  { key: "renderMs", label: "Building your answer" },
];

/**
 * One component for live progress (while streaming) and post-answer timing bars.
 * Driven by the same per-stage timing / progress data from the NLQ pipeline.
 */
export function ExecutionTimeline({
  timings,
  totalMs,
  progress,
  className,
}: {
  timings?: QueryTimings | null;
  totalMs?: number;
  progress?: ProgressState | null;
  className?: string;
}) {
  if (progress && !timings) {
    return (
      <div
        className={cn(
          "rounded-xl border border-border/60 bg-muted/20 p-3 dark:bg-background/80",
          className,
        )}
        role="status"
        aria-live="polite"
        aria-label={progress.currentLabel || "Working on your answer"}
      >
        {progress.slowWarning ? (
          <p className="mb-2 text-xs text-amber-800 dark:text-amber-200">
            {progress.message ||
              `This query is taking longer than expected. Current stage: ${progress.currentLabel}`}
          </p>
        ) : (
          <p className="mb-2 text-xs font-medium text-foreground">
            {progress.currentLabel || "Working on your answer"}
          </p>
        )}
        <ul className="space-y-2">
          {progress.steps.map((step) => {
            const done = progress.completed.includes(step.id);
            const active = progress.current === step.id && !done;
            return (
              <li
                key={step.id}
                className={cn(
                  "flex items-center gap-2.5 text-[12px]",
                  done && "text-foreground",
                  active && "font-medium text-foreground",
                  !done && !active && "text-muted-foreground",
                )}
              >
                <span className="flex size-4 shrink-0 items-center justify-center" aria-hidden="true">
                  {done ? (
                    <Check className="size-3.5 text-success" />
                  ) : active ? (
                    <Loader2 className="size-3.5 animate-spin text-primary" />
                  ) : (
                    <span className="size-1.5 rounded-full bg-border" />
                  )}
                </span>
                <span>
                  {step.label}
                  {done ? " ✓" : active ? "…" : ""}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  if (!timings) return null;

  const rows = COMPLETE_STAGES.map((stage) => ({
    ...stage,
    ms: Number(timings[stage.key] ?? 0),
  })).filter((row) => row.key !== "sqlAutoRepairMs" || row.ms > 0);

  const total = totalMs ?? 0;
  const max = Math.max(1, ...rows.map((row) => row.ms), total);

  return (
    <div className={cn("rounded-xl border border-border/60 bg-background/80 p-3", className)}>
      <p className="mb-2 text-xs font-medium text-foreground">
        Total: {(total / 1000).toFixed(1)} sec
      </p>
      <ul className="space-y-2">
        {rows.map((row) => {
          const width = Math.max(4, Math.round((row.ms / max) * 100));
          return (
            <li key={row.key} className="grid grid-cols-[minmax(0,1fr)_72px] items-center gap-2">
              <div>
                <p className="mb-1 text-[11px] text-muted-foreground">{row.label}</p>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-foreground/70"
                    style={{ width: `${width}%` }}
                  />
                </div>
              </div>
              <p className="text-right font-mono text-[11px] text-muted-foreground">
                {(row.ms / 1000).toFixed(1)} sec
              </p>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
