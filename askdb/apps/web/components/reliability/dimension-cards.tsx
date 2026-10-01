"use client";

import { ChevronRight } from "lucide-react";

import type { DimensionCard, DimensionKey } from "@/components/reliability/types";
import {
  BAND_COLOUR,
  cardClass,
  DIMENSION_COLOUR,
  formatDelta,
  formatScore,
  formatWhen,
  ScoreRing,
  Sparkline,
} from "@/components/reliability/ui";
import { cn } from "@/lib/utils";

export function DimensionCards({
  dimensions,
  selected,
  onOpen,
}: {
  dimensions: DimensionCard[];
  selected?: DimensionKey;
  onOpen: (key: DimensionKey) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 lg:gap-5 2xl:grid-cols-6">
      {dimensions.map((d) => {
        const active = selected === d.key;
        const faded = selected != null && !active;
        return (
          <button
            key={d.key}
            type="button"
            onClick={() => onOpen(d.key)}
            title={d.question}
            className={cn(
              cardClass,
              "group flex flex-col p-3.5 text-left transition hover:border-[#8fb3f5] hover:shadow-md",
              active && "border-[#8fb3f5] ring-2 ring-[#2f6fed]/15",
              faded && "opacity-60 hover:opacity-100",
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-foreground">
                <span className="size-2 rounded-sm" style={{ backgroundColor: DIMENSION_COLOUR[d.key] }} />
                {d.label}
              </span>
              <span className="text-[10px] tabular-nums text-slate-400">
                weight {Math.round(d.effectiveWeight ?? d.weight)}%
              </span>
            </div>
            <div className="mt-2.5 flex items-center gap-3">
              <div className="relative">
                <ScoreRing score={d.score} band={d.band} size={52} stroke={5} />
                <span
                  className="absolute inset-0 flex items-center justify-center text-[11px] font-semibold tabular-nums"
                  style={{ color: BAND_COLOUR[d.band] }}
                >
                  {d.score == null ? "—" : Math.round(d.score)}
                </span>
              </div>
              <div className="min-w-0">
                <p className="text-xl font-semibold tracking-tight text-slate-900 tabular-nums dark:text-foreground">
                  {formatScore(d.score)}
                </p>
                <p className="text-2xs text-slate-500">
                  <span className="text-[#0f7a6c]">{d.passing} passing</span>
                  {d.failing ? <span className="text-[#a8463d]"> · {d.failing} failing</span> : null}
                  {d.errored ? <span className="text-[#94660f]"> · {d.errored} not run</span> : null}
                </p>
              </div>
            </div>
            <div className="mt-2.5 flex items-end justify-between gap-2">
              <span
                className={cn(
                  "text-2xs font-medium tabular-nums",
                  d.delta7d != null && d.delta7d < -0.05 ? "text-[#94660f]" : "text-slate-500",
                )}
              >
                {formatDelta(d.delta7d)} <span className="font-normal text-slate-400">7d</span>
              </span>
              <Sparkline values={d.sparkline} colour={DIMENSION_COLOUR[d.key]} width={76} height={22} />
            </div>
            <div className="mt-2 border-t border-slate-100 pt-2 text-[10px] text-slate-400 dark:border-border">
              {d.topIssue ? (
                <p className="truncate text-slate-600 dark:text-muted-foreground" title={d.topIssue}>
                  {d.topIssue}
                </p>
              ) : (
                <p className="truncate">{d.rules ? "All checks within target" : "No checks configured"}</p>
              )}
              <p className="mt-0.5 flex items-center justify-between">
                <span>Last failure {d.lastFailureAt ? formatWhen(d.lastFailureAt) : "none recorded"}</span>
                <ChevronRight className="size-3 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-[#2f6fed]" />
              </p>
            </div>
          </button>
        );
      })}
    </div>
  );
}
