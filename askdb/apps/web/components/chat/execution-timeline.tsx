"use client";

import * as React from "react";

import type { ProgressState, QueryTimings } from "@/components/chat/types";
import { cn } from "@/lib/utils";

const COMPLETE_STAGES: Array<{ key: keyof QueryTimings; label: string }> = [
  { key: "llmGenerationMs", label: "LLM Query Generation" },
  { key: "semanticLookupMs", label: "Semantic Layer Lookup" },
  { key: "sqlValidationMs", label: "SQL Validation" },
  { key: "sqlAutoRepairMs", label: "SQL Auto-Repair" },
  { key: "executionMs", label: "SQL Execution" },
  { key: "renderMs", label: "Chart/Table Rendering" },
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
      <div className={cn("rounded-xl border border-border/60 bg-background/80 p-3", className)}>
        {progress.slowWarning ? (
          <p className="mb-2 text-xs text-amber-800 dark:text-amber-200">
            {progress.message ||
              `This query is taking longer than expected. Current Stage: ${progress.currentLabel}`}
          </p>
        ) : (
          <p className="mb-2 text-xs font-medium text-foreground">Working…</p>
        )}
        <ul className="space-y-1.5">
          {progress.steps.map((step) => {
            const done = progress.completed.includes(step.id);
            const active = progress.current === step.id;
            return (
              <li
                key={step.id}
                className={cn(
                  "flex items-center gap-2 text-[11px]",
                  done && "text-foreground",
                  active && !done && "font-medium text-foreground",
                  !done && !active && "text-muted-foreground",
                )}
              >
                <span className="w-3 shrink-0 text-center" aria-hidden="true">
                  {done ? "✓" : active ? "…" : "○"}
                </span>
                <span>
                  {step.label}
                  {active && !done ? "…" : ""}
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
