"use client";

import * as React from "react";
import type { AnalyticsRunResponse, AnalyticsSpec, AnalyticsWorkspacePanel, AnalyticsWorkspacePlan, SavedAnalysis, SemanticPackResponse } from "@nql/shared-types";
import { ResultChart, type ChartKind } from "@/components/chat/result-chart";
import { ResultPreview } from "@/components/analytics-builder/analytics-builder-shell";
import { Button } from "@/components/ui/button";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { EMPTY_SPEC, useAnalyticsCapabilities } from "@/hooks/use-analytics";
import { downloadCsv } from "@/lib/analytics/helpers";
import { apiClient } from "@/lib/api-client";

type Panel = Omit<AnalyticsWorkspacePanel, "daily"> & { daily?: boolean };
type Plan = Omit<AnalyticsWorkspacePlan, "panels"> & { panels: Panel[] };
type Saved = { id: string; revision: number; plan: Plan; warning?: string | null; messages?: Array<{ question: string; answer: string }> };
type PanelState = { result?: AnalyticsRunResponse; error?: string; loading?: boolean; evidence?: string; elapsedMs?: number; queryCount?: number; scope?: string; resultSpec?: AnalyticsSpec };
type RunResponse = { result: AnalyticsRunResponse; evidence: string; elapsedMs: number; queryCount: number };
const options = { industry: "automotive" as const };
const root = "/api/v1/analytics";
const scopeOf = (panel: Panel) => JSON.stringify({ ...panel.spec, viz: undefined, daily: panel.daily ?? false });
const message = (cause: unknown) => cause instanceof Error ? cause.message : "The request could not complete. Please retry.";

