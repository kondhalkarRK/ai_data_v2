"use client";

import { ChevronDown } from "lucide-react";
import * as React from "react";

import { ExecutionTimeline } from "@/components/chat/execution-timeline";
import type { ResponseMeta } from "@/components/chat/types";
import { cn } from "@/lib/utils";

function formatAsOf(value: string | null | undefined): string {
  if (!value) return "Data freshness unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return `Data as of ${value}`;
  return `Data as of ${date.toLocaleString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    month: "short",
    day: "numeric",
  })}`;
}

export function ResponseHeader({
  meta,
  latencyMs,
  className,
}: {
  meta: ResponseMeta;
  latencyMs?: number;
  className?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const totalMs = latencyMs ?? meta.executionTimeMs ?? 0;
  const answered = `${(totalMs / 1000).toFixed(1)} sec`;

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-background px-2.5 py-1 font-medium text-foreground transition-colors hover:bg-muted/60"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          Answered in {answered}
          <ChevronDown className={cn("size-3 transition-transform", open && "rotate-180")} />
        </button>
        <span className="rounded-full border border-border/60 px-2.5 py-1">{meta.sourceDatabase}</span>
        <span className="rounded-full border border-border/60 px-2.5 py-1">
          {meta.rowCount.toLocaleString()} rows analyzed
        </span>
        <span className="rounded-full border border-border/60 px-2.5 py-1">
          {formatAsOf(meta.dataAsOf)}
        </span>
        {meta.validationStatus === "auto_repaired" ? (
          <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-amber-800 dark:text-amber-200">
            Query was auto-corrected after an initial validation error
          </span>
        ) : null}
      </div>
      {open ? (
        <ExecutionTimeline timings={meta.timings} totalMs={totalMs || sumTimings(meta.timings)} />
      ) : null}
    </div>
  );
}

function sumTimings(timings: ResponseMeta["timings"]): number {
  return (
    (timings.llmGenerationMs ?? 0) +
    (timings.semanticLookupMs ?? 0) +
    (timings.sqlValidationMs ?? 0) +
    (timings.sqlAutoRepairMs ?? 0) +
    (timings.executionMs ?? 0) +
    (timings.renderMs ?? 0)
  );
}
