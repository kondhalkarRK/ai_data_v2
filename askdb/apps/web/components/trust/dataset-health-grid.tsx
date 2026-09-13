"use client";

import * as React from "react";

import type { DatasetHealth } from "@/components/trust/types";
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
      sort === "health" ? a.healthScore - b.healthScore : a.displayName.localeCompare(b.displayName),
    );
    return rows;
  }, [datasets, query, sort]);

  if (!datasets.length) {
    return (
      <p className="rounded-2xl border border-dashed border-border/70 px-4 py-6 text-center text-sm text-muted-foreground">
        No datasets available to score.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <input
          className="h-9 flex-1 rounded-lg border border-border bg-background px-3 text-sm"
          placeholder="Search datasets…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search datasets"
        />
        <select
          className="h-9 rounded-lg border border-border bg-background px-2 text-sm"
          value={sort}
          onChange={(e) => setSort(e.target.value as "health" | "name")}
        >
          <option value="health">Sort: least healthy</option>
          <option value="name">Sort: name</option>
        </select>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {filtered.map((dataset) => (
          <article
            key={dataset.name}
            className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold">{dataset.displayName}</h3>
                <p className="text-[11px] text-muted-foreground">{dataset.tableType}</p>
              </div>
              <p className="text-lg font-semibold tabular-nums">{dataset.healthScore.toFixed(0)}%</p>
            </div>
            <Sparkline values={dataset.sparkline} />
            <div className="mt-3 flex flex-wrap gap-1.5">
              {Object.entries(dataset.flags).map(([key, flag]) => (
                <span
                  key={key}
                  className={cn(
                    "rounded-full border px-2 py-0.5 text-[10px] capitalize",
                    flag === "ok" && "border-emerald-500/30 text-emerald-700 dark:text-emerald-300",
                    flag === "warn" && "border-amber-500/30 text-amber-700 dark:text-amber-300",
                    flag === "fail" && "border-rose-500/30 text-rose-700 dark:text-rose-300",
                  )}
                >
                  {key} {flag === "ok" ? "✓" : flag === "warn" ? "⚠" : "✕"}
                </span>
              ))}
            </div>
            {dataset.slaHours != null ? (
              <p className="mt-2 text-[11px] text-muted-foreground">
                SLA: every {dataset.slaHours}h
                {dataset.lastRefresh ? ` · last ${new Date(dataset.lastRefresh).toLocaleString()}` : ""}
              </p>
            ) : null}
          </article>
        ))}
      </div>
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
  const w = 120;
  const h = 28;
  const points = values
    .map((v, i) => {
      const x = (i / Math.max(values.length - 1, 1)) * w;
      const y = h - ((v - min) / span) * h;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-2 h-7 w-full text-foreground/70" aria-hidden="true">
      <polyline fill="none" stroke="currentColor" strokeWidth="1.5" points={points} />
    </svg>
  );
}
