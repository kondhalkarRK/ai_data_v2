"use client";

import * as React from "react";

import { ChartFrame, Segmented } from "@/components/executive/cockpit/chart-frame";
import { formatInr, formatPct } from "@/components/executive/cockpit/format";
import { COCKPIT, growthColour, tint } from "@/components/executive/cockpit/palette";
import type { CockpitData, FilterKey, HeatMatrix, RankedItem, SelectHandler } from "@/components/executive/cockpit/types";
import { cn } from "@/lib/utils";

type Tab = "states" | "cities" | "dealers";

const TAB_FILTER: Record<Tab, FilterKey> = { states: "state", cities: "city", dealers: "dealer_id" };

export function GeoIntelligence({
  data,
  onSelect,
  className,
}: {
  data: CockpitData;
  onSelect: SelectHandler;
  className?: string;
}) {
  const [tab, setTab] = React.useState<Tab>("states");
  const items = data[tab].slice(0, 10);
  return (
    <ChartFrame
      title="Geography intelligence"
      subtitle="Top performers ranked by revenue · growth heat vs last year"
      exportName={`geography-${tab}`}
      className={className}
      controls={
        <Segmented
          value={tab}
          onChange={setTab}
          options={[
            { value: "states", label: "States" },
            { value: "cities", label: "Cities" },
            { value: "dealers", label: "Dealers" },
          ]}
        />
      }
      csv={() =>
        data[tab].map((item, i) => ({
          rank: i + 1,
          name: item.name,
          location: item.detail ?? "",
          region: item.group ?? "",
          revenue: item.revenue,
          units: item.units,
          share_pct: +(item.share * 100).toFixed(2),
          growth_pct: item.growth == null ? null : +(item.growth * 100).toFixed(2),
        }))
      }
    >
      {() => (
        <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
          <RankedGrid items={items} onPick={(item) => onSelect(TAB_FILTER[tab], item.key)} />
          <HeatGrid heat={data.heat} onPick={(zone) => onSelect("zone", zone)} />
        </div>
      )}
    </ChartFrame>
  );
}

function RankedGrid({ items, onPick }: { items: RankedItem[]; onPick: (item: RankedItem) => void }) {
  const max = Math.max(...items.map((i) => i.revenue), 1);
  if (!items.length) return <p className="py-8 text-center text-xs text-slate-400">No sales in this selection.</p>;
  return (
    <div>
      <div className="grid grid-cols-[1.25rem_minmax(0,1fr)_minmax(0,1fr)_3.25rem_3.75rem] gap-2 px-1 pb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
        <span>#</span>
        <span>Name</span>
        <span>Revenue</span>
        <span className="text-right">Share</span>
        <span className="text-right">Growth</span>
      </div>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={item.key}>
            <button
              type="button"
              onClick={() => onPick(item)}
              className="grid w-full grid-cols-[1.25rem_minmax(0,1fr)_minmax(0,1fr)_3.25rem_3.75rem] items-center gap-2 rounded-lg px-1 py-1 text-left text-xs transition hover:bg-slate-50 dark:hover:bg-muted"
            >
              <span className="text-[10px] font-bold tabular-nums text-slate-400">{i + 1}</span>
              <span className="min-w-0">
                <span className="block truncate font-medium text-slate-800 dark:text-foreground">{item.name}</span>
                <span className="block truncate text-[10px] text-slate-400">
                  {[item.detail, item.group].filter((v, idx, arr) => v && arr.indexOf(v) === idx).join(" · ")}
                </span>
              </span>
              <span className="flex min-w-0 items-center gap-1.5">
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-muted">
                  <span className="block h-full rounded-full bg-[#5b8def]" style={{ width: `${(item.revenue / max) * 100}%` }} />
                </span>
                <span className="w-16 shrink-0 text-right text-[10px] font-semibold tabular-nums text-slate-600 dark:text-muted-foreground">
                  {formatInr(item.revenue)}
                </span>
              </span>
              <span className="text-right text-[10px] tabular-nums text-slate-500">{formatPct(item.share)}</span>
              <span
                className="rounded-md px-1.5 py-0.5 text-right text-[10px] font-semibold tabular-nums"
                style={{
                  backgroundColor: growthColour(item.growth),
                  color:
                    item.growth == null
                      ? COCKPIT.grey
                      : Math.abs(item.growth) > 0.125
                        ? "#ffffff"
                        : item.growth >= 0
                          ? "#0b5f54"
                          : "#8f3a33",
                }}
              >
                {item.growth == null ? "new" : formatPct(item.growth, true)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function HeatGrid({ heat, onPick }: { heat: HeatMatrix; onPick: (zone: string) => void }) {
  if (!heat.rows.length) return null;
  const cell = new Map(heat.cells.map((c) => [`${c.row}|${c.col}`, c]));
  const maxShare = Math.max(...heat.cells.map((c) => c.share), 0.01);
  return (
    <div>
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
        Region × vehicle type · revenue mix
      </p>
      <div
        className="grid gap-1 text-[10px]"
        style={{ gridTemplateColumns: `4.5rem repeat(${heat.cols.length}, minmax(0, 1fr))` }}
      >
        <span />
        {heat.cols.map((col) => (
          <span key={col} className="truncate text-center font-semibold text-slate-500">
            {col}
          </span>
        ))}
        {heat.rows.map((row) => (
          <React.Fragment key={row}>
            <button type="button" className="truncate text-left font-semibold text-slate-600 hover:text-[#2f6fed] dark:text-muted-foreground" onClick={() => onPick(row)}>
              {row}
            </button>
            {heat.cols.map((col) => {
              const c = cell.get(`${row}|${col}`);
              const intensity = c ? c.share / maxShare : 0;
              return (
                <div
                  key={col}
                  className="flex h-10 flex-col items-center justify-center rounded-md"
                  style={{ backgroundColor: c ? tint(COCKPIT.blue, 0.92 - intensity * 0.62) : "#f8fafc" }}
                  title={c ? `${row} · ${col}: ${formatInr(c.revenue)} (${formatPct(c.share)} of region), ${formatPct(c.growth, true)} YoY` : undefined}
                >
                  {c ? (
                    <>
                      <span className={cn("font-bold tabular-nums", intensity > 0.55 ? "text-white" : "text-slate-700")}>
                        {formatPct(c.share, false, 0)}
                      </span>
                      <span
                        className={cn("tabular-nums", intensity > 0.55 ? "text-white/85" : "")}
                        style={intensity > 0.55 ? undefined : { color: c.growth == null ? COCKPIT.grey : c.growth >= 0 ? COCKPIT.positive : COCKPIT.negative }}
                      >
                        {c.growth == null ? "" : formatPct(c.growth, true, 0)}
                      </span>
                    </>
                  ) : null}
                </div>
              );
            })}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}
