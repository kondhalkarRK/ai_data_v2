"use client";

import * as React from "react";

import type { AnomalyMarker } from "@/components/chat/types";
import { cn } from "@/lib/utils";

export function ResultChart({
  xKey,
  yKey,
  rows,
  anomalies = [],
  className,
}: {
  xKey: string;
  yKey: string;
  rows: Array<Record<string, unknown>>;
  anomalies?: AnomalyMarker[];
  className?: string;
}) {
  const [hover, setHover] = React.useState<number | null>(null);
  const points = React.useMemo(() => {
    return rows.slice(0, 40).map((row, index) => {
      const raw = row[yKey];
      const y = typeof raw === "number" ? raw : Number(raw);
      return {
        index,
        x: String(row[xKey] ?? index),
        y: Number.isFinite(y) ? y : 0,
      };
    });
  }, [rows, xKey, yKey]);

  if (!points.length) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">No chartable rows in this result.</p>
    );
  }

  const width = 640;
  const height = 240;
  const pad = { top: 16, right: 16, bottom: 36, left: 44 };
  const maxY = Math.max(...points.map((p) => p.y), 1);
  const barW = Math.max(8, (width - pad.left - pad.right) / points.length - 4);
  const anomalyByIndex = new Map(anomalies.map((item) => [item.index, item]));

  return (
    <div className={cn("relative w-full overflow-x-auto", className)}>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-[240px] w-full min-w-[320px]">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const y = pad.top + (1 - t) * (height - pad.top - pad.bottom);
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
        {points.map((point, index) => {
          const h = (point.y / maxY) * (height - pad.top - pad.bottom);
          const x =
            pad.left +
            index * ((width - pad.left - pad.right) / points.length) +
            2;
          const y = height - pad.bottom - h;
          const anomaly = anomalyByIndex.get(point.index);
          return (
            <g
              key={point.index}
              onMouseEnter={() => setHover(point.index)}
              onMouseLeave={() => setHover(null)}
            >
              <rect
                x={x}
                y={y}
                width={barW}
                height={Math.max(2, h)}
                rx={4}
                className={anomaly ? "fill-amber-500/80" : "fill-foreground/75"}
              />
              {anomaly ? (
                <circle
                  cx={x + barW / 2}
                  cy={y - 8}
                  r={4}
                  className="fill-amber-500 stroke-background"
                  strokeWidth={2}
                >
                  <title>{anomaly.label}</title>
                </circle>
              ) : null}
              {index % Math.ceil(points.length / 6) === 0 ? (
                <text
                  x={x + barW / 2}
                  y={height - 12}
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
        <div className="pointer-events-none absolute right-3 top-3 rounded-lg border border-border/70 bg-background/95 px-2.5 py-1.5 text-[11px] shadow-sm">
          <p className="font-medium">{points[hover]?.x}</p>
          <p className="text-muted-foreground">
            {yKey}: {points[hover]?.y.toLocaleString()}
          </p>
          {anomalyByIndex.get(hover) ? (
            <p className="text-amber-700 dark:text-amber-300">
              {anomalyByIndex.get(hover)?.label}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
