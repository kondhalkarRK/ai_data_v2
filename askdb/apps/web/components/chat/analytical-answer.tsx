"use client";

import type { AnalyticalProgress, AnalyticalStepView, ChatMessage } from "./types";
import { ResultChart } from "./result-chart";
import { analyticalPresentation, formatAnalyticalCell } from "@/lib/analytical-response";

const STATUS: Record<string, string> = {
  completed: "Checked", partial: "Partially verified", empty: "No matching records",
  skipped: "Not answered", clarification: "Narrow the selection", pending: "Waiting for results",
};
const OPERATORS: Record<string, string> = { eq: "is", ne: "is not", in: "includes", not_in: "excludes", gt: ">", gte: "≥", lt: "<", lte: "≤", is_null: "has no value", not_null: "has a value" };

export function AnalyticalProgressView({ progress }: { progress: AnalyticalProgress }) {
  return <section role="status" aria-live="polite" aria-label="Analysis progress" className="space-y-3 rounded-2xl border border-border bg-surface-raised p-4 text-sm">
    <p className="font-medium">{progress.message}</p>
    <ol className="space-y-2">{progress.steps.map((step, index) => <li key={step.id} className="flex min-w-0 gap-3">
      <span aria-hidden="true" className="text-muted-foreground">{index + 1}.</span>
      <span className="min-w-0 break-words">{step.label}<span className="ml-2 text-xs text-muted-foreground">{STATUS[step.status] ?? "Waiting for results"}</span></span>
    </li>)}</ol>
    {progress.phase === "running" && <p className="text-xs text-muted-foreground">Running the linked analysis in one database snapshot. You can cancel while it runs.</p>}
  </section>;
}

function StepPeriods({ step }: { step: AnalyticalStepView }) {
  return <div className="space-y-1 break-words text-xs text-muted-foreground">
    {step.searchPeriod?.start && <p>Search period: {step.searchPeriod.start} to {step.searchPeriod.endExclusive} (end exclusive).</p>}
    {step.comparisonPeriods.map((period, index) => <p key={index}>Current: {period.currentStart} to {period.currentEnd}; baseline: {period.baselineStart} to {period.baselineEnd} (ends exclusive).</p>)}
    {step.baseline && <p>Baseline: {step.baseline.kind.replaceAll("_", " ")}. {step.baseline.origin === "approved_default" ? "Approved default." : "From the interpreted request."}</p>}
  </div>;
}

