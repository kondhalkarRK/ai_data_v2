"use client";

import { ChevronDown, Compass, Lightbulb, Rocket, Sigma } from "lucide-react";
import * as React from "react";

import type { Capability, DataReliability, DimensionKey, Drilldown, InsightItem, TrustFilters } from "@/components/reliability/types";
import {
  BAND_COLOUR,
  Card,
  DIMENSION_COLOUR,
  PanelTitle,
  SEVERITIES,
  TONE_COLOUR,
} from "@/components/reliability/ui";
import { cn } from "@/lib/utils";

export function InsightsPanel({
  insights,
  onFilter,
  onDrill,
  className,
}: {
  insights: InsightItem[];
  onFilter: (patch: TrustFilters) => void;
  onDrill: (next: Drilldown) => void;
  className?: string;
}) {
  const open = (i: InsightItem) => {
    if (i.ruleIds.length === 1) onDrill({ kind: "rule", id: i.ruleIds[0]! });
    else if (i.dimension) onDrill({ kind: "dimension", key: i.dimension });
    else if (i.dataset) onFilter({ dataset: i.dataset });
  };
  return (
    <Card className={className}>
      <PanelTitle
        title="AI insights"
        subtitle="Patterns found across rules, history and freshness"
        right={<Lightbulb className="size-4 text-[#d69e2e]" />}
      />
      {insights.length ? (
        <ul className="space-y-2">
          {insights.map((i) => {
            const actionable = Boolean(i.ruleIds.length || i.dimension || i.dataset);
            return (
              <li key={i.id}>
                <button
                  type="button"
                  disabled={!actionable}
                  onClick={() => open(i)}
                  className="flex w-full gap-2.5 rounded-xl border border-slate-100 px-3 py-2.5 text-left transition enabled:hover:border-[#c9dafb] enabled:hover:bg-[#f8faff] dark:border-border"
                >
                  <span className="mt-1 size-2 shrink-0 rounded-full" style={{ backgroundColor: TONE_COLOUR[i.tone] }} />
                  <span className="min-w-0">
                    <span className="block text-xs font-semibold text-slate-800 dark:text-foreground">{i.title}</span>
                    <span className="mt-0.5 block text-[11px] leading-relaxed text-slate-600 dark:text-muted-foreground">{i.detail}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-2xs text-slate-500">No notable patterns in the latest run.</p>
      )}
    </Card>
  );
}

export function MethodologyPanel({ data, className }: { data: DataReliability; className?: string }) {
  const [open, setOpen] = React.useState(false);
  const m = data.methodology;
  return (
    <Card className={cn("p-0", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2">
          <span className="icon-well size-7 rounded-lg bg-[#e3ecfd] text-[#2f6fed]">
            <Sigma className="size-4" />
          </span>
          <span>
            <span className="block text-sm font-semibold text-slate-800 dark:text-foreground">DQ score methodology</span>
            <span className="block text-2xs text-slate-500">How the trust score is calculated, weighted and banded</span>
          </span>
        </span>
        <ChevronDown className={cn("size-4 text-slate-400 transition", open && "rotate-180")} />
      </button>
      {open ? (
        <div className="grid gap-5 border-t border-slate-100 px-4 py-4 lg:grid-cols-3 dark:border-border">
          <div className="lg:col-span-1">
            <h4 className="text-2xs font-semibold uppercase tracking-wide text-slate-500">Formula</h4>
            <p className="mt-1.5 rounded-xl bg-slate-50 px-3 py-2 font-mono text-[11px] leading-relaxed text-slate-700 dark:bg-muted dark:text-foreground">
              {m.formula}
            </p>
            <h4 className="mt-4 text-2xs font-semibold uppercase tracking-wide text-slate-500">Severity weight within a dimension</h4>
            <div className="mt-1.5 flex gap-1.5">
              {SEVERITIES.map((s) => (
                <span key={s} className="flex-1 rounded-lg bg-slate-50 px-2 py-1.5 text-center dark:bg-muted">
                  <span className="block text-[10px] capitalize text-slate-400">{s}</span>
                  <span className="text-sm font-semibold tabular-nums text-slate-700 dark:text-foreground">×{m.severityWeights[s]}</span>
                </span>
              ))}
            </div>
          </div>
          <div>
            <h4 className="text-2xs font-semibold uppercase tracking-wide text-slate-500">Dimension weights</h4>
            <ul className="mt-2 space-y-2">
              {m.dimensions.map((d) => (
                <li key={d.key} className="text-xs">
                  <div className="flex items-center justify-between">
                    <span className={cn("text-slate-700 dark:text-foreground", !d.measured && "text-slate-400")}>
                      {d.label}
                      {!d.measured ? <span className="ml-1 text-[10px]">(not measured)</span> : null}
                    </span>
                    <span className="tabular-nums text-slate-500">
                      {Math.round(d.weight)}%
                      {d.effectiveWeight != null && Math.abs(d.effectiveWeight - d.weight) > 0.05 ? (
                        <span className="text-slate-400"> → {d.effectiveWeight.toFixed(1)}%</span>
                      ) : null}
                    </span>
                  </div>
                  <span className="mt-1 block h-1.5 rounded-full bg-slate-100">
                    <span
                      className="block h-full rounded-full"
                      style={{ width: `${Math.min(100, d.weight * 2.5)}%`, backgroundColor: DIMENSION_COLOUR[d.key as DimensionKey] }}
                    />
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h4 className="text-2xs font-semibold uppercase tracking-wide text-slate-500">Trust bands</h4>
            <ul className="mt-2 space-y-1.5">
              {m.bands.map((b, i) => (
                <li key={b.key} className="flex items-center justify-between rounded-lg bg-slate-50 px-2.5 py-1.5 text-xs dark:bg-muted">
                  <span className="flex items-center gap-1.5 font-medium text-slate-700 dark:text-foreground">
                    <span className="size-2 rounded-full" style={{ backgroundColor: BAND_COLOUR[b.key] }} />
                    {b.label}
                  </span>
                  <span className="tabular-nums text-slate-500">
                    {i === 0 ? `${b.min}–100` : b.min === 0 ? `< ${m.bands[i - 1]!.min}` : `${b.min}–${m.bands[i - 1]!.min}`}
                  </span>
                </li>
              ))}
            </ul>
            {m.notes.length ? (
              <ul className="mt-3 list-disc space-y-1 pl-4 text-[11px] leading-relaxed text-slate-500">
                {m.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            ) : null}
          </div>
        </div>
      ) : null}
    </Card>
  );
}

const CAPABILITY_STYLE: Record<Capability["status"], { label: string; colour: string; bg: string; icon: React.ReactNode }> = {
  live: { label: "Live", colour: "#0f7a6c", bg: "#dcf3ee", icon: <Compass className="size-3.5" /> },
  next: { label: "Next", colour: "#2f5fc4", bg: "#e3ecfd", icon: <Rocket className="size-3.5" /> },
  planned: { label: "Planned", colour: "#64748b", bg: "#f1f5f9", icon: <Lightbulb className="size-3.5" /> },
};

export function CapabilitiesPanel({ capabilities, className }: { capabilities: Capability[]; className?: string }) {
  return (
    <Card className={className}>
      <PanelTitle title="Reliability platform roadmap" subtitle="What is running today and what the architecture is ready for next" />
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {capabilities.map((c) => {
          const s = CAPABILITY_STYLE[c.status];
          return (
            <div key={c.key} className="rounded-xl border border-slate-100 px-3 py-2.5 dark:border-border">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-semibold text-slate-800 dark:text-foreground">{c.label}</p>
                <span
                  className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
                  style={{ color: s.colour, backgroundColor: s.bg }}
                >
                  {s.icon}
                  {s.label}
                </span>
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-slate-500">{c.detail}</p>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
