"use client";

import * as React from "react";

import { ChartFrame, ChartTooltip, Segmented } from "@/components/executive/cockpit/chart-frame";
import { monotonePath, runs, useElementSize } from "@/components/executive/cockpit/chart-utils";
import type { DataReliability, TrendEvent, TrustFilters } from "@/components/reliability/types";
import { DIMENSION_COLOUR, DIMENSION_LABEL, EmptyNote, formatScore, TRUST } from "@/components/reliability/ui";

type Range = "7" | "30" | "90";

const EVENT_STYLE: Record<TrendEvent["kind"], { colour: string; label: string }> = {
  drop: { colour: TRUST.amber, label: "Quality drop" },
  incident: { colour: TRUST.coral, label: "Incident" },
  drift: { colour: TRUST.teal, label: "Schema drift" },
};

const BANDS = [
  { min: 95, max: 100, colour: TRUST.green },
  { min: 85, max: 95, colour: TRUST.teal },
  { min: 70, max: 85, colour: TRUST.amber },
  { min: 0, max: 70, colour: TRUST.coral },
];

export function TrustTrendChart({
  data,
  filters,
  onOpenRule,
  className,
}: {
  data: DataReliability;
  filters: TrustFilters;
  onOpenRule: (id: string) => void;
  className?: string;
}) {
  const [range, setRange] = React.useState<Range>("30");
  const days = Number(range);
  const points = data.trend.points.slice(-days);
  const first = points[0]?.date ?? "";
  const events = data.trend.events.filter((e) => e.date >= first);
  const dimension = filters.dimension;

  return (
    <ChartFrame
      title="Trust score trend"
      subtitle={
        dimension
          ? `Overall score with ${DIMENSION_LABEL[dimension]} overlaid · by business date`
          : "Daily trust score by business date · drops, incidents and schema changes marked"
      }
      exportName={`trust-trend-${range}d`}
      className={className}
      controls={
        <Segmented<Range>
          value={range}
          onChange={setRange}
          options={[
            { value: "7", label: "7D" },
            { value: "30", label: "30D" },
            { value: "90", label: "90D" },
          ]}
        />
      }
      csv={() =>
        points.map((p) => ({
          date: p.date,
          trust_score: p.score,
          measured_run_score: p.measured,
          ...Object.fromEntries(Object.entries(p.dimensions).map(([k, v]) => [k, v])),
          events: events
            .filter((e) => e.date === p.date)
            .map((e) => `${EVENT_STYLE[e.kind].label}: ${e.title}`)
            .join(" | "),
        }))
      }
    >
      {(expanded) =>
        points.some((p) => p.score != null) ? (
          <>
            <TrendPlot points={points} events={events} dimension={dimension} height={expanded ? 520 : 236} />
            <EventStrip events={events} onOpenRule={onOpenRule} />
          </>
        ) : (
          <EmptyNote>
            No dated history yet. The trend fills in as checks run against daily data or as runs are recorded.
          </EmptyNote>
        )
      }
    </ChartFrame>
  );
}

