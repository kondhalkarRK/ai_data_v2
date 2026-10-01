"use client";

import { ChevronRight, Filter } from "lucide-react";
import * as React from "react";

import { ChartFrame, ChartTooltip } from "@/components/executive/cockpit/chart-frame";
import { useElementSize } from "@/components/executive/cockpit/chart-utils";
import { formatInr, formatPct } from "@/components/executive/cockpit/format";
import { categoryColour, COCKPIT, tint } from "@/components/executive/cockpit/palette";
import type { CockpitData, SelectHandler, SunburstNode } from "@/components/executive/cockpit/types";

const ENGINE_COLOURS: Record<string, string> = {
  Petrol: "#9db7f0",
  Diesel: "#94a3b8",
  Electric: "#14a3a1",
  Hybrid: "#6fcfc4",
  CNG: "#b4c6dc",
};

interface Arc {
  node: SunburstNode;
  path: string[];
  depth: number;
  start: number;
  end: number;
  colour: string;
}

export function RevenueSunburst({
  data,
  onSelect,
  className,
}: {
  data: CockpitData;
  onSelect: SelectHandler;
  className?: string;
}) {
  const [focus, setFocus] = React.useState<string | null>(null);
  const roots = data.sunburst;
  const single = roots.length === 1 ? roots[0]!.name : null;
  const focused = single ?? (focus && roots.some((r) => r.name === focus) ? focus : null);
  return (
    <ChartFrame
      title="Revenue contribution"
      subtitle="Make → model → engine type · click a make to drill in"
      exportName="revenue-sunburst"
      className={className}
      csv={() =>
        roots.flatMap((make) =>
          make.children.flatMap((model) =>
            (model.children.length ? model.children : [null]).map((engine) => ({
              make: make.name,
              model: model.name,
              engine_type: engine?.name ?? "",
              revenue: engine?.revenue ?? model.revenue,
              units: engine?.units ?? model.units,
            })),
          ),
        )
      }
    >
      {(expanded) => (
        <SunburstBody
          roots={roots}
          focused={focused}
          canReset={!single}
          expanded={expanded}
          onFocus={setFocus}
          onSelect={onSelect}
        />
      )}
    </ChartFrame>
  );
}

