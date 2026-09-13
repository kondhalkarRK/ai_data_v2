"use client";

import { ChevronDown } from "lucide-react";
import * as React from "react";

import type { BusinessHealth } from "@/components/executive/types";
import { StatusPill } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

function healthTone(score: number): "ok" | "warn" | "fail" {
  if (score >= 75) return "ok";
  if (score >= 50) return "warn";
  return "fail";
}

export function BusinessHealthPanel({ health }: { health: BusinessHealth }) {
  const [open, setOpen] = React.useState(false);

  if (!health.available || health.score == null) {
    return (
      <div className="card-supporting px-4 py-3 text-sm text-muted-foreground">
        {health.unavailableReason || "Business Health unavailable for the current metrics."}
      </div>
    );
  }

  const score = health.score;
  const tone = healthTone(score);
  const circumference = 2 * Math.PI * 54;
  const offset = circumference * (1 - Math.min(100, Math.max(0, score)) / 100);

  return (
    <div className="card-primary overflow-hidden">
      <button
        type="button"
        className="flex w-full items-center gap-5 px-5 py-5 text-left"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <div className="relative size-[7.5rem] shrink-0" aria-hidden="true">
          <svg viewBox="0 0 120 120" className="size-full -rotate-90">
            <circle
              cx="60"
              cy="60"
              r="54"
              fill="none"
              stroke="hsl(var(--muted))"
              strokeWidth="8"
            />
            <circle
              cx="60"
              cy="60"
              r="54"
              fill="none"
              stroke={
                tone === "ok"
                  ? "hsl(var(--success))"
                  : tone === "warn"
                    ? "hsl(var(--warning))"
                    : "hsl(var(--danger))"
              }
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              className="transition-[stroke-dashoffset] duration-500"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-3xl font-semibold tabular-nums tracking-tight">
              {score.toFixed(0)}
            </span>
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm text-muted-foreground">Business Health</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <StatusPill tone={tone} label={health.label} />
          </div>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Weighted score from domain KPIs. Expand to see each component’s contribution.
          </p>
        </div>
        <ChevronDown
          className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
        />
      </button>
      {open ? (
        <div className="space-y-3 border-t border-border/60 bg-surface/40 px-5 py-4">
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
