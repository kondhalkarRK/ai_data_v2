"use client";

import { ChevronDown } from "lucide-react";
import * as React from "react";

import type { BusinessHealth } from "@/components/executive/types";
import { cn } from "@/lib/utils";

export function BusinessHealthPanel({ health }: { health: BusinessHealth }) {
  const [open, setOpen] = React.useState(false);

  if (!health.available || health.score == null) {
    return (
      <div className="rounded-2xl border border-border/70 bg-muted/20 px-4 py-3 text-sm text-muted-foreground">
        {health.unavailableReason || "Business Health unavailable for the current metrics."}
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-border/70 bg-background shadow-sm">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Business Health
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight">
            {health.score.toFixed(0)}
            <span className="ml-2 text-sm font-medium text-muted-foreground">{health.label}</span>
          </p>
        </div>
        <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div className="space-y-3 border-t border-border/60 px-4 py-3">
          <p className="text-xs text-muted-foreground">{health.formulaNote}</p>
          <ul className="space-y-2">
            {health.components.map((component) => (
              <li key={component.kpiId} className="grid grid-cols-[1fr_auto] gap-2 text-xs">
                <div>
                  <p className="font-medium">{component.label}</p>
                  <p className="text-muted-foreground">
                    Weight {(component.weight * 100).toFixed(0)}% ·{" "}
                    {component.direction === "lower_better" ? "lower is better" : "higher is better"}
                  </p>
                </div>
                <div className="text-right">
                  <p className="font-medium tabular-nums">{component.formatted}</p>
                  <p className="text-muted-foreground tabular-nums">
                    contrib {component.contribution.toFixed(1)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
