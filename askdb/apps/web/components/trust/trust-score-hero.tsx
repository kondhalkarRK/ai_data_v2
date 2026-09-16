"use client";

import { ChevronDown } from "lucide-react";
import * as React from "react";

import type { TrustHero } from "@/components/trust/types";
import { StatusPill } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

function trustTone(score: number): "ok" | "warn" | "fail" {
  if (score >= 80) return "ok";
  if (score >= 60) return "warn";
  return "fail";
}

export function TrustScoreHero({ hero }: { hero: TrustHero }) {
  const [open, setOpen] = React.useState(false);

  if (!hero.available || hero.score == null) {
    return (
      <div className="card-supporting border border-dashed border-border/80 px-4 py-6 text-sm text-muted-foreground">
        {hero.unavailableReason || "Trust Score unavailable — no datasets could be scored."}
      </div>
    );
  }

  const score = hero.score;
  const tone = trustTone(score);
  const circumference = 2 * Math.PI * 54;
  const offset = circumference * (1 - Math.min(100, Math.max(0, score)) / 100);

  return (
    <div className="card-primary overflow-hidden">
      <button
        type="button"
        className="flex w-full flex-wrap items-center gap-5 px-5 py-5 text-left"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <div className="relative size-[7.5rem] shrink-0" aria-hidden="true">
          <svg viewBox="0 0 120 120" className="size-full -rotate-90">
            <circle cx="60" cy="60" r="54" fill="none" stroke="hsl(var(--muted))" strokeWidth="8" />
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
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-3xl font-semibold tabular-nums tracking-tight">
              {score.toFixed(0)}
            </span>
            <span className="text-[10px] text-muted-foreground">/ 100</span>
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm text-muted-foreground">Trust Score</p>
          <div className="mt-1">
            <StatusPill tone={tone} label={hero.label} />
          </div>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
            <Stat label="Datasets" value={String(hero.datasets)} />
            <Stat label="DQ Checks" value={hero.dqChecks.toLocaleString()} />
            <Stat label="Active incidents" value={String(hero.activeIncidents)} />
            <Stat label="Schema drift" value={String(hero.schemaDrift)} />
          </div>
        </div>
        <ChevronDown
          className={cn("size-4 self-center text-muted-foreground transition-transform", open && "rotate-180")}
        />
      </button>
      {open ? (
        <div className="space-y-3 border-t border-border/60 bg-surface/40 px-5 py-4">
          <p className="text-xs text-muted-foreground">{hero.formulaNote}</p>
          <ul className="space-y-2">
            {hero.components.map((c) => (
              <li key={c.id} className="grid grid-cols-[1fr_auto] gap-2 text-xs">
                <div>
                  <p className="font-medium">{c.label}</p>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-teal"
                      style={{ width: `${Math.min(100, c.score)}%` }}
                    />
                  </div>
                </div>
                <div className="text-right tabular-nums">
                  <p className="font-medium">{c.score.toFixed(0)}</p>
                  <p className="text-muted-foreground">w {(c.weight * 100).toFixed(0)}%</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="text-sm font-semibold tabular-nums text-foreground">{value}</p>
    </div>
  );
}