function TrendPlot({
  points,
  events,
  dimension,
  height,
}: {
  points: DataReliability["trend"]["points"];
  events: TrendEvent[];
  dimension?: TrustFilters["dimension"];
  height: number;
}) {
  const [ref, size] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = React.useState<number | null>(null);
  const width = Math.max(size.width, 240);
  const pad = { top: 22, right: 14, bottom: 24, left: 34 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const values = points.flatMap((p) => [p.score, dimension ? (p.dimensions[dimension] ?? null) : null]);
  const lowest = Math.min(...values.filter((v): v is number => v != null), 100);
  const yMin = Math.max(0, Math.floor((lowest - 3) / 5) * 5);
  const yMax = 100;
  const x = (i: number) => pad.left + (points.length <= 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);
  const y = (v: number) => pad.top + (1 - (v - yMin) / (yMax - yMin || 1)) * plotH;
  const span = yMax - yMin;
  const step = span <= 5 ? 1 : span <= 10 ? 2 : span <= 25 ? 5 : span <= 50 ? 10 : 20;
  const ticks = Array.from({ length: Math.floor(span / step) + 1 }, (_, i) => yMin + i * step);
  const index = new Map(points.map((p, i) => [p.date, i]));

  const scorePaths = runs(points, (p) => p.score).map((run) => monotonePath(run.map(([i, v]) => [x(i), y(v)])));
  const dimPaths = dimension
    ? runs(points, (p) => p.dimensions[dimension] ?? null).map((run) =>
        monotonePath(run.map(([i, v]) => [x(i), y(v)])),
      )
    : [];
  const last = [...points].reverse().find((p) => p.score != null);
  const area =
    scorePaths.length === 1 && points.every((p) => p.score != null)
      ? `${scorePaths[0]} L${x(points.length - 1)},${pad.top + plotH} L${x(0)},${pad.top + plotH} Z`
      : null;

  const byDate = new Map<string, TrendEvent[]>();
  for (const e of events) byDate.set(e.date, [...(byDate.get(e.date) ?? []), e]);
  const hovered = hover != null ? points[hover] : undefined;
  const hoveredEvents = hovered ? (byDate.get(hovered.date) ?? []) : [];
  const labelEvery = Math.max(1, Math.ceil(points.length / Math.max(2, Math.floor(plotW / 70))));

  return (
    <div ref={ref} className="relative w-full" style={{ height }}>
      <svg
        data-chart
        width={width}
        height={height}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const px = event.clientX - rect.left - pad.left;
          const i = Math.round((px / plotW) * (points.length - 1));
          setHover(Math.max(0, Math.min(points.length - 1, i)));
        }}
      >
        <defs>
          <linearGradient id="trust-area" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={TRUST.blue} stopOpacity={0.16} />
            <stop offset="100%" stopColor={TRUST.blue} stopOpacity={0} />
          </linearGradient>
        </defs>
        {BANDS.filter((b) => b.max > yMin).map((b) => (
          <rect
            key={b.min}
            x={pad.left}
            width={plotW}
            y={y(b.max)}
            height={y(Math.max(b.min, yMin)) - y(b.max)}
            fill={b.colour}
            opacity={0.05}
          />
        ))}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={pad.left + plotW} y1={y(t)} y2={y(t)} stroke="#eef2f7" />
            <text x={pad.left - 6} y={y(t)} textAnchor="end" dominantBaseline="middle" fontSize={10} fill="#94a3b8">
              {Math.round(t)}
            </text>
          </g>
        ))}
        {points.map((p, i) =>
          i % labelEvery === 0 || (i === points.length - 1 && i % labelEvery >= labelEvery * 0.6) ? (
            <text key={p.date} x={x(i)} y={height - 6} textAnchor="middle" fontSize={10} fill="#94a3b8">
              {shortDate(p.date)}
            </text>
          ) : null,
        )}
        {area ? <path d={area} fill="url(#trust-area)" /> : null}
        {scorePaths.map((d, i) => (
          <path key={i} d={d} fill="none" stroke={TRUST.blue} strokeWidth={2} strokeLinejoin="round" />
        ))}
        {dimension
          ? dimPaths.map((d, i) => (
              <path
                key={`d${i}`}
                d={d}
                fill="none"
                stroke={DIMENSION_COLOUR[dimension]}
                strokeWidth={1.6}
                strokeDasharray="4 3"
              />
            ))
          : null}
        {points.map((p, i) =>
          p.measured != null ? (
            <circle key={`m${p.date}`} cx={x(i)} cy={y(p.measured)} r={2.5} fill="#fff" stroke={TRUST.grey} strokeWidth={1.2}>
              <title>Recorded run score {p.measured.toFixed(1)}</title>
            </circle>
          ) : null,
        )}
        {[...byDate.entries()].map(([date, list]) => {
          const i = index.get(date);
          if (i == null) return null;
          const cx = x(i);
          const score = points[i]?.score;
          return (
            <g key={date}>
              {list.some((e) => e.kind === "drop") && score != null ? (
                <circle cx={cx} cy={y(score)} r={5} fill={TRUST.amber} fillOpacity={0.25} stroke={TRUST.amber} strokeWidth={1.5} />
              ) : null}
              {(["incident", "drift"] as const)
                .filter((kind) => list.some((e) => e.kind === kind))
                .map((kind, k) => (
                  <g key={kind} transform={`translate(${cx + k * 10}, ${pad.top - 10})`}>
                    <line y1={4} y2={plotH + 10} stroke={EVENT_STYLE[kind].colour} strokeOpacity={0.25} strokeDasharray="2 3" />
                    {kind === "incident" ? (
                      <path d="M0,-4 L4.5,4 L-4.5,4 Z" fill={EVENT_STYLE[kind].colour} />
                    ) : (
                      <path d="M0,-4.5 L4.5,0 L0,4.5 L-4.5,0 Z" fill={EVENT_STYLE[kind].colour} />
                    )}
                  </g>
                ))}
            </g>
          );
        })}
        {last ? (
          <circle cx={x(points.indexOf(last))} cy={y(last.score!)} r={3.5} fill={TRUST.blue} stroke="#fff" strokeWidth={1.5} />
        ) : null}
        {hovered ? <line x1={x(hover!)} x2={x(hover!)} y1={pad.top} y2={pad.top + plotH} stroke="#cbd5e1" /> : null}
      </svg>

      <div className="pointer-events-none absolute right-1 top-0 flex gap-3 text-[10px] text-slate-500">
        {(["drop", "incident", "drift"] as const).map((k) => (
          <span key={k} className="flex items-center gap-1">
            <span className="size-2 rounded-full" style={{ backgroundColor: EVENT_STYLE[k].colour }} />
            {EVENT_STYLE[k].label}
          </span>
        ))}
      </div>

      {hovered ? (
        <ChartTooltip x={x(hover!)} y={hovered.score != null ? y(hovered.score) : pad.top} width={width}>
          <p className="font-semibold text-slate-800">{shortDate(hovered.date, true)}</p>
          <p className="mt-0.5 flex justify-between gap-4 text-slate-600">
            Trust score <span className="font-semibold tabular-nums text-slate-900">{formatScore(hovered.score)}</span>
          </p>
          {dimension ? (
            <p className="flex justify-between gap-4 text-slate-600">
              {DIMENSION_LABEL[dimension]}
              <span className="font-semibold tabular-nums">{formatScore(hovered.dimensions[dimension] ?? null)}</span>
            </p>
          ) : null}
          {hovered.measured != null ? (
            <p className="flex justify-between gap-4 text-slate-500">
              Recorded run <span className="tabular-nums">{hovered.measured.toFixed(1)}</span>
            </p>
          ) : null}
          {hoveredEvents.map((e, k) => (
            <p key={k} className="mt-1 border-t border-slate-100 pt-1" style={{ color: EVENT_STYLE[e.kind].colour }}>
              <span className="font-semibold">{EVENT_STYLE[e.kind].label}:</span>{" "}
              <span className="text-slate-600">{e.title}</span>
            </p>
          ))}
        </ChartTooltip>
      ) : null}
    </div>
  );
}

