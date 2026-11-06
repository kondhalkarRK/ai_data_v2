"use client";

import * as React from "react";
import type { BiPlan, BiReportFilter } from "@nql/shared-types";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api-client";

function weekInput(iso?: string | null) {
  if (!iso) return "";
  const day = new Date(`${iso}T12:00:00Z`);
  const thursday = new Date(day);
  thursday.setUTCDate(day.getUTCDate() + 3 - ((day.getUTCDay() + 6) % 7));
  const first = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 4));
  const week = 1 + Math.round(((thursday.getTime() - first.getTime()) / 86400000 - 3 + ((first.getUTCDay() + 6) % 7)) / 7);
  return `${thursday.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

function monday(value: string) {
  const [year, week] = value.split("-W").map(Number);
  if (!year || !week) return null;
  const jan4 = new Date(Date.UTC(year, 0, 4));
  jan4.setUTCDate(jan4.getUTCDate() - ((jan4.getUTCDay() + 6) % 7) + (week - 1) * 7);
  return jan4.toISOString().slice(0, 10);
}

export function ReportFilters({ plan, busy, onApply, hideRegionFilter = false }: { plan: BiPlan; busy: boolean; onApply: (filter: BiReportFilter) => void; hideRegionFilter?: boolean }) {
  const first = plan.panels[0]?.spec;
  const showRegion = !hideRegionFilter && plan.panels.some(panel => panel.title === "Region and model mix");
  type DraftFilter = Omit<BiReportFilter, "period"> & { period: BiReportFilter["period"] | "current" };
  const initial: DraftFilter = plan.reportFilter ?? { period: "current", year: Number(first?.dateFrom?.slice(0, 4)) || new Date().getFullYear(), month: Number(first?.dateFrom?.slice(5, 7)) || 1, make: first?.filters.find(item => item.domain === "make")?.values[0] ?? null, region: first?.filters.find(item => item.domain === "region")?.values[0] ?? null };
  const [draft, setDraft] = React.useState<DraftFilter>(initial);
  const [week, setWeek] = React.useState(weekInput(initial.weekStart ?? first?.dateFrom));
  const [makes, setMakes] = React.useState<string[]>([]);
  const [regions, setRegions] = React.useState<string[]>([]);
  const [makeError, setMakeError] = React.useState("");
  React.useEffect(() => {
    const controller = new AbortController();
    void apiClient.get<{ values: Array<{ value: string }> }>("/api/v1/analytics/bi/make-options", { industry: "automotive", signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setMakes(data.values.map(item => item.value)); })
      .catch(() => { if (!controller.signal.aborted) setMakeError("Make options are unavailable; date filters still work."); });
    return () => controller.abort();
  }, []);
  React.useEffect(() => {
    if (!showRegion) return;
    const controller = new AbortController();
    void apiClient.get<{ values: Array<{ value: string }> }>("/api/v1/analytics/bi/region-options", { industry: "automotive", signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setRegions(data.values.map(item => item.value)); })
      .catch(() => { if (!controller.signal.aborted) setRegions([]); });
    return () => controller.abort();
  }, [showRegion]);
  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: Math.min(26, currentYear - 1999) }, (_, index) => currentYear - index);
  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (draft.period === "current") return;
    if (draft.period === "week") {
      const weekStart = monday(week);
      if (!weekStart) return;
      onApply({ period: "week", year: Number(weekStart.slice(0, 4)), weekStart, make: draft.make ?? null, region: draft.region ?? null });
    } else if (draft.period === "month") {
      onApply({ period: "month", year: draft.year, month: draft.month ?? 1, make: draft.make ?? null, region: draft.region ?? null });
    } else onApply({ period: "year", year: draft.year, make: draft.make ?? null, region: draft.region ?? null });
  }
  return <form onSubmit={submit} className="flex flex-wrap items-end gap-3 rounded-2xl border border-border bg-surface-raised p-4" aria-label="Report filters">
    <label className="text-xs text-muted-foreground">Period <select className="mt-1 block rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground" value={draft.period} onChange={event => setDraft(old => ({ ...old, period: event.target.value as DraftFilter["period"] }))}>{!plan.reportFilter && <option value="current">Current range</option>}<option value="year">Year</option><option value="month">Month</option><option value="week">Week · Mon–Sun</option></select></label>
    {draft.period !== "week" && draft.period !== "current" && <label className="text-xs text-muted-foreground">Year <select className="mt-1 block rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground" value={draft.year} onChange={event => setDraft(old => ({ ...old, year: Number(event.target.value) }))}>{years.map(year => <option key={year} value={year}>{year}</option>)}</select></label>}
    {draft.period === "month" && <label className="text-xs text-muted-foreground">Month <select className="mt-1 block rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground" value={draft.month ?? 1} onChange={event => setDraft(old => ({ ...old, month: Number(event.target.value) }))}>{Array.from({ length: 12 }, (_, index) => <option key={index + 1} value={index + 1}>{new Intl.DateTimeFormat("en", { month: "long" }).format(new Date(2020, index, 1))}</option>)}</select></label>}
    {draft.period === "week" && <label className="text-xs text-muted-foreground">Week starting Monday <input className="mt-1 block rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground" type="week" value={week} onChange={event => setWeek(event.target.value)} required /></label>}
    <label className="text-xs text-muted-foreground">Make <select className="mt-1 block max-w-44 rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground" value={draft.make ?? ""} onChange={event => setDraft(old => ({ ...old, make: event.target.value || null }))}><option value="">All makes</option>{makes.map(make => <option key={make} value={make}>{make}</option>)}</select></label>
    {showRegion && <label className="text-xs text-muted-foreground">Region <select className="mt-1 block max-w-44 rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground" value={draft.region ?? ""} onChange={event => setDraft(old => ({ ...old, region: event.target.value || null }))}><option value="">All permitted regions</option>{regions.map(region => <option key={region} value={region}>{region}</option>)}</select></label>}
    <Button type="submit" disabled={busy || draft.period === "current" || (draft.period === "week" && !week)}>Apply filters</Button>
    {draft.period === "current" && <span className="text-xs text-muted-foreground">Current dates: {first?.dateFrom} to {first?.dateTo}. Choose a calendar period to change them.</span>}
    {draft.make && <span className="text-xs text-muted-foreground">Make comparison is scoped to {draft.make}.</span>}
    {makeError && <span className="text-xs text-muted-foreground">{makeError}</span>}
  </form>;
}
