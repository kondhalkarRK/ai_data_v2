"use client";

import * as React from "react";

import { ChartFrame, ChartTooltip, Segmented } from "@/components/executive/cockpit/chart-frame";
import { useElementSize } from "@/components/executive/cockpit/chart-utils";
import { formatCount, formatInr, formatPct } from "@/components/executive/cockpit/format";
import { COCKPIT } from "@/components/executive/cockpit/palette";
import type { CockpitData, RankedItem, SelectHandler } from "@/components/executive/cockpit/types";

type Level = "state" | "zone";
type Category = "Leader" | "Average" | "Underperforming";

const CATEGORY_STYLE: Record<Category, { fill: string; stroke: string }> = {
  Leader: { fill: "#2f6fed", stroke: "#1d4fc4" },
  Average: { fill: "#8fa6c4", stroke: "#64748b" },
  Underperforming: { fill: "#e3a19a", stroke: "#c8574d" },
};

export function BubbleMatrix({
  data,
  onSelect,
  className,
}: {
  data: CockpitData;
  onSelect: SelectHandler;
  className?: string;
}) {
  const [level, setLevel] = React.useState<Level>("state");
  const items = (level === "state" ? data.states : data.zones).filter((item) => item.revenue > 0);
  return (
    <ChartFrame
      title="Regional performance matrix"
      subtitle="Growth vs revenue contribution · bubble size = units sold"
      exportName="regional-matrix"
      className={className}
      controls={
        <Segmented
          value={level}
          onChange={setLevel}
          options={[
            { value: "state", label: "States" },
            { value: "zone", label: "Regions" },
          ]}
        />
      }
      csv={() =>
        items.map((item) => ({
          name: item.name,
          region: item.group,
          revenue: item.revenue,
          units: item.units,
          growth_pct: item.growth == null ? null : +(item.growth * 100).toFixed(2),
          contribution_pct: +(item.share * 100).toFixed(2),
        }))
      }
    >
      {(expanded) => (
        <MatrixSvg
          items={items}
          market={data.kpis.revenue.growth}
          expanded={expanded}
          onPick={(item) => (level === "state" ? onSelect("state", item.key) : onSelect("zone", item.key))}
        />
      )}
    </ChartFrame>
  );
}