function EventStrip({ events, onOpenRule }: { events: TrendEvent[]; onOpenRule: (id: string) => void }) {
  const recent = [...events].reverse().slice(0, 4);
  if (!recent.length) {
    return <p className="mt-2 text-2xs text-slate-400">No quality drops, incidents or schema changes in this window.</p>;
  }
  return (
    <ul className="mt-2 grid gap-1.5 sm:grid-cols-2">
      {recent.map((e, k) => {
        const id = e.ruleIds[0];
        return (
          <li key={k}>
            <button
              type="button"
              disabled={!id}
              onClick={() => id && onOpenRule(id)}
              className="flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left text-2xs transition enabled:hover:bg-slate-50 dark:enabled:hover:bg-muted"
              title={e.detail}
            >
              <span className="mt-1 size-1.5 shrink-0 rounded-full" style={{ backgroundColor: EVENT_STYLE[e.kind].colour }} />
              <span className="min-w-0">
                <span className="block truncate font-medium text-slate-700 dark:text-foreground">{e.title}</span>
                <span className="text-slate-400">
                  {EVENT_STYLE[e.kind].label} · {shortDate(e.date)}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function shortDate(iso: string, year = false): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", year ? { day: "numeric", month: "short", year: "numeric" } : { day: "numeric", month: "short" });
}
