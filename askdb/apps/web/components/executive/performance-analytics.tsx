"use client";

import type { ExecutiveIntelligence } from "@/components/executive/types";
import { IndiaRegionMap } from "@/components/executive/india-region-map";
import { CHART_SERIES } from "@/lib/design";
import { cn } from "@/lib/utils";

export function PerformanceAnalytics({
  data,
  industry,
  presenterMode,
  onFilter,
}: {
  data: ExecutiveIntelligence;
  industry: import("@nql/shared-types").Industry;
  presenterMode?: boolean;
  onFilter: (dimension: string, name: string) => void;
  windowId?: string;
  lob?: string;
  region?: string;
  make?: string;
}) {
  const metrics = data.chartMetrics.length
    ? data.chartMetrics
    : Object.keys(data.series[0]?.values ?? {}).slice(0, 2);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        {metrics.slice(0, 2).map((metric, index) => (
          <SeriesCard
            key={metric}
            title={metric.replaceAll("_", " ")}
            series={data.series}
            metric={metric}
            presenterMode={Boolean(presenterMode)}
            accent={index === 0 ? CHART_SERIES.primary : CHART_SERIES.secondary}
          />
        ))}
      </div>

      <IndiaRegionMap
        industry={industry}
        presenterMode={Boolean(presenterMode)}
        displayMode="panel"
      />

      <div className="grid gap-4 lg:grid-cols-2">
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
    </div>
  );
}

function formatAxisValue(value: number, metric: string): string {
  const isMoney =
    /revenue|premium|sales|amount|aov|severity|incurred|paid/i.test(metric);
  const abs = Math.abs(value);
  const prefix = isMoney ? "₹" : "";
  if (abs >= 1_00_00_000) return `${prefix}${(value / 1_00_00_000).toFixed(1)}Cr`;
  if (abs >= 1_00_000) return `${prefix}${(value / 1_00_000).toFixed(1)}L`;
  if (abs >= 1_000) return `${prefix}${(value / 1_000).toFixed(1)}k`;
  return `${prefix}${Math.round(value).toLocaleString()}`;
}

function niceTicks(max: number, count = 4): number[] {
  if (max <= 0) return [0];
  const raw = max / count;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const candidates = [1, 2, 2.5, 5, 10].map((n) => n * pow);
  const step = candidates.find((n) => n >= raw) ?? candidates[candidates.length - 1];
  const ticks: number[] = [];
  for (let v = 0; v <= max + step * 0.01; v += step) ticks.push(v);
  if (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}

function SeriesCard({
  title,
  series,
  metric,
  presenterMode,
  accent,
}: {
  title: string;
  series: ExecutiveIntelligence["series"];
  metric: string;
  presenterMode: boolean;
  accent: string;
}) {
  const points = series.slice(-18);
  const values = points.map((point) => Number(point.values[metric] || 0));
  const dataMax = Math.max(...values, 0);
  const ticks = niceTicks(dataMax || 1);
  const axisMax = ticks[ticks.length - 1] || 1;
  const unitHint = /revenue|premium|sales|amount|aov|severity|incurred|paid/i.test(metric)
    ? "₹"
    : "count";

  if (!series.length) {
    return (
      <div className="card-secondary p-4">
        <h3 className="mb-3 text-sm font-semibold capitalize">{title}</h3>
        <p className="py-10 text-center text-sm text-muted-foreground">
          No series points for this metric in the selected window.
        </p>
      </div>
    );
  }

  return (
    <div className="card-secondary p-4">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h3
          className={cn(
            "capitalize",
            presenterMode ? "text-base font-semibold" : "text-sm font-semibold",
          )}
        >
          {title}
        </h3>
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
          Y-axis · {unitHint}
        </span>
      </div>
      <div className={cn("flex gap-2", presenterMode ? "h-56" : "h-44")}>
        <div className="relative flex w-12 shrink-0 flex-col justify-between pb-5 pr-1 text-right">
          {[...ticks].reverse().map((tick) => (
            <span key={tick} className="text-[10px] tabular-nums text-muted-foreground">
              {formatAxisValue(tick, metric)}
            </span>
          ))}
        </div>
        <div className="relative min-w-0 flex-1">
          <div className="absolute inset-0 bottom-5 flex flex-col justify-between pointer-events-none">
            {ticks.map((tick) => (
              <div
                key={tick}
                className="w-full border-t border-border/60"
                style={{ opacity: tick === 0 ? 0.9 : 0.45 }}
              />
            ))}
          </div>
          <div className="absolute inset-x-0 bottom-0 top-0 flex items-end gap-1 pb-5">
            {points.map((point) => {
              const value = Number(point.values[metric] || 0);
              const height = `${Math.max((value / axisMax) * 100, value > 0 ? 2 : 0)}%`;
              return (
                <div
                  key={point.period}
                  className="group relative flex-1 rounded-t transition-opacity hover:opacity-80"
                  style={{ height, backgroundColor: accent }}
                  title={`${point.period}: ${formatAxisValue(value, metric)}`}
                >
                  <span className="pointer-events-none absolute -top-5 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded bg-foreground px-1.5 py-0.5 text-[10px] text-background group-hover:block">
                    {formatAxisValue(value, metric)}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="absolute inset-x-0 bottom-0 flex gap-1 overflow-hidden">
            {points.map((point) => (
              <span
                key={point.period}
                className="flex-1 truncate text-center text-[9px] text-muted-foreground"
                title={point.period}
              >
                {point.period.replace(/^\d{4}-/, "")}
              </span>
            ))}
          </div>
        </div>
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
    <div className="card-secondary p-4">
      <h3
        className={cn(
          "mb-3 capitalize",
          presenterMode ? "text-base font-semibold" : "text-sm font-semibold",
        )}
      >
        {title}
        <span className="ml-2 font-normal text-muted-foreground">Click a row to filter</span>
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
                  className="h-1.5 rounded-full bg-primary/80"
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
