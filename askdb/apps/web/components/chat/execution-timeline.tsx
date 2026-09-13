"use client";

import * as React from "react";

import type { QueryTimings } from "@/components/chat/types";
import { cn } from "@/lib/utils";

const STAGES: Array<{ key: keyof QueryTimings; label: string }> = [
  { key: "llmGenerationMs", label: "LLM Query Generation" },
  { key: "semanticLookupMs", label: "Semantic Layer Lookup" },
  { key: "sqlValidationMs", label: "SQL Validation" },
  { key: "sqlAutoRepairMs", label: "SQL Auto-Repair" },
  { key: "executionMs", label: "SQL Execution" },
  { key: "renderMs", label: "Chart/Table Rendering" },
];

export function ExecutionTimeline({
  timings,
  totalMs,
  className,
}: {
  timings: QueryTimings;
  totalMs: number;
  className?: string;
}) {
  const rows = STAGES.map((stage) => ({
    ...stage,
    ms: Number(timings[stage.key] ?? 0),
  })).filter((row) => row.key !== "sqlAutoRepairMs" || row.ms > 0);

  const max = Math.max(1, ...rows.map((row) => row.ms), totalMs);

  return (
    <div className={cn("rounded-xl border border-border/60 bg-background/80 p-3", className)}>
      <p className="mb-2 text-xs font-medium text-foreground">
        Total: {(totalMs / 1000).toFixed(1)} sec
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