export function AnalyticsWorkspace({ pack }: { pack: SemanticPackResponse }) {
  const [question, setQuestion] = React.useState("");
  const [plan, setPlan] = React.useState<Plan | null>(null);
  const [results, setResults] = React.useState<Record<string, PanelState>>({});
  const resultsRef = React.useRef(results); resultsRef.current = results;
  const [selected, setSelected] = React.useState<string | null>(null);
  const [status, setStatus] = React.useState("");
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [briefing, setBriefing] = React.useState<string[]>([]);
  const [turns, setTurns] = React.useState<Array<{ question: string; answer: string }>>([]);
  const [saved, setSaved] = React.useState<Saved[]>([]);
  const [legacy, setLegacy] = React.useState<SavedAnalysis[]>([]);
  const [legacyBoards, setLegacyBoards] = React.useState<Array<{ id: string; title: string }>>([]);
  const [identity, setIdentity] = React.useState<{ id: string; revision: number } | null>(null);
  const [usage, setUsage] = React.useState("");
  const sequence = React.useRef(0);
  const controller = React.useRef<AbortController | null>(null);
  React.useEffect(() => () => { sequence.current++; controller.current?.abort(); }, []);

  const loadSaved = React.useCallback(async () => {
    const values = await Promise.allSettled([
      apiClient.get<Saved[]>(`${root}/workspaces`, options),
      apiClient.get<SavedAnalysis[]>(`${root}/analyses`, options),
      apiClient.get<Array<{ id: string; title: string }>>(`${root}/auto/boards`, options),
    ]);
    if (values[0].status === "fulfilled") setSaved(values[0].value);
    else setError(`Saved workspaces could not load: ${message(values[0].reason)}`);
    if (values[1].status === "fulfilled") setLegacy(values[1].value);
    if (values[2].status === "fulfilled") setLegacyBoards(values[2].value);
  }, []);
  React.useEffect(() => { void loadSaved(); }, [loadSaved]);

  function start() {
    controller.current?.abort();
    controller.current = new AbortController();
    const revision = ++sequence.current;
    setError(""); setNotice(""); setBriefing([]);
    return { revision, signal: controller.current.signal };
  }
  function stop() {
    sequence.current++; controller.current?.abort(); setStatus("");
    setResults(old => Object.fromEntries(Object.entries(old).map(([id, state]) => [id, { ...state, loading: false }])));
  }

  async function runPanel(panel: Panel, revision: number, signal: AbortSignal): Promise<PanelState | null> {
    setResults(old => ({ ...old, [panel.id]: { ...old[panel.id], loading: true, error: undefined } }));
    try {
      const data = await apiClient.post<RunResponse>(`${root}/workspace/run`, { panel }, { ...options, signal });
      const state = { ...data, scope: scopeOf(panel), resultSpec: panel.spec };
      if (sequence.current !== revision) return null;
      resultsRef.current = { ...resultsRef.current, [panel.id]: state };
      setResults(old => ({ ...old, [panel.id]: state }));
      return state;
    } catch (cause) {
      if (sequence.current === revision) setResults(old => ({ ...old, [panel.id]: { ...old[panel.id], loading: false, error: message(cause) } }));
      return null;
    }
  }

  async function display(next: Plan, revision: number, signal: AbortSignal) {
    setPlan(next); setSelected(null); setStatus("Loading validated panels…");
    const facts: string[] = [];
    for (const panel of next.panels) {
      if (revision !== sequence.current) return;
      const current = Object.values(resultsRef.current).find(state => state.result && state.scope === scopeOf(panel));
      const state = current?.result && current.scope === scopeOf(panel) ? current : await runPanel(panel, revision, signal);
      if (current?.result && current.scope === scopeOf(panel)) setResults(old => ({ ...old, [panel.id]: current }));
      if (state?.evidence) facts.push(state.evidence);
    }
    if (revision !== sequence.current) return;
    setStatus(""); // Core data is ready; optional narration runs independently.
    if (facts.length) {
      try {
        const story = await apiClient.post<{ paragraphs: string[]; limitation?: string; llmCalls: number; tokens: number }>(`${root}/workspace/narration`, { evidence: facts }, { ...options, signal });
        if (revision === sequence.current) {
          setBriefing(story.limitation ? [...story.paragraphs, story.limitation] : story.paragraphs);
          setUsage(old => `${old} · Narration ${story.llmCalls ?? 0} AI calls · ${story.tokens ?? 0} tokens`);
        }
      } catch { if (revision === sequence.current) setBriefing(["AI summary is unavailable. Completed panels retain their factual summaries and evidence."]); }
    }
  }

  async function ask(event: React.FormEvent) {
    event.preventDefault(); if (!question.trim()) return;
    const { revision, signal } = start();
    const prompt = question.trim(); setStatus("Understanding your question…");
    try {
      const response = await apiClient.post<{ plan: Plan; elapsedMs: number; llmCalls: number; tokens: number }>(`${root}/workspace/plan`, { prompt, previous: plan, selectedPanelId: selected, workspaceId: identity?.id, revision: identity?.revision }, { ...options, signal });
      if (revision !== sequence.current) return;
      setUsage(`Plan ${response.elapsedMs?.toFixed(0) ?? "—"} ms · ${response.llmCalls ?? 0} AI calls · ${response.tokens ?? 0} tokens`);
      setTurns(old => [...old, { question: prompt, answer: response.plan.clarification ?? response.plan.title }]); setQuestion("");
      if (response.plan.answerKind === "clarification") { setError(response.plan.clarification ?? "Please clarify your question."); return; }
      await display(response.plan, revision, signal);
    } catch (cause) { if (revision === sequence.current) setError(message(cause)); }
    finally { if (revision === sequence.current) setStatus(""); }
  }

  async function open(id: string) {
    const { revision, signal } = start(); setStatus("Opening saved analysis…");
    try {
      let next: Plan;
      if (id.startsWith("analysis:")) {
        const item = legacy.find(row => row.id === id.slice(9)); if (!item) return;
        const spec = { ...EMPTY_SPEC, ...item.spec } as AnalyticsSpec;
        next = { answerKind: "analysis", title: item.title, clarification: null, assumptions: [], panels: [{ id: "imported", title: item.title, kind: spec.viz === "kpi" ? "kpi" : spec.viz === "table" ? "table" : spec.dimensions.length ? "chart" : "kpi", spec, rationale: "Imported saved analysis; recomputed with current permissions." }] };
        setIdentity(null);
      } else if (id.startsWith("board:")) {
        const item = await apiClient.get<{ title: string; definition: { start: string; end: string; charts: Array<{ id: string; title: string; metric: string; dimension: string; viz: AnalyticsSpec["viz"] }>; filters: Record<string, string[]> } }>(`${root}/auto/boards/${id.slice(6)}`, { ...options, signal });
        next = { answerKind: "dashboard", title: item.title, clarification: null, assumptions: [], panels: item.definition.charts.map(chart => ({ id: chart.id, title: chart.title, kind: chart.viz === "table" ? "table" : "chart", daily: chart.dimension === "day", rationale: "Imported saved dashboard; exact dates retained.", spec: { ...EMPTY_SPEC, metrics: [chart.metric], dimensions: [chart.dimension === "day" ? "month" : chart.dimension], analysis: ["day", "month"].includes(chart.dimension) ? "trend" : "top_n", viz: chart.viz, datePreset: "custom", dateFrom: item.definition.start, dateTo: item.definition.end, filters: Object.entries(item.definition.filters).map(([domain, values]) => ({ domain, values, operator: "=" })) } })) };
        setIdentity(null);
      } else {
        const item = await apiClient.get<Saved>(`${root}/workspaces/${id}`, { ...options, signal });
        if (revision !== sequence.current) return;
        next = item.plan; setIdentity({ id: item.id, revision: item.revision }); if (item.warning) setError(item.warning);
        setTurns(item.messages ?? []);
      }
      if (revision !== sequence.current) return;
      if (id.includes(":")) setTurns([]); setResults({}); resultsRef.current = {};
      await display(next, revision, signal);
    } catch (cause) { if (revision === sequence.current) setError(message(cause)); }
    finally { if (revision === sequence.current) setStatus(""); }
  }

  async function save() {
    if (!plan) return;
    try {
      const revision = sequence.current;
      const item = await apiClient.post<Saved>(`${root}/workspaces`, { plan, ...identity, messages: turns.slice(-50) }, options);
      if (revision !== sequence.current) return;
      setIdentity({ id: item.id, revision: item.revision }); setError(""); setNotice("Workspace saved."); await loadSaved();
    } catch (cause) { setError(`Could not save: ${message(cause)}`); }
  }

  function editPanel(id: string, update: Partial<Panel>) {
    if (!plan) return;
    setPlan({ ...plan, answerKind: "analysis", panels: plan.panels.map(panel => panel.id === id ? { ...panel, ...update } : panel) });
  }

  return <div className="space-y-5">
    <header className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-sm font-semibold">Automotive analysis</h2><p className="mt-1 text-sm text-muted-foreground">Automotive · Questions, evidence and dashboards in one workspace.</p></div><div className="flex flex-wrap gap-2"><label className="sr-only" htmlFor="saved-workspace">Open saved analysis</label><select id="saved-workspace" className="max-w-56 rounded-lg border border-input bg-background p-2 text-sm" value="" onChange={event => void open(event.target.value)}><option value="">Open saved…</option>{saved.map(item => <option key={item.id} value={item.id}>{item.plan.title}</option>)}{legacy.map(item => <option key={item.id} value={`analysis:${item.id}`}>{item.title} · analysis</option>)}{legacyBoards.map(item => <option key={item.id} value={`board:${item.id}`}>{item.title} · dashboard</option>)}</select><Button variant="secondary" disabled={!plan || Boolean(status)} onClick={() => void save()}>Save workspace</Button><Button variant="secondary" onClick={() => { stop(); setPlan(null); setResults({}); setTurns([]); setIdentity(null); setSelected(null); setError(""); setNotice(""); setBriefing([]); }}>New analysis</Button></div></header>
    <section className="rounded-2xl border border-border bg-surface-raised p-5" aria-label="Analytics conversation">
      {turns.length > 0 && <div className="mb-4 max-h-48 space-y-3 overflow-auto">{turns.map((turn, index) => <div key={index} className="text-sm"><p className="font-medium">{turn.question}</p><p className="text-muted-foreground">{turn.answer}</p></div>)}</div>}
      <form onSubmit={ask}><label htmlFor="analytics-question" className="text-sm font-medium">Ask Analytics{selected ? ` · Selected: ${plan?.panels.find(panel => panel.id === selected)?.title}` : " · Whole workspace"}</label><textarea id="analytics-question" className="mt-2 min-h-24 w-full rounded-xl border border-input bg-background p-3 text-sm placeholder:text-muted-foreground/70 focus-visible:outline-ring" value={question} onChange={event => setQuestion(event.target.value)} maxLength={2000} placeholder="Show daily sales last week, compare models, or build a sales dashboard…" /><div className="mt-3 flex flex-wrap gap-2"><Button type="submit" disabled={!question.trim()}>Ask</Button>{status && <Button type="button" variant="secondary" onClick={stop}>Stop</Button>}{selected && <Button type="button" variant="secondary" onClick={() => setSelected(null)}>Use whole workspace</Button>}</div></form>
      {!plan && <div className="mt-4 flex flex-wrap gap-2">{["Total sales yesterday", "Daily sales last week", "Sales by model last month", "Create an executive sales dashboard for last quarter"].map(example => <button key={example} className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:text-foreground" onClick={() => setQuestion(example)}>{example}</button>)}</div>}
      <p role="status" className="mt-3 text-sm text-muted-foreground">{status || notice}</p>{error && <p role="alert" className="mt-3 text-sm text-destructive">{error}</p>}
    </section>
    {briefing.length > 0 && <section aria-label="Report briefing" className="rounded-xl border border-border p-5"><h2 className="text-sm font-semibold">Report briefing</h2>{briefing.map((text, index) => <p key={index} className="mt-2 text-sm text-muted-foreground">{text}</p>)}</section>}
    {plan && <section aria-label="Analysis results" className="space-y-4"><h2 className="text-xl font-semibold">{plan.title}</h2>{plan.assumptions.map((item, index) => <p key={index} className="text-sm text-muted-foreground">{item}</p>)}<div className={`grid gap-4 ${plan.panels.length > 1 ? "xl:grid-cols-2" : ""}`}>{plan.panels.map(panel => <WorkspacePanel key={panel.id} panel={panel} state={results[panel.id]} selected={selected === panel.id} onSelect={() => setSelected(panel.id)} onRetry={() => { const work = start(); void runPanel(panel, work.revision, work.signal); }} onEdit={update => editPanel(panel.id, update)} onRemove={() => { const panels = plan.panels.filter(item => item.id !== panel.id); setPlan(panels.length ? { ...plan, answerKind: "analysis", panels } : null); }} />)}</div></section>}
    <StructuredEditor pack={pack} onRun={async panel => { const work = start(); const next: Plan = { answerKind: "analysis", title: panel.title, panels: plan && plan.panels.length < 6 ? [...plan.panels, panel] : [panel], assumptions: [], clarification: null }; await display(next, work.revision, work.signal); }} />
    {usage && <details className="text-xs text-muted-foreground"><summary>Processing details</summary><p className="mt-2">{usage}</p>{plan?.panels.map(panel => <p key={panel.id}>{panel.title}: {results[panel.id]?.elapsedMs?.toFixed(0) ?? "—"} ms · {results[panel.id]?.queryCount ?? "—"} database calls</p>)}</details>}
  </div>;
}

export function WorkspacePanel({ panel, state, selected, onSelect, onRetry, onEdit, onRemove }: { panel: Panel; state?: PanelState; selected: boolean; onSelect: () => void; onRetry: () => void; onEdit: (update: Partial<Panel>) => void; onRemove: () => void }) {
  const [table, setTable] = React.useState(false);
  const result = state?.result;
  const current = state?.scope === scopeOf(panel);
  const chart = result?.chart;
  const format = (value: unknown) => value == null ? "—" : typeof value === "number" ? new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, ...(result?.meta.metricFormat === "currency" ? { style: "currency", currency: "INR" } : {}) }).format(value) : String(value);
  return <article className={`min-w-0 rounded-2xl border bg-surface-raised p-5 ${selected ? "border-primary" : "border-border"}`}>
    <div className="flex flex-wrap justify-between gap-2"><h3 className="font-semibold">{panel.title}</h3><div className="flex flex-wrap gap-3 text-xs"><button className="focus-visible:outline-ring" onClick={onSelect} aria-pressed={selected}>Refine</button><button onClick={() => setTable(value => !value)}>Chart / data</button><button onClick={onRemove}>Remove</button></div></div>
    <p className="mt-1 text-xs text-muted-foreground">{panel.spec.dateFrom ?? panel.spec.datePreset ?? "All available dates"}{panel.spec.dateTo ? ` to ${panel.spec.dateTo}` : ""} · {panel.spec.metrics.join(", ")}{panel.spec.filters.map(filter => ` · ${filter.domain}: ${filter.values.join(", ")}`)}</p>
    <p role="status" className="mt-2 text-xs text-muted-foreground">{state?.loading ? result ? "Updating — previous scope result shown below" : "Loading…" : result && !current ? "Previous result — refresh to apply this definition" : ""}</p>
    {result && !current && <p className="mt-2 text-xs text-muted-foreground">Result shown: {state?.resultSpec?.metrics.join(", ") ?? result.title} · {state?.resultSpec?.dateFrom ?? String(result.meta.dateLabel ?? "previous selection")} to {state?.resultSpec?.dateTo ?? "latest available"}{state?.resultSpec?.filters.map(filter => ` · ${filter.domain}: ${filter.values.join(", ")}`)}</p>}
    {state?.error && <p role="alert" className="mt-2 text-sm text-destructive">{state.error}</p>}{(!result || state?.error || !current) && <Button size="sm" variant="secondary" className="mt-2" disabled={state?.loading} onClick={onRetry}>Retry panel</Button>}
    {result && (result.rows.length === 0 ? <p className="py-12 text-sm text-muted-foreground">No data matches this scope. This is not a zero result.</p> : panel.kind === "kpi" && !table ? <div className="py-8 text-3xl font-semibold">{panel.spec.metrics.map(metric => { const column = result.columns.includes(metric) ? metric : String(result.meta.valueColumn ?? result.columns[0]); const value = result.rows[0]?.[column]; return <div key={metric}><span className="block text-xs font-normal text-muted-foreground">{metric.replaceAll("_", " ")}</span>{typeof value === "number" ? <AnimatedNumber value={value} format={format} /> : format(value)}</div>; })}</div> : !table && panel.kind === "chart" && chart ? (["heatmap", "treemap"].includes(panel.spec.viz) ? <ResultPreview result={result} viz={panel.spec.viz} tab="chart" filterLabel={null} /> : <ResultChart key={`${panel.id}-${panel.spec.viz}-${panel.daily}`} rows={chart.points} columns={result.columns} xKey={chart.x} yKey={chart.y} series={chart.series} initialType={( ["bar", "line", "area", "pie", "scatter"].includes(panel.spec.viz) ? panel.spec.viz : ["bar", "line", "area", "pie", "scatter"].includes(chart.type) ? chart.type : "bar") as ChartKind} hideTypeSelect hideControls />) : <div className="mt-4 overflow-auto"><table className="w-full text-left text-xs"><caption className="sr-only">{panel.title} underlying data</caption><thead><tr>{result.columns.map(column => <th className="p-2" key={column}>{column}</th>)}</tr></thead><tbody>{result.rows.map((row, index) => <tr key={index}>{result.columns.map(column => <td key={column} className="border-t border-border p-2">{format(row[column])}</td>)}</tr>)}</tbody></table></div>)}
    {panel.spec.dimensions.length > 0 && <label className="mt-3 block text-xs">Visualization<select aria-label={`${panel.title} visualization`} className="ml-2 rounded border border-input bg-background p-1" value={panel.spec.viz} onChange={event => { const viz = event.target.value as AnalyticsSpec["viz"]; onEdit({ kind: viz === "table" ? "table" : "chart", spec: { ...panel.spec, viz } }); }}>{["auto", "bar", "line", "area", "pie", "donut", "scatter", "heatmap", "treemap", "table"].map(viz => <option key={viz}>{viz}</option>)}</select></label>}
    {result?.insights && <p className="mt-4 text-sm text-muted-foreground">{result.insights.executive}</p>}
    <details className="mt-4 text-xs"><summary className="cursor-pointer">Definition and evidence</summary><p className="mt-2">{panel.rationale}</p>{result && <><p className="mt-2">Data as of: {String(result.meta.dataAsOf ?? "Unknown")}</p>{[...(Array.isArray(result.meta.notes) ? result.meta.notes : []), ...(Array.isArray(result.meta.warnings) ? result.meta.warnings : [])].map((note, index) => <p className="mt-1" key={index}>{String(note)}</p>)}<Button size="sm" variant="secondary" className="mt-2" onClick={() => downloadCsv(`${panel.title}.csv`, result.columns, result.rows)}>Export CSV</Button><details className="mt-3"><summary>Governed SQL</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap">{result.sql}</pre></details></>}<pre className="mt-2 overflow-auto whitespace-pre-wrap">{JSON.stringify(panel.spec, null, 2)}</pre><a className="text-primary underline" href="/data-quality">Open Data Trust</a></details>
  </article>;
}

function StructuredEditor({ onRun }: { pack: SemanticPackResponse; onRun: (panel: Panel) => Promise<void> }) {
  const caps = useAnalyticsCapabilities();
  const [spec, setSpec] = React.useState<AnalyticsSpec>({ ...EMPTY_SPEC });

  const [error, setError] = React.useState("");
  return <details className="rounded-xl border border-border p-4"><summary className="cursor-pointer text-sm font-medium">Add a panel using fields</summary><p className="mt-2 text-xs text-muted-foreground">Use the same governed metrics and analysis capabilities with precise settings.</p><form className="mt-4 grid gap-3 md:grid-cols-2" onSubmit={event => { event.preventDefault(); try { setError(""); void onRun({ id: crypto.randomUUID(), title: spec.metrics.join(", ").replaceAll("_", " "), kind: spec.viz === "table" ? "table" : spec.dimensions.length ? "chart" : "kpi", rationale: "Selected using governed analytics fields.", spec }).catch(cause => setError(message(cause))); } catch (cause) { setError(message(cause)); } }}>
    <label className="text-xs">Metrics<select multiple className="mt-1 block w-full rounded border border-input bg-background p-2" value={spec.metrics} onChange={event => setSpec({ ...spec, metrics: Array.from(event.target.selectedOptions, option => option.value) })}>{caps.data?.metrics.filter(metric => metric.supported).map(metric => <option key={metric.id} value={metric.id}>{metric.label}</option>)}</select></label>
    <label className="text-xs">Dimensions<select multiple className="mt-1 block w-full rounded border border-input bg-background p-2" value={spec.dimensions} onChange={event => setSpec({ ...spec, dimensions: Array.from(event.target.selectedOptions, option => option.value) })}>{caps.data?.dimensions.map(dimension => <option key={dimension.id} value={dimension.id}>{dimension.label}</option>)}</select></label>
    <label className="text-xs">Analysis<select className="mt-1 block w-full rounded border border-input bg-background p-2" value={spec.analysis} onChange={event => setSpec({ ...spec, analysis: event.target.value as AnalyticsSpec["analysis"] })}>{caps.data?.analyses.map(analysis => <option key={analysis.id} value={analysis.id}>{analysis.label}</option>)}</select></label>
    <label className="text-xs">Period<select className="mt-1 block w-full rounded border border-input bg-background p-2" value={spec.datePreset ?? ""} onChange={event => setSpec({ ...spec, datePreset: event.target.value || null })}><option value="">All available dates</option>{caps.data?.datePresets.map(period => <option key={period.id} value={period.id}>{period.label}</option>)}</select></label>
    <label className="text-xs">Start date<input type="date" className="mt-1 block rounded border border-input bg-background p-2" value={spec.dateFrom ?? ""} onChange={event => setSpec({ ...spec, datePreset: "custom", dateFrom: event.target.value })} /></label><label className="text-xs">End date<input type="date" className="mt-1 block rounded border border-input bg-background p-2" value={spec.dateTo ?? ""} onChange={event => setSpec({ ...spec, datePreset: "custom", dateTo: event.target.value })} /></label>
    <label className="text-xs">Limit<input type="number" min={1} max={500} className="ml-2 rounded border border-input bg-background p-2" value={spec.limit} onChange={event => setSpec({ ...spec, limit: Number(event.target.value) })} /></label><label className="text-xs">Moving window<input type="number" min={2} max={24} className="ml-2 rounded border border-input bg-background p-2" value={spec.window} onChange={event => setSpec({ ...spec, window: Number(event.target.value) })} /></label>
    <label className="text-xs">Ranking<select value={spec.rankMethod} onChange={event => setSpec({ ...spec, rankMethod: event.target.value as AnalyticsSpec["rankMethod"] })}>{["rank", "dense_rank", "row_number"].map(item => <option key={item}>{item}</option>)}</select></label><label className="text-xs">Sort<select value={spec.orderDirection} onChange={event => setSpec({ ...spec, orderDirection: event.target.value as "asc" | "desc" })}><option>desc</option><option>asc</option></select></label>
    <FilterEditor domains={caps.data?.filterDomains ?? []} filters={spec.filters} onChange={filters => setSpec({ ...spec, filters })} /><Button type="submit" disabled={!spec.metrics.length}>Add and run panel</Button>{error && <p role="alert" className="text-sm text-destructive">{error}</p>}
  </form></details>;
}

function FilterEditor({ domains, filters, onChange }: { domains: Array<{ id: string; label: string }>; filters: AnalyticsSpec["filters"]; onChange: (filters: AnalyticsSpec["filters"]) => void }) {
  const [domain, setDomain] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [choices, setChoices] = React.useState<string[]>([]);
  const [selected, setSelected] = React.useState<string[]>([]);
  const [error, setError] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  React.useEffect(() => {
    if (!domain) return;
    const abort = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true); setError("");
      void apiClient.get<{ values: Array<{ value: string }> }>(`${root}/filter-values?domain=${encodeURIComponent(domain)}&q=${encodeURIComponent(query)}`, { ...options, signal: abort.signal }).then(data => { if (!abort.signal.aborted) setChoices(data.values.map(item => item.value)); }).catch(cause => { if (!abort.signal.aborted) setError(message(cause)); }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    }, 200);
    return () => { window.clearTimeout(timer); abort.abort(); };
  }, [domain, query]);
  return <fieldset className="space-y-2 rounded-xl border border-border p-3 md:col-span-2"><legend className="px-1 text-xs font-medium">Filters</legend>{filters.map(filter => <div key={filter.domain} className="flex flex-wrap items-center gap-2 text-xs"><span>{filter.domain}: {filter.values.join(", ")}</span><button type="button" onClick={() => onChange(filters.filter(item => item.domain !== filter.domain))}>Remove {filter.domain} filter</button></div>)}<div className="grid gap-2 md:grid-cols-2"><label className="text-xs">Filter by<select className="mt-1 block w-full rounded border border-input bg-background p-2" value={domain} onChange={event => { setDomain(event.target.value); setSelected([]); setChoices([]); }}><option value="">Choose a field</option>{domains.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>{domain && <><label className="text-xs">Search values<input className="mt-1 block w-full rounded border border-input bg-background p-2" value={query} onChange={event => setQuery(event.target.value)} /></label><label className="text-xs md:col-span-2">Available values<select multiple className="mt-1 block w-full rounded border border-input bg-background p-2" value={selected} onChange={event => setSelected(Array.from(event.target.selectedOptions, item => item.value))}>{choices.map(value => <option key={value}>{value}</option>)}</select></label><Button type="button" variant="secondary" disabled={!selected.length || loading} onClick={() => { onChange([...filters.filter(item => item.domain !== domain), { domain, values: selected, operator: "=" }]); setDomain(""); }}>Apply filter</Button></>}</div>{loading && <p role="status" className="text-xs text-muted-foreground">Loading available values…</p>}{error && <p role="alert" className="text-xs text-destructive">{error}</p>}</fieldset>;
}
