"use client";

import type { regionalContributions } from "./revenue-lift";

const money = (value: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value);

export function RegionalContributions({ data }: { data: NonNullable<ReturnType<typeof regionalContributions>> }) {
  const max = Math.max(1, ...data.rows.map(row => Math.abs(row.delta)));
  return <article data-askbi-pdf className="min-w-0 rounded-2xl border border-border bg-surface-raised p-4 sm:p-5" aria-label="Observed revenue change by region">
    <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="text-sm font-semibold">Observed revenue change by region</h3><p className="mt-1 text-xs text-muted-foreground">{data.priorFrom} – {data.priorTo} compared with {data.currentFrom} – {data.currentTo}</p></div><p className={`text-sm font-semibold tabular-nums ${data.total >= 0 ? "text-success" : "text-danger"}`}>{data.total >= 0 ? "+" : ""}{money(data.total)}</p></div>
    <div className="mt-5 space-y-3" role="img" aria-label={`Total change ${money(data.total)}. ${data.rows.map(row => `${row.name}: ${row.delta >= 0 ? "increase" : "decrease"} ${money(Math.abs(row.delta))}`).join("; ")}`}>{data.rows.slice(0, 8).map(row => <div key={row.name} className="grid grid-cols-[minmax(5rem,9rem)_minmax(0,1fr)_auto] items-center gap-2 text-xs"><span className="truncate text-muted-foreground" title={row.name}>{row.name}</span><div className="h-2.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full" style={{ width: `${Math.abs(row.delta) / max * 100}%`, background: row.delta >= 0 ? "hsl(var(--success))" : "hsl(var(--danger))" }} /></div><span className="min-w-16 text-right font-medium tabular-nums">{row.delta > 0 ? "+" : row.delta < 0 ? "−" : ""}{money(Math.abs(row.delta))}</span></div>)}</div>
    <p className="mt-4 text-xs leading-relaxed text-muted-foreground">These are observed regional changes, not proven causes of revenue movement. The figures reconcile to the total; “Other / reconciliation” appears if the breakdown differs from it.</p>
    <details className="mt-3 border-t border-border pt-3 text-xs"><summary className="cursor-pointer text-muted-foreground">Inspect comparison values</summary><div className="mt-2 overflow-x-auto"><table className="w-full text-left"><thead><tr><th className="p-2">Region</th><th className="p-2">Prior revenue</th><th className="p-2">Current revenue</th><th className="p-2">Change</th></tr></thead><tbody>{data.rows.map(row => <tr key={row.name}><td className="border-t border-border p-2">{row.name}</td><td className="border-t border-border p-2">{row.name === "Other / reconciliation" ? "—" : money(row.prior)}</td><td className="border-t border-border p-2">{row.name === "Other / reconciliation" ? "—" : money(row.current)}</td><td className="border-t border-border p-2">{money(row.delta)}</td></tr>)}</tbody></table></div></details>
  </article>;
}
