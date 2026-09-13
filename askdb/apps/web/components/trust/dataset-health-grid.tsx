"use client";

import * as React from "react";

import type { DatasetHealth } from "@/components/trust/types";
import { EmptyState, StatusPill } from "@/components/ui/status-pill";
import { CHART_SERIES } from "@/lib/design";
import { cn } from "@/lib/utils";

export function DatasetHealthGrid({ datasets }: { datasets: DatasetHealth[] }) {
  const [query, setQuery] = React.useState("");
  const [sort, setSort] = React.useState<"health" | "name">("health");

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    let rows = datasets.filter(
      (d) =>
        !q ||
        d.displayName.toLowerCase().includes(q) ||
        d.name.toLowerCase().includes(q),
    );
    rows = [...rows].sort((a, b) =>
      sort === "health"
        ? a.healthScore - b.healthScore
        : a.displayName.localeCompare(b.displayName),
    );
    return rows;
  }, [datasets, query, sort]);

  if (!datasets.length) {
    return (
      <EmptyState
        title="No datasets to score"
        detail="Migrate and seed the analytics database, then refresh Data Trust Center."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <input
          className="h-9 flex-1 rounded-[var(--radius-control)] border border-border bg-background px-3 text-sm"
          placeholder="Search datasets…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search datasets"
        />
        <select
          className="h-9 rounded-[var(--radius-control)] border border-border bg-background px-2 text-sm"
          value={sort}
          onChange={(e) => setSort(e.target.value as "health" | "name")}
        >
          <option value="health">Sort: least healthy</option>
          <option value="name">Sort: name</option>
        </select>
      </div>
      {filtered.length === 0 ? (
        <EmptyState
          title="No matching datasets"
          detail="Try a different search term or clear the filter."
        />
      ) : (
        <div
          className={cn(
            "grid gap-3",
            filtered.length === 1 && "md:grid-cols-1 max-w-md",
            filtered.length === 2 && "md:grid-cols-2",
            filtered.length >= 3 && "md:grid-cols-2 xl:grid-cols-3",
          )}
        >
          {filtered.map((dataset, index) => {
            const tone =
              dataset.healthScore >= 80 ? "ok" : dataset.healthScore >= 60 ? "warn" : "fail";
            return (
              <article
                key={dataset.name}
                className={cn(
                  "p-4 transition-colors hover:border-border",
                  index === 0 ? "card-primary" : "card-secondary",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-semibold" title={dataset.displayName}>
                      {dataset.displayName}
                    </h3>
                    <p className="text-[11px] text-muted-foreground">{dataset.tableType}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-semibold tabular-nums">
                      {dataset.healthScore.toFixed(0)}%
                    </p>
                    <StatusPill
                      tone={tone}
                      label={tone === "ok" ? "Healthy" : tone === "warn" ? "Watch" : "At risk"}
                      className="mt-1"
                    />
                  </div>
                </div>
                <Sparkline values={dataset.sparkline} />
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {Object.entries(dataset.flags).map(([key, flag]) => (
                    <StatusPill
                      key={key}
                      tone={flag === "ok" ? "ok" : flag === "warn" ? "warn" : "fail"}
                      label={`${key} ${flag === "ok" ? "ok" : flag === "warn" ? "warn" : "fail"}`}
                    />
                  ))}
                </div>
                {dataset.slaHours != null ? (
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    SLA: every {dataset.slaHours}h
                    {dataset.lastRefresh
                      ? ` · last ${new Date(dataset.lastRefresh).toLocaleString()}`
                      : ""}
                  </p>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  if (!values.length) {
    return <p className="mt-2 text-[11px] text-muted-foreground">No sparkline history yet</p>;
  }
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = Math.max(max - min, 1);
  const w = 160;
  const h = 28;
  const points = values
    .map((v, i) => {
      const x = (i / Math.max(values.length - 1, 1)) * w;
      const y = h - ((v - min) / span) * (h - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-3 h-7 w-full" aria-hidden="true">
      <polyline
        fill="none"
        stroke={CHART_SERIES.secondary}
        strokeWidth="1.5"
        points={points}
      />
    </svg>
  );
}
