"use client";

import * as React from "react";

import { ChartFrame, ChartTooltip } from "@/components/executive/cockpit/chart-frame";
import { monotonePath, niceMax, runs, useElementSize } from "@/components/executive/cockpit/chart-utils";
import { formatCompact, formatCount, formatInr, formatMonth, formatPct } from "@/components/executive/cockpit/format";
import { COCKPIT } from "@/components/executive/cockpit/palette";
import type { CockpitData, TrendPoint } from "@/components/executive/cockpit/types";
import { cn } from "@/lib/utils";

type SeriesKey = "revenue" | "units" | "forecast" | "prior";

const SERIES: Array<{ key: SeriesKey; label: string; colour: string; dashed?: boolean }> = [
  { key: "revenue", label: "Revenue", colour: COCKPIT.blue },
  { key: "units", label: "Units", colour: COCKPIT.teal },
  { key: "forecast", label: "Forecast", colour: "#7c9cc9", dashed: true },
  { key: "prior", label: "Last year", colour: COCKPIT.greySoft, dashed: true },
];

export function TrendChart({ data, className }: { data: CockpitData; className?: string }) {
  const [visible, setVisible] = React.useState<Record<SeriesKey, boolean>>({
    revenue: true,
    units: true,
    forecast: true,
    prior: false,
  });
  return (
    <ChartFrame
      title="Revenue trend"
      subtitle={`Last 24 months${data.trend.some((p) => p.revenue == null) ? " + 6-month forecast" : ""} · Diwali and shocks highlighted`}
      exportName="revenue-trend"
      className={className}
      csv={() =>
        data.trend.map((p) => ({
          month: p.month,
          revenue: p.revenue,
          units: p.units,
          forecast_revenue: p.forecastRevenue,
          forecast_units: p.forecastUnits,
          last_year_revenue: p.priorRevenue,
        }))
      }
      controls={
        <div className="mr-1 hidden items-center gap-1 sm:flex">
          {SERIES.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => setVisible((v) => ({ ...v, [s.key]: !v[s.key] }))}
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-2xs font-medium transition",
                visible[s.key] ? "bg-slate-100 text-slate-700 dark:bg-muted dark:text-foreground" : "text-slate-400",
              )}
            >
              <span
                className="inline-block h-0.5 w-3 rounded"
                style={{
                  backgroundColor: visible[s.key] ? s.colour : COCKPIT.greySoft,
                  backgroundImage: s.dashed ? "none" : undefined,
                }}
              />
              {s.label}
            </button>
          ))}
        </div>
      }
    >
      {(expanded) => <TrendSvg data={data} visible={visible} expanded={expanded} />}
    </ChartFrame>
  );
}

