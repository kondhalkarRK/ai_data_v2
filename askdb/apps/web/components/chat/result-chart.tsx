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
  anomalies = [],
  className,
  initialType = "bar",
}: {
  xKey: string;
  yKey: string;
  rows: Array<Record<string, unknown>>;
  columns?: string[];
  anomalies?: AnomalyMarker[];
  className?: string;
  initialType?: ChartKind;
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
          value={yKey}
          options={numericKeys.length ? numericKeys : keys}
          onChange={setYKey}
        />
        <FieldSelect
          id="chart-type"
          label="Chart Type"
          value={chartType}
          options={CHART_KINDS.map((item) => item.id)}
          labels={Object.fromEntries(CHART_KINDS.map((item) => [item.id, item.label]))}
          onChange={(value) => setChartType(value as ChartKind)}
        />
      </div>

      {chartType === "pie" ? (
        <PieChart points={points} hover={hover} setHover={setHover} yKey={yKey} />
      ) : (
        <CartesianChart
          points={points}
          chartType={chartType}
          hover={hover}
          setHover={setHover}
          yKey={yKey}
          anomalies={anomalies}
        />
      )}
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
  yKey,
  anomalies,
}: {
  points: Array<{ index: number; x: string; y: number }>;
  chartType: Exclude<ChartKind, "pie">;
  hover: number | null;
  setHover: (value: number | null) => void;
  yKey: string;
  anomalies: AnomalyMarker[];
}) {
  const width = 640;
  const height = 260;
  const pad = { top: 16, right: 16, bottom: 40, left: 48 };
  const maxY = Math.max(...points.map((p) => p.y), 1);
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const barW = Math.max(6, plotW / points.length - 4);
  const anomalyByIndex = new Map(anomalies.map((item) => [item.index, item]));

  const coords = points.map((point, index) => {
    const x =
      chartType === "scatter"
        ? pad.left + ((index + 0.5) / points.length) * plotW
        : pad.left + index * (plotW / points.length) + 2 + barW / 2;
    const y = pad.top + (1 - point.y / maxY) * plotH;
    return { ...point, cx: x, cy: y };
  });

  const linePath = coords
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.cx} ${point.cy}`)
    .join(" ");
  const areaPath = `${linePath} L ${coords[coords.length - 1]?.cx ?? pad.left} ${
    pad.top + plotH
  } L ${coords[0]?.cx ?? pad.left} ${pad.top + plotH} Z`;

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
                {Math.round(maxY * t).toLocaleString()}
              </text>
            </g>
          );
        })}

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
          const h = (point.y / maxY) * plotH;
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
                  y={pad.top + plotH - h}
                  width={barW}
                  height={Math.max(2, h)}
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
                  y={height - 14}
                  textAnchor="middle"
                  className="fill-muted-foreground text-[9px]"
                >
                  {point.x.length > 10 ? `${point.x.slice(0, 8)}…` : point.x}
                </text>
              ) : null}
            </g>
          );
        })}
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