function SunburstBody({
  roots,
  focused,
  canReset,
  expanded,
  onFocus,
  onSelect,
}: {
  roots: SunburstNode[];
  focused: string | null;
  canReset: boolean;
  expanded: boolean;
  onFocus: (name: string | null) => void;
  onSelect: SelectHandler;
}) {
  const [ref, size] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = React.useState<{ arc: Arc; x: number; y: number } | null>(null);
  const total = roots.reduce((sum, r) => sum + r.revenue, 0);
  const makeIndex = new Map(roots.map((r, i) => [r.name, i]));
  const focusNode = focused ? roots.find((r) => r.name === focused) ?? null : null;
  const levelNodes = focusNode ? focusNode.children : roots;
  const levelTotal = focusNode ? focusNode.revenue : total;

  const height = expanded ? Math.max(size.height - 8, 300) : 262;
  const svgSize = Math.min(height, Math.max(size.width * (size.width > 520 ? 0.6 : 1), 160));
  const R = svgSize / 2 - 4;
  const rings = focusNode ? [0.36, 0.72, 1] : [0.3, 0.6, 0.82, 1];

  const arcs: Arc[] = [];
  const layout = (nodes: SunburstNode[], start: number, span: number, depth: number, path: string[], colour: (n: SunburstNode, i: number) => string) => {
    const sum = nodes.reduce((s, n) => s + n.revenue, 0) || 1;
    let angle = start;
    nodes.forEach((node, i) => {
      const width = (node.revenue / sum) * span;
      const c = colour(node, i);
      arcs.push({ node, path: [...path, node.name], depth, start: angle, end: angle + width, colour: c });
      if (node.children.length && depth + 1 < rings.length - 1) {
        layout(node.children, angle, width, depth + 1, [...path, node.name], (child, j) =>
          child.dimension === "engine_type"
            ? (ENGINE_COLOURS[child.name] ?? COCKPIT.greySoft)
            : tint(c, 0.15 + Math.min(j, 10) * 0.055),
        );
      }
      angle += width;
    });
  };
  const span = Math.PI * 2;
  if (focusNode) {
    const base = categoryColour(makeIndex.get(focusNode.name) ?? 0);
    layout(focusNode.children, 0, span, 0, [focusNode.name], (_n, j) => tint(base, Math.min(j, 10) * 0.06));
  } else {
    layout(roots, 0, span, 0, [], (n) => categoryColour(makeIndex.get(n.name) ?? 0));
  }

  const centre = svgSize / 2;
  const arcPath = (a: Arc) => {
    const r0 = rings[a.depth]! * R;
    const r1 = rings[a.depth + 1]! * R - 1;
    const pad = Math.min(0.012, (a.end - a.start) / 4);
    const s = a.start + pad - Math.PI / 2;
    const e = a.end - pad - Math.PI / 2;
    const large = e - s > Math.PI ? 1 : 0;
    const p = (r: number, ang: number) => `${centre + r * Math.cos(ang)},${centre + r * Math.sin(ang)}`;
    return `M${p(r1, s)} A${r1},${r1} 0 ${large} 1 ${p(r1, e)} L${p(r0, e)} A${r0},${r0} 0 ${large} 0 ${p(r0, s)} Z`;
  };

  const handleClick = (arc: Arc) => {
    if (arc.node.dimension === "make") onFocus(arc.node.name);
    else if (arc.node.dimension === "model" && !/ other models$/.test(arc.node.name)) onSelect("model", arc.node.name);
    else if (arc.node.dimension === "engine_type") onSelect("engine_type", arc.node.name);
  };

  return (
    <div ref={ref} className="flex h-full w-full flex-col gap-2" style={{ minHeight: height }}>
      <div className="flex items-center gap-1 text-2xs text-slate-500">
        <button type="button" disabled={!focusNode || !canReset} className="font-medium enabled:text-[#2f6fed] enabled:hover:underline" onClick={() => onFocus(null)}>
          All makes
        </button>
        {focusNode ? (
          <>
            <ChevronRight className="size-3" />
            <span className="font-semibold text-slate-700 dark:text-foreground">{focusNode.name}</span>
            {canReset ? (
              <button
                type="button"
                className="ml-auto inline-flex items-center gap-1 rounded-full bg-[#e3ecfd] px-2 py-0.5 font-medium text-[#2f6fed] hover:bg-[#d3e1fc]"
                onClick={() => onSelect("make", focusNode.name)}
              >
                <Filter className="size-3" /> Filter dashboard to {focusNode.name}
              </button>
            ) : null}
          </>
        ) : null}
      </div>
      <div className="relative flex min-h-0 flex-1 items-center gap-4">
        {size.width > 0 ? (
          <svg data-chart width={svgSize} height={svgSize} className="shrink-0" role="img" aria-label="Revenue sunburst">
            {arcs.map((arc) => (
              <path
                key={arc.path.join("/")}
                d={arcPath(arc)}
                fill={arc.colour}
                stroke="#fff"
                strokeWidth={1}
                opacity={hover && !hover.arc.path.every((p, i) => arc.path[i] === p) && !arc.path.every((p, i) => hover.arc.path[i] === p) ? 0.45 : 1}
                className="cursor-pointer transition-opacity"
                onMouseMove={(event) => {
                  const box = (event.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                  setHover({ arc, x: event.clientX - box.left, y: event.clientY - box.top });
                }}
                onMouseLeave={() => setHover(null)}
                onClick={() => handleClick(arc)}
              />
            ))}
            {arcs
              .filter((a) => a.depth === 0 && (a.end - a.start) * rings[1]! * R > 34)
              .map((a) => {
                const mid = (a.start + a.end) / 2 - Math.PI / 2;
                const r = ((rings[0]! + rings[1]!) / 2) * R;
                return (
                  <text key={`l-${a.path.join("/")}`} x={centre + r * Math.cos(mid)} y={centre + r * Math.sin(mid)} textAnchor="middle" dominantBaseline="middle" fontSize={9.5} fontWeight={600} fill="#fff" pointerEvents="none">
                    {a.node.name.length > 10 ? `${a.node.name.slice(0, 9)}…` : a.node.name}
                  </text>
                );
              })}
            <circle
              cx={centre}
              cy={centre}
              r={rings[0]! * R - 2}
              fill="#fff"
              className={focusNode && canReset ? "cursor-pointer" : undefined}
              onClick={() => focusNode && canReset && onFocus(null)}
            />
            <text x={centre} y={centre - 8} textAnchor="middle" fontSize={10} fill="#94a3b8" pointerEvents="none">
              {focusNode ? focusNode.name : "Total revenue"}
            </text>
            <text x={centre} y={centre + 9} textAnchor="middle" fontSize={14} fontWeight={700} fill={COCKPIT.ink} pointerEvents="none">
              {formatInr(levelTotal)}
            </text>
            {focusNode && canReset ? (
              <text x={centre} y={centre + 24} textAnchor="middle" fontSize={9} fill={COCKPIT.blue} pointerEvents="none">
                ← back
              </text>
            ) : null}
          </svg>
        ) : null}
        {size.width > 380 ? (
          <ul className="min-w-0 flex-1 space-y-1.5 text-2xs">
            {levelNodes.slice(0, expanded ? 16 : 7).map((node, i) => (
              <li key={node.name}>
                <button
                  type="button"
                  className="flex w-full items-center gap-2 rounded px-1 py-0.5 text-left hover:bg-slate-50 dark:hover:bg-muted"
                  onClick={() => (node.dimension === "make" ? onFocus(node.name) : !/ other models$/.test(node.name) && onSelect("model", node.name))}
                >
                  <span
                    className="size-2.5 shrink-0 rounded-sm"
                    style={{
                      backgroundColor: focusNode
                        ? tint(categoryColour(makeIndex.get(focusNode.name) ?? 0), Math.min(i, 10) * 0.06)
                        : categoryColour(makeIndex.get(node.name) ?? 0),
                    }}
                  />
                  <span className="min-w-0 flex-1 truncate text-slate-700 dark:text-foreground">{node.name}</span>
                  <span className="tabular-nums text-slate-500">{formatPct(node.revenue / (levelTotal || 1))}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        {hover ? (
          <ChartTooltip x={hover.x} y={hover.y} width={size.width}>
            <p className="font-semibold text-slate-800 dark:text-foreground">{hover.arc.path.join(" › ")}</p>
            <div className="mt-1 flex justify-between gap-4">
              <span className="text-slate-500">Revenue</span>
              <span className="font-semibold tabular-nums">{formatInr(hover.arc.node.revenue)}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-slate-500">Share of total</span>
              <span className="font-semibold tabular-nums">{formatPct(hover.arc.node.revenue / (total || 1))}</span>
            </div>
            <p className="mt-1 text-[10px] text-slate-400">
              {hover.arc.node.dimension === "make" ? "Click to drill in" : "Click to filter the dashboard"}
            </p>
          </ChartTooltip>
        ) : null}
      </div>
    </div>
  );
}
