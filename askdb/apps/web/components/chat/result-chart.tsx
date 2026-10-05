"use client";

import * as React from "react";

import type { AnomalyMarker } from "@/components/chat/types";
import { CHART_SERIES } from "@/lib/design";
import { cn } from "@/lib/utils";

export type ChartKind = "bar" | "line" | "area" | "pie" | "scatter";

const CHART_KINDS: Array<{ id: ChartKind; label: string }> = [
  { id: "bar", label: "Bar" },
  { id: "line", label: "Line" },
  { id: "area", label: "Area" },
  { id: "pie", label: "Pie" },
  { id: "scatter", label: "Scatter" },
];

function isNumericColumn(rows: Array<Record<string, unknown>>, key: string): boolean {
  let seen = 0;
  for (const row of rows.slice(0, 30)) {
    const value = row[key];
    if (value == null || value === "") continue;
    const n = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(n)) return false;
    seen += 1;
  }
  return seen > 0;
}

export function ResultChart({
  xKey: initialX,
  yKey: initialY,
  rows,
  columns,
  series,
  anomalies = [],
  className,
  initialType = "bar",
  hideTypeSelect = false,
}: {
  xKey: string;
  yKey: string;
  rows: Array<Record<string, unknown>>;
  columns?: string[];
  series?: string[];
  anomalies?: AnomalyMarker[];
  className?: string;
  initialType?: ChartKind;
  hideTypeSelect?: boolean;
}) {
  const keys = React.useMemo(() => {
    if (columns?.length) return columns;
    return Object.keys(rows[0] ?? {});
  }, [columns, rows]);

  const numericKeys = React.useMemo(
    () => keys.filter((key) => isNumericColumn(rows, key)),
    [keys, rows],
  );

  const [xKey, setXKey] = React.useState(initialX || keys[0] || "");
  const [yKey, setYKey] = React.useState(
    initialY || numericKeys.find((key) => key !== initialX) || numericKeys[0] || keys[1] || "",
  );
  const [chartType, setChartType] = React.useState<ChartKind>(initialType);
  const [hover, setHover] = React.useState<number | null>(null);
  const seriesKeys = React.useMemo(
    () => (series ?? []).filter((key) => numericKeys.includes(key)),
    [series, numericKeys],
  );
  const [showAll, setShowAll] = React.useState(true);
  const multi = showAll && seriesKeys.length > 1 && chartType !== "pie";

  React.useEffect(() => {
    if (keys.includes(initialX)) setXKey(initialX);
    if (keys.includes(initialY)) setYKey(initialY);
  }, [initialX, initialY, keys]);

  React.useEffect(() => {
    setChartType(initialType);
  }, [initialType]);

  const points = React.useMemo(() => {
    return rows.slice(0, chartType === "pie" ? 12 : 48).map((row, index) => {
      const raw = row[yKey];
      const y = typeof raw === "number" ? raw : Number(raw);
      return {
        index,
        x: String(row[xKey] ?? index),
        y: Number.isFinite(y) ? y : 0,
      };
    });
  }, [rows, xKey, yKey, chartType]);

  if (!keys.length || !points.length) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No chartable rows in this result.
      </p>
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold tracking-tight">
          {multi ? seriesKeys.map(prettyKey).join(" vs ") : prettyKey(yKey)} by {prettyKey(xKey)}
        </p>
        <p className="text-[10px] text-muted-foreground">Hover a point for exact values</p>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <FieldSelect
          id="chart-x"
          label="X Axis"
          value={xKey}
          options={keys}
          onChange={setXKey}
        />
        <FieldSelect
          id="chart-y"
          label="Y Axis"
          value={multi ? ALL_SERIES : yKey}
          options={[
            ...(seriesKeys.length > 1 ? [ALL_SERIES] : []),
            ...(numericKeys.length ? numericKeys : keys),
          ]}
          labels={{ [ALL_SERIES]: "All series" }}
          onChange={(value) => {
            setShowAll(value === ALL_SERIES);
            if (value !== ALL_SERIES) setYKey(value);
          }}
        />
        {hideTypeSelect ? null : (
          <FieldSelect
            id="chart-type"
            label="Chart Type"
            value={chartType}
            options={CHART_KINDS.map((item) => item.id)}
            labels={Object.fromEntries(CHART_KINDS.map((item) => [item.id, item.label]))}
            onChange={(value) => setChartType(value as ChartKind)}
          />
        )}
      </div>

      {multi ? (
        <MultiSeriesChart
          rows={rows.slice(0, 48)}
          xKey={xKey}
          seriesKeys={seriesKeys}
          chartType={chartType as Exclude<ChartKind, "pie">}
        />
      ) : chartType === "pie" ? (
        <PieChart points={points} hover={hover} setHover={setHover} yKey={yKey} />
      ) : (
        <CartesianChart
          points={points}
          chartType={chartType}
          hover={hover}
          setHover={setHover}
          xKey={xKey}
          yKey={yKey}
          anomalies={anomalies}
        />
      )}
    </div>
  );
}

