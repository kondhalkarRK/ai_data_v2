"use client";

import type { ExecutiveIntelligence } from "@/components/executive/types";
import { cn } from "@/lib/utils";

export function PerformanceAnalytics({
  data,
  presenterMode,
  onFilter,
}: {
  data: ExecutiveIntelligence;
  presenterMode?: boolean;
  onFilter: (dimension: string, name: string) => void;
}) {
  const metrics = data.chartMetrics.length
    ? data.chartMetrics
    : Object.keys(data.series[0]?.values ?? {}).slice(0, 2);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {metrics.slice(0, 2).map((metric) => (
        <SeriesCard
          key={metric}
          title={metric.replaceAll("_", " ")}
          series={data.series}
          metric={metric}
          presenterMode={Boolean(presenterMode)}
        />
      ))}
      {Object.entries(data.breakdowns).map(([key, items]) => (
        <BreakdownCard
          key={key}
          title={key}
          items={items}
          onSelect={(name) => onFilter(key, name)}
          presenterMode={Boolean(presenterMode)}
        />
      ))}
    </div>
  );
}

function SeriesCard({
  title,
  series,
  metric,
  presenterMode,
}: {
  title: string;
  series: ExecutiveIntelligence["series"];
  metric: string;
  presenterMode: boolean;
}) {
  const max = Math.max(...series.map((point) => Number(point.values[metric] || 0)), 1);
  return (
    <div className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
      <h3 className={cn("mb-3 capitalize", presenterMode ? "text-base font-semibold" : "text-sm font-semibold")}>
        {title}
      </h3>
      <div className={cn("flex items-end gap-1", presenterMode ? "h-56" : "h-40")}>
        {series.slice(-18).map((point) => {
          const value = Number(point.values[metric] || 0);
          const height = `${Math.max((value / max) * 100, 2)}%`;
          return (
            <div
              key={point.period}
              className="flex-1 rounded-t bg-foreground/70"
              style={{ height }}
              title={`${point.period}: ${value.toLocaleString()}`}
            />
          );
        })}
      </div>
    </div>
  );
}

function BreakdownCard({
  title,
  items,
  onSelect,
  presenterMode,
}: {
  title: string;
  items: Array<{ name: string; value: number; formatted: string }>;
  onSelect: (name: string) => void;
  presenterMode: boolean;
}) {
  const max = Math.max(...items.map((item) => item.value), 1);
  return (
    <div className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
      <h3 className={cn("mb-3 capitalize", presenterMode ? "text-base font-semibold" : "text-sm font-semibold")}>
        {title}
        <span className="ml-2 font-normal text-muted-foreground">(click to filter)</span>
      </h3>
      <ul className="space-y-2">
        {items.slice(0, 8).map((item) => (
          <li key={item.name}>
            <button type="button" className="w-full text-left" onClick={() => onSelect(item.name)}>
              <div className="mb-1 flex justify-between gap-2 text-xs">
                <span className="truncate underline-offset-2 hover:underline">{item.name}</span>
                <span className="tabular-nums text-muted-foreground">{item.formatted}</span>
              </div>
              <div className="h-1.5 rounded-full bg-muted">
                <div
                  className="h-1.5 rounded-full bg-foreground/70"
                  style={{ width: `${(item.value / max) * 100}%` }}
                />
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
