"use client";

import * as React from "react";

import { ChartFrame, ChartTooltip } from "@/components/executive/cockpit/chart-frame";
import { useElementSize } from "@/components/executive/cockpit/chart-utils";
import { formatCount, formatInr, formatPct, formatPts } from "@/components/executive/cockpit/format";
import { COCKPIT, tint } from "@/components/executive/cockpit/palette";
import type { CockpitData, FilterKey, RankedItem, SelectHandler } from "@/components/executive/cockpit/types";

const FUEL_COLOURS: Record<string, string> = {
  Petrol: "#5b8def",
  Diesel: "#7c8ba1",
  Electric: "#14a3a1",
  Hybrid: "#5fc4bb",
  CNG: "#9db7f0",
};
const FAMILY_COLOURS: Record<string, string> = {
  SUV: "#2f6fed",
  Hatchback: "#14a3a1",
  Sedan: "#7c9cc9",
  "MUV / MPV": "#64748b",
};

interface Rect {
  item: RankedItem;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Squarified treemap layout (Bruls et al.): tiles stay close to square. */
function squarify(items: RankedItem[], x: number, y: number, w: number, h: number): Rect[] {
  const total = items.reduce((s, i) => s + i.units, 0);
  if (!total || w <= 0 || h <= 0) return [];
  const scale = (w * h) / total;
  const queue = items.filter((i) => i.units > 0).map((item) => ({ item, area: item.units * scale }));
  const out: Rect[] = [];
  let row: typeof queue = [];
  const worst = (r: typeof queue, side: number) => {
    const sum = r.reduce((s, c) => s + c.area, 0);
    const max = Math.max(...r.map((c) => c.area));
    const min = Math.min(...r.map((c) => c.area));
    return Math.max((side * side * max) / (sum * sum), (sum * sum) / (side * side * min));
  };
  const flush = () => {
    const sum = row.reduce((s, c) => s + c.area, 0);
    if (w >= h) {
      const colW = sum / h;
      let cy = y;
      for (const c of row) {
        const ch = c.area / colW;
        out.push({ item: c.item, x, y: cy, w: colW, h: ch });
        cy += ch;
      }
      x += colW;
      w -= colW;
    } else {
      const rowH = sum / w;
      let cx = x;
      for (const c of row) {
        const cw = c.area / rowH;
        out.push({ item: c.item, x: cx, y, w: cw, h: rowH });
        cx += cw;
      }
      y += rowH;
      h -= rowH;
    }
    row = [];
  };
  for (const cell of queue) {
    const side = Math.min(w, h);
    if (!row.length || worst([...row, cell], side) <= worst(row, side)) row.push(cell);
    else {
      flush();
      row.push(cell);
    }
  }
  if (row.length) flush();
  return out;
}

export function SalesMix({
  data,
  onSelect,
  className,
}: {
  data: CockpitData;
  onSelect: SelectHandler;
  className?: string;
}) {
  return (
    <ChartFrame
      title="Sales mix"
      subtitle={`Share of units · change vs ${data.period.priorLabel}`}
      exportName="sales-mix"
      className={className}
      csv={() =>
        [...data.fuelMix.map((i) => ({ ...i, mix: "fuel" })), ...data.bodyMix.map((i) => ({ ...i, mix: "vehicle_type" }))].map((i) => ({
          mix: i.mix,
          name: i.name,
          family: i.group ?? "",
          units: i.units,
          revenue: i.revenue,
          unit_share_pct: +(i.share * 100).toFixed(2),
          prior_share_pct: i.priorShare == null ? null : +(i.priorShare * 100).toFixed(2),
        }))
      }
    >
      {(expanded) => (
        <div className="flex h-full flex-col gap-3">
          <Treemap
            title="Fuel mix"
            items={data.fuelMix}
            height={expanded ? 220 : 92}
            colour={(item) => FUEL_COLOURS[item.name] ?? COCKPIT.greySoft}
            filterKey="engine_type"
            onSelect={onSelect}
          />
          <Treemap
            title="Vehicle type mix"
            items={data.bodyMix}
            height={expanded ? 360 : 150}
            colour={(item, index) => tint(FAMILY_COLOURS[item.group ?? ""] ?? COCKPIT.grey, Math.min(index, 6) * 0.07)}
            filterKey="car_type"
            onSelect={onSelect}
          />
        </div>
      )}
    </ChartFrame>
  );
}

function Treemap({
  title,
  items,
  height,
  colour,
  filterKey,
  onSelect,
}: {
  title: string;
  items: RankedItem[];
  height: number;
  colour: (item: RankedItem, index: number) => string;
  filterKey: FilterKey;
  onSelect: SelectHandler;
}) {
  const [ref, size] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = React.useState<{ rect: Rect; x: number; y: number } | null>(null);
  const rects = squarify(items, 0, 0, size.width, height);
  const colourByKey = new Map(items.map((item, i) => [item.key, colour(item, i)]));
  return (
    <div>
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">{title}</p>
      <div ref={ref} className="relative w-full" style={{ height }}>
        {size.width > 0 ? (
          <svg data-chart width={size.width} height={height} className="block overflow-hidden rounded-lg" role="img" aria-label={title}>
            {rects.map((r) => {
              const fill = colourByKey.get(r.item.key) ?? COCKPIT.grey;
              const delta = r.item.priorShare == null ? null : r.item.share - r.item.priorShare;
              const roomy = r.w > 64 && r.h > 34;
              const tiny = r.w > 34 && r.h > 18;
              return (
                <g
                  key={r.item.key}
                  className="cursor-pointer"
                  onClick={() => onSelect(filterKey, r.item.key)}
                  onMouseMove={(event) => {
                    const box = (event.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                    setHover({ rect: r, x: event.clientX - box.left, y: event.clientY - box.top });
                  }}
                  onMouseLeave={() => setHover(null)}
                >
                  <rect x={r.x + 1} y={r.y + 1} width={Math.max(r.w - 2, 0)} height={Math.max(r.h - 2, 0)} rx={6} fill={fill} opacity={hover && hover.rect.item.key !== r.item.key ? 0.7 : 1} />
                  {tiny ? (
                    <text x={r.x + 8} y={r.y + 15} fontSize={10.5} fontWeight={600} fill="#fff" pointerEvents="none">
                      {fit(r.item.name, r.w - 14, 10.5)}
                    </text>
                  ) : null}
                  {roomy ? (
                    <>
                      <text x={r.x + 8} y={r.y + 31} fontSize={13} fontWeight={700} fill="#fff" pointerEvents="none">
                        {formatPct(r.item.share)}
                      </text>
                      {delta != null && r.h > 50 ? (
                        <text x={r.x + 8} y={r.y + 45} fontSize={9.5} fill="#fff" opacity={0.85} pointerEvents="none">
                          {formatPts(delta)}
                        </text>
                      ) : null}
                    </>
                  ) : null}
                </g>
              );
            })}
          </svg>
        ) : null}
        {hover ? (
          <ChartTooltip x={hover.x} y={hover.y} width={size.width}>
            <p className="font-semibold text-slate-800 dark:text-foreground">
              {hover.rect.item.name}
              {hover.rect.item.group && hover.rect.item.group !== hover.rect.item.name ? (
                <span className="font-normal text-slate-400"> · {hover.rect.item.group}</span>
              ) : null}
            </p>
            <Row label="Unit share" value={formatPct(hover.rect.item.share)} />
            <Row label="Change" value={hover.rect.item.priorShare == null ? "—" : formatPts(hover.rect.item.share - hover.rect.item.priorShare)} />
            <Row label="Units" value={formatCount(hover.rect.item.units)} />
            <Row label="Revenue" value={formatInr(hover.rect.item.revenue)} />
          </ChartTooltip>
        ) : null}
      </div>
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

function fit(text: string, width: number, fontSize: number): string {
  const max = Math.floor(width / (fontSize * 0.58));
  if (text.length <= max) return text;
  return max > 3 ? `${text.slice(0, max - 1)}…` : "";
}
