"use client";

import Link from "next/link";
import { ResultChart } from "./result-chart";
import type { ChatReportPreview } from "./types";
import { formatChatCell } from "@/lib/format-chat-cell";

/** Read-only evidence for the returned revision. No browser analytical queries. */
export function ReportPreview({ report }: { report: ChatReportPreview }) {
  const validId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(report.reportId);
  return <section aria-label="AskBI report preview" className="space-y-4 rounded-2xl border border-border bg-surface-raised p-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">AskBI report</h2><span className="text-xs text-muted-foreground">Revision {report.revision}</span></div>
    <p className="text-sm leading-relaxed">{report.briefing}</p>
    {report.partial && <p role="status" className="rounded-lg border border-warning/50 bg-warning/10 p-3 text-sm">Partial report. Unavailable panels have no verified values; other panels remain available.</p>}
    <div className="grid min-w-0 gap-3 sm:grid-cols-2">{report.panels.map(panel => <div key={panel.id} className="min-w-0 rounded-xl border border-border p-3">
      <h3 className="text-sm font-medium">{panel.title ?? panel.id.replace(/[-_]/g," ")}</h3>
      {["warnings", "notes"].map(key => Array.isArray(panel.result?.result.meta?.[key]) ? <ul key={key} className="my-2 list-inside list-disc text-xs text-muted-foreground">{(panel.result!.result.meta![key] as unknown[]).filter((note): note is string => typeof note === "string").map((note,index) => <li key={index}>{note}</li>)}</ul> : null)}
      {panel.status !== "verified" ? <p className="mt-2 text-sm text-muted-foreground">Unavailable — retry this panel in Builder.</p> : <div className="mt-2 overflow-x-auto">{panel.kind === "kpi" && panel.result?.result.rows[0] && <p className="mb-2 text-2xl font-semibold">{formatChatCell(panel.result.result.rows[0][panel.result.result.columns[0]!],panel.result.result.columns[0]!)}</p>}{panel.kind === "chart" && panel.result && panel.result.result.columns.length >= 2 && panel.result.result.rows.length > 0 && <ResultChart xKey={panel.result.result.columns[0]!} yKey={panel.result.result.columns[1]!} rows={panel.result.result.rows.slice(0,60)} columns={panel.result.result.columns} hideControls hideHeading initialType={panel.id.includes("month") ? "line" : "bar"} />}{panel.kind !== "kpi" && <table aria-label={`${panel.title ?? panel.id} preview`} className="w-full text-left text-xs"><thead><tr>{panel.result?.result.columns?.map(column => <th key={column} className="px-2 py-1 font-medium">{column.replaceAll("_"," ")}</th>)}</tr></thead><tbody>{panel.result?.result.rows?.slice(0,3).map((row,index) => <tr key={index}>{panel.result!.result.columns.map(column => <td key={column} className="border-t border-border px-2 py-2">{formatChatCell(row[column],column)}</td>)}</tr>)}</tbody></table>}<p className="mt-2 text-xs text-muted-foreground">{panel.result?.result.rows.length ? panel.kind === "kpi" ? "Verified value for this report revision." : "Preview: up to three rows; charts show up to 60. Full results in Builder." : "No matching records. This is not a zero result."}</p></div>}
    </div>)}</div>
    {validId && <Link className="inline-flex rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground focus-visible:outline-ring" href={`/analytics-builder?askbiReport=${report.reportId}`}>Open in Analytics Builder</Link>}
    <p className="text-xs text-muted-foreground">Preview of this revision. Builder checks current access and loads the latest revision.</p>
  </section>;
}