function MatrixSvg({
  items,
  market,
  expanded,
  onPick,
}: {
  items: RankedItem[];
  market: number | null;
  expanded: boolean;
  onPick: (item: RankedItem) => void;
}) {
  const [ref, size] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = React.useState<RankedItem | null>(null);
  const width = size.width;
  const height = expanded ? Math.max(size.height, 320) : 268;
  const margin = { top: 14, right: 18, bottom: 34, left: 46 };
  const innerW = Math.max(width - margin.left - margin.right, 10);
  const innerH = height - margin.top - margin.bottom;

  const plotted = items.filter((item) => item.growth != null);
  if (!plotted.length) {
    return (
      <div ref={ref} className="flex h-[268px] items-center justify-center text-xs text-slate-400">
        No prior-year data to compare growth for this selection.
      </div>
    );
  }
  const growths = plotted.map((item) => Math.max(-0.6, Math.min(0.8, item.growth ?? 0)));
  const xMin = Math.min(...growths, (market ?? 0) - 0.05) - 0.03;
  const xMax = Math.max(...growths, (market ?? 0) + 0.05) + 0.03;
  const yMax = Math.max(...plotted.map((item) => item.share), 0.05) * 1.15;
  const x = (g: number) => margin.left + ((Math.max(-0.6, Math.min(0.8, g)) - xMin) / (xMax - xMin)) * innerW;
  const y = (s: number) => margin.top + innerH - (s / yMax) * innerH;
  const maxUnits = Math.max(...plotted.map((item) => item.units), 1);
  const radius = (units: number) => 5 + Math.sqrt(units / maxUnits) * (expanded ? 34 : 22);
  const xMid = market ?? 0;
  const yMid = 1 / plotted.length;
  const categorise = (item: RankedItem): Category => {
    const fast = (item.growth ?? 0) >= xMid;
    const big = item.share >= yMid;
    return fast && big ? "Leader" : !fast && !big ? "Underperforming" : "Average";
  };
  const xTicks = niceRange(xMin, xMax);
  const labelled = new Set([...plotted].sort((a, b) => b.share - a.share).slice(0, expanded ? 24 : 9).map((item) => item.key));

  return (
    <div ref={ref} className="relative w-full" style={{ height: expanded ? "100%" : height }}>
      {width > 0 ? (
        <svg data-chart width={width} height={height} className="block" role="img" aria-label="Regional performance matrix">
          <rect x={x(xMid)} y={margin.top} width={Math.max(width - margin.right - x(xMid), 0)} height={y(yMid) - margin.top} fill={COCKPIT.blueMist} opacity={0.6} />
          <rect x={margin.left} y={y(yMid)} width={Math.max(x(xMid) - margin.left, 0)} height={margin.top + innerH - y(yMid)} fill="#fbeeec" opacity={0.6} />
          {xTicks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={margin.top} y2={margin.top + innerH} stroke="#eef2f7" />
              <text x={x(t)} y={height - 18} textAnchor="middle" fontSize={10} fill="#94a3b8">
                {formatPct(t, true, 0)}
              </text>
            </g>
          ))}
          {[0, yMax / 2, yMax].map((t) => (
            <text key={t} x={margin.left - 6} y={y(t)} textAnchor="end" dominantBaseline="middle" fontSize={10} fill="#94a3b8">
              {formatPct(t, false, 0)}
            </text>
          ))}
          <line x1={x(xMid)} x2={x(xMid)} y1={margin.top} y2={margin.top + innerH} stroke="#94a3b8" strokeDasharray="4 4" />
          <line x1={margin.left} x2={width - margin.right} y1={y(yMid)} y2={y(yMid)} stroke="#94a3b8" strokeDasharray="4 4" />
          <text x={width - margin.right - 4} y={margin.top + 12} textAnchor="end" fontSize={10} fontWeight={700} fill={COCKPIT.blue}>
            LEADERS
          </text>
          <text x={margin.left + 4} y={margin.top + innerH - 6} fontSize={10} fontWeight={700} fill={COCKPIT.negative}>
            UNDERPERFORMING
          </text>
          <text x={margin.left + 4} y={margin.top + 12} fontSize={10} fontWeight={600} fill="#94a3b8">
            AVERAGE · defend share
          </text>
          <text x={width - margin.right - 4} y={margin.top + innerH - 6} textAnchor="end" fontSize={10} fontWeight={600} fill="#94a3b8">
            AVERAGE · rising
          </text>
          <text x={margin.left + innerW / 2} y={height - 3} textAnchor="middle" fontSize={10} fill="#64748b">
            Revenue growth YoY → (dashed = overall {formatPct(market, true)})
          </text>
          {[...plotted]
            .sort((a, b) => b.units - a.units)
            .map((item) => {
              const style = CATEGORY_STYLE[categorise(item)];
              const cx = x(item.growth ?? 0);
              const cy = y(item.share);
              const r = radius(item.units);
              const active = hover?.key === item.key;
              return (
                <g
                  key={item.key}
                  className="cursor-pointer"
                  onMouseEnter={() => setHover(item)}
                  onMouseLeave={() => setHover(null)}
                  onClick={() => onPick(item)}
                >
                  <circle cx={cx} cy={cy} r={r} fill={style.fill} fillOpacity={active ? 0.85 : 0.55} stroke={style.stroke} strokeWidth={active ? 2 : 1} />
                  {labelled.has(item.key) ? (
                    <text x={cx} y={cy} textAnchor="middle" dominantBaseline="middle" fontSize={r > 14 ? 10 : 9} fontWeight={600} fill={r > 12 ? "#fff" : COCKPIT.ink} pointerEvents="none">
                      {item.key.length <= 3 ? item.key : item.name}
                    </text>
                  ) : null}
                </g>
              );
            })}
        </svg>
      ) : null}
      {hover ? (
        <ChartTooltip x={x(hover.growth ?? 0)} y={y(hover.share)} width={width}>
          <p className="font-semibold text-slate-800 dark:text-foreground">
            {hover.name}
            {hover.group && hover.group !== hover.name ? <span className="font-normal text-slate-400"> · {hover.group}</span> : null}
          </p>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide" style={{ color: CATEGORY_STYLE[categorise(hover)].stroke }}>
            {categorise(hover)}
          </p>
          <Row label="Revenue" value={formatInr(hover.revenue)} />
          <Row label="Growth" value={formatPct(hover.growth, true)} />
          <Row label="Contribution" value={formatPct(hover.share)} />
          <Row label="Units" value={formatCount(hover.units)} />
          <p className="mt-1 text-[10px] text-slate-400">Click to filter the dashboard</p>
        </ChartTooltip>
      ) : null}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 py-0.5">
      <span className="text-slate-500">{label}</span>
      <span className="font-semibold tabular-nums text-slate-800 dark:text-foreground">{value}</span>
    </div>
  );
}

function niceRange(min: number, max: number): number[] {
  const span = max - min;
  const step = span > 0.6 ? 0.2 : span > 0.3 ? 0.1 : 0.05;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(4));
  return out;
}