const ALL_SERIES = "__all_series__";

const SERIES_PALETTE = [
  CHART_SERIES.primary,
  CHART_SERIES.secondary,
  CHART_SERIES.positive,
  CHART_SERIES.attention,
  CHART_SERIES.ai,
  CHART_SERIES.muted,
];

function prettyKey(key: string): string {
  return key.replace(/_/g, " ");
}

function maybeNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** Axis bounds that always include zero, so negative values (growth %) draw below the baseline. */
function axisBounds(values: number[]): { min: number; max: number; range: number } {
  const max = Math.max(0, ...values);
  const min = Math.min(0, ...values);
  const range = max - min || 1;
  return { min, max: max === min ? min + 1 : max, range };
}

function tickLabel(value: number): string {
  return Math.abs(value) >= 1000 ? Math.round(value).toLocaleString() : String(Math.round(value * 10) / 10);
}

function MultiSeriesChart({
  rows,
  xKey,
  seriesKeys,
  chartType,
}: {
  rows: Array<Record<string, unknown>>;
  xKey: string;
  seriesKeys: string[];
  chartType: Exclude<ChartKind, "pie">;
}) {
  const [hover, setHover] = React.useState<number | null>(null);
  const width = 640;
  const height = 260;
  const pad = { top: 28, right: 16, bottom: 52, left: 58 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const bounds = axisBounds(
    rows.flatMap((row) => seriesKeys.map((key) => maybeNumber(row[key])).filter((v): v is number => v != null)),
  );
  const slot = plotW / Math.max(rows.length, 1);
  const barW = Math.max(3, (slot - 6) / seriesKeys.length);
  const cx = (index: number) => pad.left + index * slot + slot / 2;
  const cy = (value: number) => pad.top + ((bounds.max - value) / bounds.range) * plotH;
  const baseline = cy(0);

  return (
    <div className="relative w-full space-y-2 overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-[260px] w-full min-w-[320px]">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const y = pad.top + (1 - t) * plotH;
          return (
            <g key={t}>
              <line x1={pad.left} x2={width - pad.right} y1={y} y2={y} stroke="currentColor" className="text-border" />
              <text x={pad.left - 8} y={y + 3} textAnchor="end" className="fill-muted-foreground text-[10px]">
                {tickLabel(bounds.min + bounds.range * t)}
              </text>
            </g>
          );
        })}
        {bounds.min < 0 ? (
          <line x1={pad.left} x2={width - pad.right} y1={baseline} y2={baseline} stroke="currentColor" className="text-muted-foreground" strokeWidth={1.25} />
        ) : null}
        {seriesKeys.map((key, s) => {
          const color = SERIES_PALETTE[s % SERIES_PALETTE.length];
          if (chartType === "bar") {
            return rows.map((row, index) => {
              const value = maybeNumber(row[key]);
              if (value == null) return null;
              const y = cy(value);
              return (
                <rect
                  key={`${key}-${index}`}
                  x={pad.left + index * slot + 3 + s * barW}
                  y={Math.min(y, baseline)}
                  width={Math.max(1, barW - 1)}
                  height={Math.max(1, Math.abs(baseline - y))}
                  rx={2}
                  fill={color}
                  opacity={hover == null || hover === index ? 0.9 : 0.45}
                />
              );
            });
          }
          let pen = false;
          const path = rows
            .map((row, index) => {
              const value = maybeNumber(row[key]);
              if (value == null) {
                pen = false;
                return "";
              }
              const segment = `${pen ? "L" : "M"} ${cx(index)} ${cy(value)}`;
              pen = true;
              return segment;
            })
            .filter(Boolean)
            .join(" ");
          return (
            <g key={key}>
              {chartType === "area" && s === 0 ? (
                <path
                  d={`${path} L ${cx(rows.length - 1)} ${baseline} L ${cx(0)} ${baseline} Z`}
                  fill={color}
                  opacity={0.12}
                />
              ) : null}
              {chartType !== "scatter" ? (
                <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
              ) : null}
              {rows.map((row, index) => {
                const value = maybeNumber(row[key]);
                if (value == null) return null;
                return (
                  <circle
                    key={index}
                    cx={cx(index)}
                    cy={cy(value)}
                    r={chartType === "scatter" ? 4 : hover === index ? 4 : 2.25}
                    fill={color}
                  />
                );
              })}
            </g>
          );
        })}
        {rows.map((row, index) => (
          <g key={`x-${index}`}>
            <rect
              x={pad.left + index * slot}
              y={pad.top}
              width={slot}
              height={plotH}
              fill="transparent"
              onMouseEnter={() => setHover(index)}
              onMouseLeave={() => setHover(null)}
            />
            {index % Math.ceil(rows.length / 6) === 0 ? (
              <text x={cx(index)} y={height - 22} textAnchor="middle" className="fill-muted-foreground text-[9px]">
                {String(row[xKey] ?? index).slice(0, 10)}
              </text>
            ) : null}
          </g>
        ))}
        <text x={width / 2} y={height - 6} textAnchor="middle" className="fill-muted-foreground text-[10px]">
          {prettyKey(xKey)}
        </text>
      </svg>
      <ul className="flex flex-wrap gap-3 text-xs">
        {seriesKeys.map((key, s) => (
          <li key={key} className="flex items-center gap-1.5">
            <span
              className="size-2.5 rounded-sm"
              style={{ backgroundColor: SERIES_PALETTE[s % SERIES_PALETTE.length] }}
            />
            {prettyKey(key)}
          </li>
        ))}
      </ul>
      {hover != null && rows[hover] ? (
        <HoverCard
          title={String(rows[hover]?.[xKey] ?? "")}
          detail={seriesKeys
            .map((key) => {
              const value = maybeNumber(rows[hover]?.[key]);
              return `${prettyKey(key)}: ${value == null ? "—" : value.toLocaleString()}`;
            })
            .join(" · ")}
        />
      ) : null}
    </div>
  );
}

