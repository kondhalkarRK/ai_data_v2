"use client";

import * as React from "react";
import type { AnalyticsSpec, BiPanel } from "@nql/shared-types";
import { ResultChart, type ChartKind } from "@/components/chat/result-chart";
import { ResultPreview } from "@/components/analytics-builder/analytics-builder-shell";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { Button } from "@/components/ui/button";
import { downloadCsv } from "@/lib/analytics/helpers";
import { panelScope, type PanelResult, type ReportAction } from "./use-askbi";

export function ReportPanel({ panel, state, selected, onSelect, onRetry, onCommand }: {
  panel: BiPanel; state?: PanelResult; selected: boolean; onSelect: () => void; onRetry: () => void;
  onCommand: (action: ReportAction, question?: string, value?: string, target?: string) => void;
}) {
  const [table, setTable] = React.useState(false);
  const result = state?.result;
  const current = state?.scope === panelScope(panel);
  const chart = result?.chart;
  const chartKind = (["bar", "line", "area", "pie", "scatter"].includes(panel.spec.viz) ? panel.spec.viz : ["bar", "line", "area", "pie", "scatter"].includes(chart?.type ?? "") ? chart?.type : "bar") as ChartKind;
  const metric = panel.spec.metrics[0] ?? "";
  const format = (value: unknown) => value == null ? "—" : typeof value === "number" ? new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, ...(result?.meta.metricFormat === "currency" ? { style: "currency", currency: "INR" } : {}) }).format(value) : String(value);
  const valueColumn = String(result?.meta.valueColumn ?? metric);
  const kpiValue = result?.rows[0]?.[valueColumn];
  return <article data-metric={metric} className={`askbi-panel flex h-full min-w-0 flex-col rounded-2xl border bg-surface-raised p-4 sm:p-5 ${selected ? "border-primary" : "border-border"}`}>
    <div className="flex items-start justify-between gap-3"><div className="min-w-0"><h3 className="text-sm font-semibold leading-snug tracking-tight">{panel.title}</h3>{panel.kind === "chart" && <p className="mt-1 text-xs text-muted-foreground">{panel.spec.dateFrom} – {panel.spec.dateTo}</p>}</div>
      <details className="relative shrink-0 text-xs"><summary className="cursor-pointer rounded-lg border border-border px-2.5 py-1.5 text-muted-foreground hover:text-foreground focus-visible:outline-ring" aria-label={`${panel.title} options`}>Options</summary><div className="absolute right-0 z-20 mt-1 w-44 space-y-1 rounded-xl border border-border bg-background p-2 shadow-lg"><button type="button" className="block w-full rounded px-2 py-1 text-left hover:bg-muted" onClick={onSelect}>Ask about this</button><button type="button" className="block w-full rounded px-2 py-1 text-left hover:bg-muted" onClick={() => setTable(value => !value)}>{table ? "Show chart" : "Inspect data"}</button><button type="button" className="block w-full rounded px-2 py-1 text-left hover:bg-muted" onClick={() => onCommand("move_up", "", undefined, panel.id)}>Move up</button><button type="button" className="block w-full rounded px-2 py-1 text-left hover:bg-muted" onClick={() => onCommand("move_down", "", undefined, panel.id)}>Move down</button><button type="button" className="block w-full rounded px-2 py-1 text-left text-danger hover:bg-muted" onClick={() => onCommand("remove", "", undefined, panel.id)}>Remove</button></div></details></div>
    <p role="status" className="mt-2 text-xs text-muted-foreground">{state?.loading ? result ? "Updating · previous values shown" : "Loading data…" : result && !current ? "Previous selection · refresh to update" : ""}</p>
    {result && !current && <p className="text-xs text-muted-foreground">Shown scope: {state?.resultSpec?.dateFrom ?? "previous"} – {state?.resultSpec?.dateTo ?? "selection"}</p>}
    {state?.error && <p role="alert" className="mt-2 text-xs text-danger">{state.error}</p>}
    {(!result || state?.error || !current) && <Button size="sm" variant="secondary" className="mt-2 self-start" disabled={state?.loading} onClick={onRetry}>Retry</Button>}
    {result && (result.rows.length === 0 ? <p className="flex min-h-36 items-center text-sm text-muted-foreground">No data for this selection. This is not a zero value.</p> : panel.kind === "kpi" && !table ? <div className="mt-auto pt-5"><div className="askbi-kpi-value text-3xl font-semibold tabular-nums sm:text-4xl">{typeof kpiValue === "number" ? <AnimatedNumber value={kpiValue} format={format} /> : format(kpiValue)}</div><p className="mt-2 text-xs text-muted-foreground">{panel.spec.dateFrom} – {panel.spec.dateTo}</p></div> : !table && panel.kind === "chart" && chart ? panel.spec.viz === "bar" && panel.spec.dimensions.length === 1 && !["month", "year", "quarter"].includes(panel.spec.dimensions[0] ?? "") ? <RankedBars points={chart.points} x={chart.x} y={chart.y} format={format} title={panel.title} /> : panel.spec.viz === "treemap" ? <ReportTreemap points={chart.points} x={chart.x} y={chart.y} format={format} title={panel.title} /> : panel.spec.viz === "heatmap" ? <ResultPreview result={result} viz={panel.spec.viz} tab="chart" filterLabel={null} /> : <ResultChart key={`${panel.id}-${panel.spec.viz}-${panel.daily}`} rows={chart.points} columns={result.columns} xKey={chart.x} yKey={chart.y} series={chart.series} initialType={chartKind} hideTypeSelect hideControls hideHeading /> : <div className="mt-4 overflow-auto"><table className="w-full text-left text-xs"><caption className="sr-only">{panel.title} underlying data</caption><thead><tr>{result.columns.map(column => <th className="p-2" key={column}>{column}</th>)}</tr></thead><tbody>{result.rows.map((row, index) => <tr key={index}>{result.columns.map(column => <td key={column} className="border-t border-border p-2">{format(row[column])}</td>)}</tr>)}</tbody></table></div>)}
    {result?.insights?.executive && panel.kind === "chart" && <p className="mt-3 border-t border-border pt-3 text-xs leading-relaxed text-muted-foreground">{result.insights.executive}</p>}
    <details className="mt-3 border-t border-border pt-3 text-xs"><summary className="cursor-pointer text-muted-foreground focus-visible:outline-ring">Data and definition</summary><div className="mt-2 space-y-2 text-muted-foreground"><p>{panel.rationale}</p><p>Data as of: {String(result?.meta.dataAsOf ?? "Unknown")}</p>{result?.meta.notes?.map((note, index) => <p key={index}>{String(note)}</p>)}{result?.meta.warnings?.map((note, index) => <p key={index}>{String(note)}</p>)}{panel.spec.dimensions.length > 0 && <label className="block">Visualization <select aria-label={`${panel.title} visualization`} className="ml-2 rounded border border-input bg-background p-1" value={panel.spec.viz} onChange={event => onCommand("visualize", "", event.target.value as AnalyticsSpec["viz"], panel.id)}>{["auto", "bar", "line", "area", "pie", "donut", "scatter", "heatmap", "treemap", "table"].map(viz => <option key={viz}>{viz}</option>)}</select></label>}{result && <><Button size="sm" variant="secondary" onClick={() => downloadCsv(`${panel.title}.csv`, result.columns, result.rows)}>Export CSV</Button><details><summary>Governed SQL</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap">{result.sql}</pre></details></>}<a className="block text-primary underline" href="/data-quality">Open Data Trust</a></div></details>
  </article>;
}

