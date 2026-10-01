"use client";

import * as React from "react";

import { ChartFrame, Segmented } from "@/components/executive/cockpit/chart-frame";
import { formatCount, formatInr, formatPct } from "@/components/executive/cockpit/format";
import { COCKPIT } from "@/components/executive/cockpit/palette";
import type { CockpitData, RankedItem, SelectHandler } from "@/components/executive/cockpit/types";
import { cn } from "@/lib/utils";

type Metric = "revenue" | "units";

export function RankedModels({
  data,
  onSelect,
  className,
}: {
  data: CockpitData;
  onSelect: SelectHandler;
  className?: string;
}) {
  const [metric, setMetric] = React.useState<Metric>("revenue");
  const items = metric === "revenue" ? data.topModelsByRevenue : data.topModelsByUnits;
  return (
    <ChartFrame
      title="Top performing models"
      subtitle={`Top 10 by ${metric} · click a model to focus`}
      exportName={`top-models-${metric}`}
      className={className}
      controls={
        <Segmented
          value={metric}
          onChange={setMetric}
          options={[
            { value: "revenue", label: "Revenue" },
            { value: "units", label: "Units" },
          ]}
        />
      }
      csv={() =>
        items.map((item, i) => ({
          rank: i + 1,
          make: item.group,
          model: item.name,
          revenue: item.revenue,
          units: item.units,
          revenue_share_pct: +(item.share * 100).toFixed(2),
          growth_pct: item.growth == null ? null : +(item.growth * 100).toFixed(2),
        }))
      }
    >
      {(expanded) => <Bars items={items} metric={metric} expanded={expanded} onSelect={onSelect} />}
    </ChartFrame>
  );
}

function Bars({
  items,
  metric,
  expanded,
  onSelect,
}: {
  items: RankedItem[];
  metric: Metric;
  expanded: boolean;
  onSelect: SelectHandler;
}) {
  const max = Math.max(...items.map((item) => item[metric]), 1);
  if (!items.length) return <p className="py-10 text-center text-xs text-slate-400">No model sales in this selection.</p>;
  return (
    <ol className={cn("space-y-1.5", expanded && "space-y-3 text-sm")}>
      {items.map((item, index) => {
        const value = item[metric];
        const pct = (value / max) * 100;
        return (
          <li key={item.key}>
            <button
              type="button"
              onClick={() => onSelect("model", item.name)}
              className="group grid w-full grid-cols-[1.25rem_minmax(0,7.5rem)_minmax(0,1fr)_auto] items-center gap-2 rounded-lg px-1 py-0.5 text-left transition hover:bg-slate-50 dark:hover:bg-muted"
              title={`${item.group} ${item.name}: ${formatInr(item.revenue)} · ${formatCount(item.units)} units`}
            >
              <span
                className={cn(
                  "flex size-5 items-center justify-center rounded-md text-[10px] font-bold tabular-nums",
                  index < 3 ? "bg-[#2f6fed] text-white" : "bg-slate-100 text-slate-500 dark:bg-muted",
                )}
              >
                {index + 1}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-xs font-semibold text-slate-800 dark:text-foreground">{item.name}</span>
                <span className="block truncate text-[10px] text-slate-400">{item.group}</span>
              </span>
              <span className="relative h-5 overflow-hidden rounded-md bg-slate-50 dark:bg-muted/50">
                <span
                  className="absolute inset-y-0 left-0 rounded-md transition-[width] duration-500"
                  style={{
                    width: `${Math.max(pct, 2)}%`,
                    background: `linear-gradient(90deg, ${metric === "revenue" ? COCKPIT.blueSoft : COCKPIT.tealSoft}, ${metric === "revenue" ? COCKPIT.blue : COCKPIT.teal})`,
                  }}
                />
                <span className="absolute inset-y-0 left-2 flex items-center text-[10px] font-semibold text-white mix-blend-normal">
                  {pct > 28 ? (metric === "revenue" ? formatInr(value) : formatCount(value)) : ""}
                </span>
                {pct <= 28 ? (
                  <span className="absolute inset-y-0 flex items-center text-[10px] font-semibold text-slate-600" style={{ left: `calc(${Math.max(pct, 2)}% + 6px)` }}>
                    {metric === "revenue" ? formatInr(value) : formatCount(value)}
                  </span>
                ) : null}
              </span>
              <span
                className={cn(
                  "w-14 text-right text-[10px] font-semibold tabular-nums",
                  item.growth == null ? "text-slate-400" : item.growth >= 0 ? "text-[#0f8f7e]" : "text-[#c8574d]",
                )}
              >
                {item.growth == null ? "new" : formatPct(item.growth, true)}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