function FieldSelect({
  id,
  label,
  value,
  options,
  labels,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: string[];
  labels?: Record<string, string>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex min-w-[140px] flex-1 flex-col gap-1 text-[11px] text-muted-foreground">
      {label}
      <select
        id={id}
        className="h-9 rounded-[var(--radius-control)] border border-border bg-background px-2 text-xs text-foreground outline-none ring-primary/20 focus:ring-2"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {labels?.[option] ?? option}
          </option>
        ))}
      </select>
    </label>
  );
}

function CartesianChart({
  points,
  chartType,
  hover,
  setHover,
  xKey,
  yKey,
  anomalies,
}: {
  points: Array<{ index: number; x: string; y: number }>;
  chartType: Exclude<ChartKind, "pie">;
  hover: number | null;
  setHover: (value: number | null) => void;
  xKey: string;
  yKey: string;
  anomalies: AnomalyMarker[];
}) {
  const width = 640;
  const height = 260;
  const pad = { top: 28, right: 16, bottom: 52, left: 58 };
  const bounds = axisBounds(points.map((p) => p.y));
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const barW = Math.max(6, plotW / points.length - 4);
  const anomalyByIndex = new Map(anomalies.map((item) => [item.index, item]));
  const toY = (value: number) => pad.top + ((bounds.max - value) / bounds.range) * plotH;
  const baseline = toY(0);

  const coords = points.map((point, index) => {
    const x =
      chartType === "scatter"
        ? pad.left + ((index + 0.5) / points.length) * plotW
        : pad.left + index * (plotW / points.length) + 2 + barW / 2;
    return { ...point, cx: x, cy: toY(point.y) };
  });

  const linePath = coords
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.cx} ${point.cy}`)
    .join(" ");
  const areaPath = `${linePath} L ${coords[coords.length - 1]?.cx ?? pad.left} ${baseline} L ${
    coords[0]?.cx ?? pad.left
  } ${baseline} Z`;

  return (
    <div className="relative w-full overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-[260px] w-full min-w-[320px]">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const y = pad.top + (1 - t) * plotH;
          return (
            <g key={t}>
              <line
                x1={pad.left}
                x2={width - pad.right}
                y1={y}
                y2={y}
                stroke="currentColor"
                className="text-border"
                strokeWidth={1}
              />
              <text
                x={pad.left - 8}
                y={y + 3}
                textAnchor="end"
                className="fill-muted-foreground text-[10px]"
              >
                {tickLabel(bounds.min + bounds.range * t)}
              </text>
            </g>
          );
        })}
        {bounds.min < 0 ? (
          <line x1={pad.left} x2={width - pad.right} y1={baseline} y2={baseline} stroke="currentColor" className="text-muted-foreground" strokeWidth={1.25} />
        ) : null}

        {chartType === "area" ? (
          <path d={areaPath} fill={CHART_SERIES.primary} opacity={0.18} />
        ) : null}
        {chartType === "line" || chartType === "area" ? (
          <path
            d={linePath}
            fill="none"
            stroke={CHART_SERIES.primary}
            strokeWidth={2.25}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ) : null}

        {coords.map((point, index) => {
          const anomaly = anomalyByIndex.get(point.index);
          const barX = pad.left + index * (plotW / points.length) + 2;
          return (
            <g
              key={point.index}
              onMouseEnter={() => setHover(point.index)}
              onMouseLeave={() => setHover(null)}
            >
              {chartType === "bar" ? (
                <rect
                  x={barX}
                  y={Math.min(point.cy, baseline)}
                  width={barW}
                  height={Math.max(2, Math.abs(baseline - point.cy))}
                  rx={4}
                  fill={anomaly ? CHART_SERIES.attention : CHART_SERIES.primary}
                  opacity={hover === point.index ? 1 : 0.88}
                />
              ) : null}
              {chartType === "scatter" || chartType === "line" || chartType === "area" ? (
                <circle
                  cx={point.cx}
                  cy={point.cy}
                  r={chartType === "scatter" ? 4.5 : hover === point.index ? 4 : 2.5}
                  fill={anomaly ? CHART_SERIES.attention : CHART_SERIES.primary}
                />
              ) : null}
              {anomaly ? (
                <circle
                  cx={point.cx}
                  cy={point.cy - 10}
                  r={3.5}
                  fill={CHART_SERIES.attention}
                  stroke="hsl(var(--background))"
                  strokeWidth={2}
                >
                  <title>{anomaly.label}</title>
                </circle>
              ) : null}
              {index % Math.ceil(points.length / 6) === 0 ? (
                <text
                  x={point.cx}
                  y={height - 22}
                  textAnchor="middle"
                  className="fill-muted-foreground text-[9px]"
                >
                  {point.x.length > 10 ? `${point.x.slice(0, 8)}…` : point.x}
                </text>
              ) : null}
            </g>
          );
        })}
        <text
          x={12}
          y={height / 2}
          transform={`rotate(-90 12 ${height / 2})`}
          textAnchor="middle"
          className="fill-muted-foreground text-[10px]"
        >
          {yKey.replace(/_/g, " ")}
        </text>
        <text x={width / 2} y={height - 6} textAnchor="middle" className="fill-muted-foreground text-[10px]">
          {xKey.replace(/_/g, " ")}
        </text>
      </svg>
      {hover != null ? (
        <HoverCard
          title={points[hover]?.x ?? ""}
          detail={`${yKey}: ${points[hover]?.y.toLocaleString()}`}
          anomaly={anomalyByIndex.get(hover)?.label}
        />
      ) : null}
    </div>
  );
}

function PieChart({
  points,
  hover,
  setHover,
  yKey,
}: {
  points: Array<{ index: number; x: string; y: number }>;
  hover: number | null;
  setHover: (value: number | null) => void;
  yKey: string;
}) {
  const total = Math.max(
    points.reduce((sum, point) => sum + Math.abs(point.y), 0),
    1,
  );
  const cx = 160;
  const cy = 130;
  const r = 88;
  let angle = -Math.PI / 2;
  const slices = points.map((point) => {
    const portion = Math.abs(point.y) / total;
    const start = angle;
    angle += portion * Math.PI * 2;
    const end = angle;
    const large = end - start > Math.PI ? 1 : 0;
    const x1 = cx + r * Math.cos(start);
    const y1 = cy + r * Math.sin(start);
    const x2 = cx + r * Math.cos(end);
    const y2 = cy + r * Math.sin(end);
    return { ...point, portion, d: `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z` };
  });
  const palette = [
    CHART_SERIES.primary,
    CHART_SERIES.secondary,
    CHART_SERIES.positive,
    CHART_SERIES.attention,
    CHART_SERIES.ai,
    CHART_SERIES.muted,
  ];

  return (
    <div className="relative grid gap-3 md:grid-cols-[280px_1fr]">
      <svg viewBox="0 0 320 260" className="mx-auto h-[240px] w-full max-w-[320px]">
        {slices.map((slice, index) => (
          <path
            key={slice.index}
            d={slice.d}
            fill={palette[index % palette.length]}
            opacity={hover == null || hover === slice.index ? 0.92 : 0.35}
            onMouseEnter={() => setHover(slice.index)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
      </svg>
      <ul className="space-y-1.5 self-center text-xs">
        {slices.map((slice, index) => (
          <li key={slice.index} className="flex items-center justify-between gap-3">
            <span className="flex min-w-0 items-center gap-2">
              <span
                className="size-2.5 shrink-0 rounded-sm"
                style={{ backgroundColor: palette[index % palette.length] }}
              />
              <span className="truncate">{slice.x}</span>
            </span>
            <span className="tabular-nums text-muted-foreground">
              {(slice.portion * 100).toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
      {hover != null ? (
        <HoverCard
          title={points[hover]?.x ?? ""}
          detail={`${yKey}: ${points[hover]?.y.toLocaleString()}`}
        />
      ) : null}
    </div>
  );
}

function HoverCard({
  title,
  detail,
  anomaly,
}: {
  title: string;
  detail: string;
  anomaly?: string;
}) {
  return (
    <div className="pointer-events-none absolute right-3 top-3 rounded-[var(--radius-control)] border border-border/70 bg-background/95 px-2.5 py-1.5 text-[11px] shadow-[var(--shadow-raised)]">
      <p className="font-medium">{title}</p>
      <p className="text-muted-foreground">{detail}</p>
      {anomaly ? <p className="text-orange">{anomaly}</p> : null}
    </div>
  );
}
