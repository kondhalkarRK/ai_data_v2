"use client";

import * as React from "react";

import type { InsightDepth } from "@/components/chat/types";
import { cn } from "@/lib/utils";

export function InsightSummary({
  executive,
  analyst,
  depth,
  onDepthChange,
  className,
}: {
  executive: string;
  analyst: string;
  depth: InsightDepth;
  onDepthChange: (depth: InsightDepth) => void;
  className?: string;
}) {
  const body = depth === "executive" ? executive : analyst;

  return (
    <div
      className={cn(
        "rounded-2xl border border-border/70 bg-muted/25 px-4 py-3 shadow-sm",
        className,
      )}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          AI Insight
        </p>
        <div
          className="inline-flex rounded-full border border-border/70 bg-background p-0.5 text-[11px]"
          role="group"
          aria-label="Insight depth"
        >
          {(["executive", "analyst"] as const).map((option) => (
            <button
              key={option}
              type="button"
              className={cn(
                "rounded-full px-2.5 py-1 capitalize transition-colors",
                depth === option
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground",
              )}
              aria-pressed={depth === option}
              onClick={() => onDepthChange(option)}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
      <p className="text-sm leading-relaxed text-foreground/90">{body}</p>
    </div>
  );
}
