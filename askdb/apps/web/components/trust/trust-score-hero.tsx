"use client";

import { ChevronDown } from "lucide-react";
import * as React from "react";

import type { TrustHero } from "@/components/trust/types";
import { cn } from "@/lib/utils";

export function TrustScoreHero({ hero }: { hero: TrustHero }) {
  const [open, setOpen] = React.useState(false);

  if (!hero.available || hero.score == null) {
    return (
      <div className="rounded-2xl border border-dashed border-border/70 bg-muted/20 px-4 py-6 text-sm text-muted-foreground">
        {hero.unavailableReason || "Trust Score unavailable — no datasets could be scored."}
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-border/70 bg-background shadow-sm">
      <button
        type="button"
        className="flex w-full flex-wrap items-end justify-between gap-4 px-5 py-4 text-left"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Trust Score
          </p>
          <p className="mt-1 text-4xl font-semibold tabular-nums tracking-tight">
            {hero.score.toFixed(0)}
            <span className="text-lg font-medium text-muted-foreground"> / 100</span>
          </p>
          <p className="mt-1 text-sm text-muted-foreground">{hero.label}</p>
        </div>
        <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
          <Stat label="Datasets" value={String(hero.datasets)} />
          <Stat label="DQ Checks" value={hero.dqChecks.toLocaleString()} />
          <Stat label="Active Incidents" value={String(hero.activeIncidents)} />
          <Stat label="Schema Drift" value={String(hero.schemaDrift)} />
          <ChevronDown className={cn("size-4 self-center transition-transform", open && "rotate-180")} />
        </div>
      </button>
      {open ? (
        <div className="space-y-3 border-t border-border/60 px-5 py-4">
          <p className="text-xs text-muted-foreground">{hero.formulaNote}</p>
          <ul className="space-y-2">
            {hero.components.map((c) => (
              <li key={c.id} className="grid grid-cols-[1fr_auto] gap-2 text-xs">
                <div>
                  <p className="font-medium">{c.label}</p>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-foreground/70"
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
      <p className="text-[10px] uppercase tracking-wide">{label}</p>
      <p className="text-sm font-semibold tabular-nums text-foreground">{value}</p>
    </div>
  );
}