function RankedBars({ points, x, y, format, title }: { points: Array<Record<string, unknown>>; x: string; y: string; format: (value: unknown) => string; title: string }) {
  const rows = points.map(point => ({ label: String(point[x] ?? "Unknown"), value: Number(point[y]) })).filter(point => Number.isFinite(point.value)).slice(0, 8);
  const max = Math.max(0, ...rows.map(row => row.value));
  if (!rows.length) return <p className="py-10 text-sm text-muted-foreground">No chartable rows.</p>;
  return <div className="mt-5 space-y-3" role="img" aria-label={`${title}. ${rows.map(row => `${row.label}: ${format(row.value)}`).join("; ")}`}>
    {rows.map((row, index) => <div key={`${row.label}-${index}`} className="grid grid-cols-[minmax(5rem,8rem)_minmax(0,1fr)_auto] items-center gap-2 text-xs"><span className="truncate text-muted-foreground" title={row.label}>{row.label}</span><div className="h-2.5 overflow-hidden rounded-full bg-muted"><div className="askbi-bar h-full rounded-full" style={{ width: `${max > 0 ? Math.max(2, row.value / max * 100) : 0}%` }} /></div><span className="min-w-14 text-right font-medium tabular-nums">{format(row.value)}</span></div>)}
  </div>;
}

function ReportTreemap({ points, x, y, format, title }: { points: Array<Record<string, unknown>>; x: string; y: string; format: (value: unknown) => string; title: string }) {
  const rows = points.map(point => ({ label: String(point[x] ?? "Unknown"), value: Number(point[y]) })).filter(point => Number.isFinite(point.value) && point.value > 0).slice(0, 12);
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  if (!total) return <p className="py-10 text-sm text-muted-foreground">No positive values to display as a composition.</p>;
  const split = rows.findIndex((_, index) => rows.slice(0, index + 1).reduce((sum, row) => sum + row.value, 0) >= total / 2);
  const groups = [rows.slice(0, split + 1), rows.slice(split + 1)].filter(group => group.length);
  const rectangles = groups.flatMap((group, groupIndex) => {
    const groupTotal = group.reduce((sum, row) => sum + row.value, 0);
    const height = 260 * groupTotal / total;
    const top = 260 * groups.slice(0, groupIndex).flat().reduce((sum, row) => sum + row.value, 0) / total;
    return group.map((row, index) => {
      const width = 640 * row.value / groupTotal;
      const left = 640 * group.slice(0, index).reduce((sum, item) => sum + item.value, 0) / groupTotal;
      const item = { ...row, left, top, width, height, index: rows.indexOf(row) };
      return item;
    });
  });
  return <div className="mt-4"><svg viewBox="0 0 640 260" className="h-[260px] w-full rounded-xl" role="img" aria-label={`${title}. Rectangle area represents value. ${rows.map(row => `${row.label}: ${format(row.value)}`).join("; ")}`}>
    {rectangles.map(item => <g key={`${item.label}-${item.index}`}><rect x={item.left + 1} y={item.top + 1} width={Math.max(0, item.width - 2)} height={Math.max(0, item.height - 2)} rx="5" className={`askbi-tree-tile-${item.index % 6}`} /><title>{item.label}: {format(item.value)}</title>{item.width > 110 && item.height > 55 && <><text x={item.left + 10} y={item.top + item.height - 28} className="fill-foreground text-[12px] font-semibold">{item.label.slice(0, 18)}</text><text x={item.left + 10} y={item.top + item.height - 11} className="fill-foreground text-[11px]">{format(item.value)}</text></>}</g>)}
  </svg><p className="mt-2 text-xs text-muted-foreground">Area represents share of the displayed values. Hover or inspect data for exact figures.</p></div>;
}