function Observations({ step, message, raw = false }: { step: AnalyticalStepView; message: ChatMessage; raw?: boolean }) {
  const result = message.meta?.analyticalExecution?.steps.find(item => item.id === step.id);
  if (!result?.rows.length) return null;
  return <div className="max-w-full overflow-x-auto rounded-lg border border-border" tabIndex={0} role="region" aria-label={`${step.title} observations`}>
    <table className="w-full text-left text-xs" aria-label={`${step.title}${raw ? step.verified ? " exact" : " unverified" : ""} data`}>
      <caption className="px-3 py-2 text-left text-xs text-muted-foreground">{raw && !step.verified ? "Returned observations — attribution is unverified. " : ""}Showing {result.rows.length} of {step.totalGroups} groups. {raw ? "" : "Display values are rounded; expand exact values for full precision."}</caption>
      <thead className="bg-muted/40"><tr>{step.columns.map(column => <th key={column.key} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">{column.label}</th>)}</tr></thead>
      <tbody>{result.rows.map((row, index) => <tr key={index} className="border-t border-border/60">{step.columns.map(column => <td key={column.key} title={row[column.key] == null ? "Unavailable, not zero" : String(row[column.key])} className="whitespace-nowrap px-3 py-2 tabular-nums">{raw ? row[column.key] == null ? "Unavailable" : String(row[column.key]) : formatAnalyticalCell(row[column.key], column)}</td>)}</tr>)}</tbody>
    </table>
  </div>;
}

export function AnalyticalAnswer({ message, chartRequested = false }: { message: ChatMessage; chartRequested?: boolean }) {
  const view = analyticalPresentation(message);
  if (!view) return <p className="text-sm">Analysis details are unavailable. Ask again with your current access.</p>;
  const usedAsInput = new Set(view.steps.flatMap(step => step.dependsOn));
  return <section aria-label="Multi-step analysis" className="min-w-0 space-y-4">
    <p className="max-w-[90ch] whitespace-pre-wrap break-words text-sm leading-relaxed">{view.summary}</p>
    <p className="text-xs text-muted-foreground">Scope: {view.scope.join(", ")}</p>
    {view.status === "partial" && <p role="status" className="rounded-lg border border-warning/50 bg-warning/10 p-3 text-sm">Partial answer. Check each step for what was verified and what could not be answered.</p>}
    {view.status === "clarification" && <p role="status" className="rounded-lg border border-warning/50 bg-warning/10 p-3 text-sm">No arbitrary winner was chosen. Narrow the selection to continue.</p>}
    {view.notes.map((note, index) => <p key={index} className="text-sm text-muted-foreground">{note}</p>)}
    <ol className="space-y-3">{view.steps.map((step, index) => {
      const result = message.meta?.analyticalExecution?.steps.find(item => item.id === step.id);
      const labels = step.columns.filter(column => ["dimension", "period_start"].includes(column.role ?? ""));
      const metric = step.columns.find(column => column.role === (step.operation === "contributors" ? "change" : step.baseline ? "current" : "value"));
      const paired = metric?.semanticId && step.baseline && step.operation !== "contributors" ? step.columns.filter(column => column.semanticId === metric.semanticId && ["current", "baseline"].includes(column.role ?? "")) : [];
      const canChart = step.verified && step.status === "completed" && labels.length === 1 && metric && (result?.rows.length ?? 0) > 1;
      const prerequisite = step.operation === "aggregate" && usedAsInput.has(step.id);
      return <li key={step.id} className="min-w-0 rounded-2xl border border-border bg-surface-raised p-4">
        <section aria-label={step.title} className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-2"><h3 className="min-w-0 break-words text-sm font-semibold"><span className="mr-2 text-muted-foreground">Step {index + 1}</span>{" "}{step.title}</h3><span className="shrink-0 rounded-full border border-border bg-muted/40 px-2 py-1 text-[11px]">{STATUS[step.status] ?? "Unavailable"}</span></div>
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{step.summary}</p>
          <StepPeriods step={step} />
          {step.filters?.length ? <p className="break-words text-xs text-muted-foreground">Filters: {step.filters.map(filter => `${filter.label} ${OPERATORS[filter.operator] ?? filter.operator.replaceAll("_", " ")} ${filter.values.join(", ")}`).join("; ")}</p> : null}
          {step.notes.length > 0 && <ul className="list-inside list-disc space-y-1 text-xs text-muted-foreground">{step.notes.map((note, item) => <li key={item}>{note}</li>)}</ul>}
          {step.verified && result?.rows.length ? prerequisite ? <details><summary className="cursor-pointer text-xs font-medium">View supporting observations</summary><div className="mt-3"><Observations step={step} message={message} /></div></details> : <Observations step={step} message={message} /> : null}
          {step.verified && result?.rows.length ? <details><summary className="cursor-pointer text-xs font-medium">View exact values — {step.title}</summary><div className="mt-3"><Observations step={step} message={message} raw /></div></details> : null}
          {!step.verified && result?.rows.length ? <p className="text-xs text-muted-foreground">Unverified observations remain in the info panel; they are not presented as contributing factors.</p> : null}
          {canChart && <details open={chartRequested || undefined}><summary className="cursor-pointer text-xs font-medium">Chart — {step.title}</summary><div className="mt-3 min-w-0"><ResultChart xKey={labels[0]!.key} yKey={metric.key} columns={[labels[0]!.key, ...(paired.length > 1 ? paired.map(column => column.key) : [metric.key])]} series={paired.length > 1 ? paired.map(column => column.key) : undefined} rows={result!.rows} hideControls hideHeading initialType={labels[0]!.kind === "date" ? "line" : "bar"} metricFormat={metric.kind === "currency" ? "currency" : undefined} /><p className="mt-2 text-xs text-muted-foreground">Charts use displayed observations for {metric.label}. Other measures remain in the table.</p></div></details>}
        </section>
      </li>;
    })}</ol>
    {view.unanswered.length > 0 && <section aria-label="Not answered" className="rounded-xl border border-warning/50 p-3"><h3 className="text-sm font-medium">Not answered</h3><ul className="mt-2 list-inside list-disc text-sm">{view.unanswered.map(item => <li key={item.id}>{item.reason}</li>)}</ul></section>}
  </section>;
}

export function AnalyticalDetails({ message }: { message: ChatMessage }) {
  const view = analyticalPresentation(message);
  const audit = message.meta?.analyticalAudit;
  if (!view && !audit) return null;
  return <section aria-label="Analysis plan and checks" className="space-y-4 text-xs">
    <h3 className="text-sm font-semibold">Plan and checks</h3>
    {view && <><p>Scope: {view.scope.join(", ")}</p><ol className="space-y-3">{view.steps.map((step, index) => <li key={step.id} className="space-y-1"><p className="font-medium">{index + 1}. {step.title} — {STATUS[step.status] ?? "Unavailable"}</p><StepPeriods step={step} />{step.dependsOn.length > 0 && <p>Uses: {step.dependsOn.map(id => view.steps.find(parent => parent.id === id)?.title ?? "Earlier step").join(", ")}</p>}{step.completenessVerified === false && <p>Loaded-period completeness is unverified.</p>}{!step.verified && <Observations step={step} message={message} raw />}</li>)}</ol>
      <div aria-label="Reconciliation checks">{view.checks.length ? view.checks.map((check, index) => <p key={index}>{check.measure?.replaceAll("_", " ") ?? "Independent reconciliation"}: {check.passed ? "Passed against independent totals" : "Not verified"}</p>) : <p>No independent reconciliation check was available or required.</p>}</div></>}
    {audit && <details><summary className="cursor-pointer font-medium">Audit references</summary><dl className="mt-2 space-y-2 break-all">{["runId", "status", "semanticVersion", "scopeFingerprint", "sqlFingerprint", "analysisDate"].map(key => <div key={key}><dt className="font-medium">{key.replace(/([A-Z])/g, " $1")}</dt><dd>{typeof audit[key] === "string" ? audit[key] : "Not available"}</dd></div>)}</dl></details>}
  </section>;
}