function TrendSvg({
  data,
  visible,
  expanded,
}: {
  data: CockpitData;
  visible: Record<SeriesKey, boolean>;
  expanded: boolean;
}) {
  const [ref, size] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = React.useState<number | null>(null);
  const points = data.trend;
  const width = size.width;
  const height = expanded ? Math.max(size.height, 320) : 268;
  const margin = { top: 24, right: 46, bottom: 26, left: 56 };
  const innerW = Math.max(width - margin.left - margin.right, 10);
  const innerH = height - margin.top - margin.bottom;
  const n = points.length;
  const band = innerW / Math.max(n, 1);
  const x = (i: number) => margin.left + (i + 0.5) * band;

  const revMax = niceMax(
    Math.max(
      ...points.map((p) =>
        Math.max(p.revenue ?? 0, visible.forecast ? (p.forecastRevenue ?? 0) : 0, visible.prior ? (p.priorRevenue ?? 0) : 0),
      ),
      1,
    ),
  );
  const unitMax = niceMax(Math.max(...points.map((p) => Math.max(p.units ?? 0, p.forecastUnits ?? 0)), 1));
  const yRev = (v: number) => margin.top + innerH - (v / revMax.max) * innerH;
  const yUnits = (v: number) => margin.top + innerH - (v / unitMax.max) * innerH;
  const ticks = Array.from({ length: Math.round(revMax.max / revMax.step) + 1 }, (_, i) => i * revMax.step);

  const line = (value: (p: TrendPoint) => number | null, y: (v: number) => number) =>
    runs(points, value).map((run) => monotonePath(run.map(([i, v]) => [x(i), y(v)])));

  const revenueRuns = runs(points, (p) => p.revenue);
  const eventByMonth = new Map(data.events.map((e) => [e.month, e]));
  const labelEvery = Math.max(1, Math.ceil(n / Math.max(innerW / 52, 1)));
  const baseline = margin.top + innerH;
  const hovered = hover != null ? points[hover] : null;

  return (
    <div ref={ref} className="relative w-full" style={{ height: expanded ? "100%" : height }}>
      {width > 0 ? (
        <svg data-chart width={width} height={height} className="block" role="img" aria-label="Revenue trend chart">
          <defs>
            <linearGradient id="trend-revenue-fill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={COCKPIT.blue} stopOpacity={0.28} />
              <stop offset="100%" stopColor={COCKPIT.blue} stopOpacity={0.02} />
            </linearGradient>
          </defs>

          {points.map((p, i) =>
            p.inPeriod ? (
              <rect key={`period-${p.month}`} x={x(i) - band / 2} y={margin.top} width={band} height={innerH} fill={COCKPIT.blueMist} opacity={0.55} />
            ) : null,
          )}
          {points.map((p, i) => {
            const event = eventByMonth.get(p.month);
            if (!event) return null;
            const festive = event.kind === "festive";
            return (
              <g key={`event-${p.month}`}>
                <rect x={x(i) - band / 2} y={margin.top} width={band} height={innerH} fill={festive ? COCKPIT.amberMist : COCKPIT.greyMist} opacity={0.95} />
                <text x={x(i)} y={margin.top - 8} textAnchor="middle" fontSize={10} fontWeight={600} fill={festive ? COCKPIT.amber : COCKPIT.grey}>
                  {event.label.replace(/ (\d{2})(\d{2})$/, " '$2")}
                </text>
              </g>
            );
          })}

          {ticks.map((t) => (
            <g key={t}>
              <line x1={margin.left} x2={width - margin.right} y1={yRev(t)} y2={yRev(t)} stroke="#e2e8f0" strokeDasharray={t === 0 ? undefined : "3 4"} />
              <text x={margin.left - 8} y={yRev(t)} textAnchor="end" dominantBaseline="middle" fontSize={10} fill="#94a3b8">
                {t === 0 ? "0" : `₹${formatCompact(t)}`}
              </text>
              {visible.units ? (
                <text x={width - margin.right + 8} y={yRev(t)} dominantBaseline="middle" fontSize={10} fill={COCKPIT.teal} opacity={0.8}>
                  {formatCompact((t / revMax.max) * unitMax.max)}
                </text>
              ) : null}
            </g>
          ))}

          {points.map((p, i) =>
            p.growthPeriod ? (
              <rect key={`growth-${p.month}`} x={x(i) - band / 2 + 1} y={baseline - 3} width={band - 2} height={3} rx={1.5} fill={COCKPIT.tealSoft} />
            ) : null,
          )}

          {visible.prior
            ? line((p) => p.priorRevenue, yRev).map((d, i) => (
                <path key={`prior-${i}`} d={d} fill="none" stroke="#94a3b8" strokeWidth={1.4} strokeDasharray="2 4" />
              ))
            : null}

          {visible.revenue
            ? revenueRuns.map((run, i) => {
                const path = monotonePath(run.map(([idx, v]) => [x(idx), yRev(v)]));
                const first = run[0]!;
                const last = run[run.length - 1]!;
                return (
                  <g key={`rev-${i}`}>
                    <path d={`${path} L${x(last[0])},${baseline} L${x(first[0])},${baseline} Z`} fill="url(#trend-revenue-fill)" />
                    <path d={path} fill="none" stroke={COCKPIT.blue} strokeWidth={2.2} strokeLinecap="round" />
                  </g>
                );
              })
            : null}

          {visible.forecast
            ? line((p) => p.forecastRevenue, yRev).map((d, i) => (
                <path key={`fc-${i}`} d={d} fill="none" stroke="#7c9cc9" strokeWidth={1.6} strokeDasharray="5 4" />
              ))
            : null}

          {visible.units
            ? line((p) => p.units, yUnits).map((d, i) => (
                <path key={`units-${i}`} d={d} fill="none" stroke={COCKPIT.teal} strokeWidth={1.7} strokeLinecap="round" />
              ))
            : null}

          {visible.revenue
            ? points.map((p, i) =>
                p.peak && p.revenue != null ? (
                  <g key={`peak-${p.month}`}>
                    <circle cx={x(i)} cy={yRev(p.revenue)} r={4} fill="#fff" stroke={COCKPIT.blue} strokeWidth={2} />
                    <text x={x(i)} y={yRev(p.revenue) - 9} textAnchor="middle" fontSize={9.5} fontWeight={600} fill={COCKPIT.ink}>
                      Peak {formatInr(p.revenue)}
                    </text>
                  </g>
                ) : p.partial && p.revenue != null ? (
                  <g key={`mtd-${p.month}`}>
                    <circle cx={x(i)} cy={yRev(p.revenue)} r={3.5} fill="#fff" stroke={COCKPIT.blue} strokeWidth={1.5} strokeDasharray="2 2" />
                    <text x={x(i)} y={yRev(p.revenue) - 8} textAnchor="middle" fontSize={9} fill="#94a3b8">
                      MTD
                    </text>
                  </g>
                ) : null,
              )
            : null}

          {points.map((p, i) =>
            i % labelEvery === 0 || i === n - 1 ? (
              <text key={`lbl-${p.month}`} x={x(i)} y={height - 8} textAnchor="middle" fontSize={10} fill={p.revenue == null ? "#a5b4cf" : "#94a3b8"}>
                {formatMonth(p.month)}
              </text>
            ) : null,
          )}

          {hover != null && hovered ? (
            <g pointerEvents="none">
              <line x1={x(hover)} x2={x(hover)} y1={margin.top} y2={baseline} stroke="#94a3b8" strokeDasharray="3 3" />
              {visible.revenue && hovered.revenue != null ? (
                <circle cx={x(hover)} cy={yRev(hovered.revenue)} r={4} fill={COCKPIT.blue} stroke="#fff" strokeWidth={1.5} />
              ) : null}
              {visible.units && hovered.units != null ? (
                <circle cx={x(hover)} cy={yUnits(hovered.units)} r={3.5} fill={COCKPIT.teal} stroke="#fff" strokeWidth={1.5} />
              ) : null}
              {visible.forecast && hovered.forecastRevenue != null ? (
                <circle cx={x(hover)} cy={yRev(hovered.forecastRevenue)} r={3} fill="#7c9cc9" stroke="#fff" strokeWidth={1.5} />
              ) : null}
            </g>
          ) : null}

          {points.map((p, i) => (
            <rect
              key={`hit-${p.month}`}
              x={x(i) - band / 2}
              y={margin.top}
              width={band}
              height={innerH}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            />
          ))}
        </svg>
      ) : null}
      {hovered && hover != null ? (
        <ChartTooltip x={x(hover)} y={margin.top} width={width}>
          <p className="mb-1 font-semibold text-slate-800 dark:text-foreground">
            {formatMonth(hovered.month)}
            {hovered.partial ? " · month to date" : ""}
            {eventByMonth.get(hovered.month) ? ` · ${eventByMonth.get(hovered.month)!.label}` : ""}
          </p>
          <TooltipRow colour={COCKPIT.blue} label="Revenue" value={formatInr(hovered.revenue)} />
          <TooltipRow colour={COCKPIT.teal} label="Units" value={formatCount(hovered.units)} />
          <TooltipRow colour="#7c9cc9" label="Forecast" value={formatInr(hovered.forecastRevenue)} />
          {hovered.revenue != null && hovered.priorRevenue ? (
            <TooltipRow colour="#94a3b8" label="YoY" value={formatPct(hovered.revenue / hovered.priorRevenue - 1, true)} />
          ) : null}
          {hovered.revenue != null && hovered.forecastRevenue ? (
            <TooltipRow colour="#94a3b8" label="vs forecast" value={formatPct(hovered.revenue / hovered.forecastRevenue - 1, true)} />
          ) : null}
        </ChartTooltip>
      ) : null}
    </div>
  );
}

function TooltipRow({ colour, label, value }: { colour: string; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-0.5">
      <span className="flex items-center gap-1.5 text-slate-500">
        <span className="size-2 rounded-full" style={{ backgroundColor: colour }} />
        {label}
      </span>
      <span className="font-semibold tabular-nums text-slate-800 dark:text-foreground">{value}</span>
    </div>
  );
}
