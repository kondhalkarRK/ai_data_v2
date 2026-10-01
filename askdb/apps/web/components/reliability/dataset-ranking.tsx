"use client";

import { ChartFrame } from "@/components/executive/cockpit/chart-frame";
import { formatCompact } from "@/components/executive/cockpit/format";
import type { DataReliability, DatasetTrust, Drilldown, TrustFilters } from "@/components/reliability/types";
import { BAND_COLOUR, cardClass, formatScore, formatWhen, ScoreRing } from "@/components/reliability/ui";
import { cn } from "@/lib/utils";

export function DatasetRanking({
  data,
  filters,
  onFilter,
  onDrill,
  className,
}: {
  data: DataReliability;
  filters: TrustFilters;
  onFilter: (patch: TrustFilters) => void;
  onDrill: (next: Drilldown) => void;
  className?: string;
}) {
  const ranked = [...data.datasets].sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999));
  return (
    <ChartFrame
      title="Dataset trust ranking"
      subtitle="Most to least trusted · click to filter the page, open for details"
      exportName="dataset-trust-ranking"
      png={false}
      className={className}
      csv={() =>
        ranked.map((d) => ({
          rank: d.rank ?? "",
          dataset: d.label,
          domain: d.domain,
          score: d.score,
          band: d.band,
          rules: d.rules,
          passing: d.passing,
          failing: d.failing,
          rows: d.rows ?? "",
          last_refresh: d.lastRefresh ?? "",
          top_issue: d.topIssue ?? "",
        }))
      }
    >
      {(expanded) => (
        <div className={cn("grid gap-2.5 sm:grid-cols-2", expanded ? "xl:grid-cols-4" : "xl:grid-cols-3")}>
          {ranked.map((d) => (
            <DatasetCard
              key={d.name}
              dataset={d}
              active={filters.dataset === d.name}
              faded={filters.dataset != null && filters.dataset !== d.name}
              onSelect={() => onFilter({ dataset: filters.dataset === d.name ? undefined : d.name })}
              onOpen={() => onDrill({ kind: "dataset", name: d.name })}
            />
          ))}
        </div>
      )}
    </ChartFrame>
  );
}

function DatasetCard({
  dataset: d,
  active,
  faded,
  onSelect,
  onOpen,
}: {
  dataset: DatasetTrust;
  active: boolean;
  faded: boolean;
  onSelect: () => void;
  onOpen: () => void;
}) {
  return (
    <div
      className={cn(
        cardClass,
        "flex flex-col p-3 shadow-none transition hover:border-[#8fb3f5]",
        active && "border-[#8fb3f5] ring-2 ring-[#2f6fed]/15",
        faded && "opacity-60 hover:opacity-100",
      )}
    >
      <button type="button" onClick={onSelect} className="flex items-center gap-3 text-left" title="Filter the page to this dataset">
        <span className="w-5 text-center text-xs font-semibold tabular-nums text-slate-400">{d.rank ?? "–"}</span>
        <div className="relative">
          <ScoreRing score={d.score} band={d.band} size={40} stroke={4} />
          <span
            className="absolute inset-0 flex items-center justify-center text-[10px] font-semibold tabular-nums"
            style={{ color: BAND_COLOUR[d.band] }}
          >
            {d.score == null ? "—" : Math.round(d.score)}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-slate-800 dark:text-foreground">{d.label}</p>
          <p className="truncate text-[10px] capitalize text-slate-400">
            {d.domain} · {d.rows == null ? "—" : `${formatCompact(d.rows)} rows`}
          </p>
        </div>
        <span className="text-sm font-semibold tabular-nums text-slate-700 dark:text-foreground">{formatScore(d.score)}</span>
      </button>
      <p className={cn("mt-2 truncate text-[11px]", d.topIssue ? "text-[#94660f]" : "text-slate-400")} title={d.topIssue ?? undefined}>
        {d.topIssue ?? `${d.passing}/${d.rules} checks passing`}
      </p>
      <div className="mt-1 flex items-center justify-between text-[10px] text-slate-400">
        <span>Refreshed {formatWhen(d.lastRefresh)}</span>
        <button type="button" onClick={onOpen} className="font-medium text-[#2f6fed] hover:underline">
          Details
        </button>
      </div>
    </div>
  );
}
