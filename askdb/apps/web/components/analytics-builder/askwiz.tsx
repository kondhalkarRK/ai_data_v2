"use client";

import type { AskWizBoard, AskWizChart, AskWizChartResult, AskWizNarration, AskWizResults } from "@nql/shared-types";
import { useQuery } from "@tanstack/react-query";
import { ArrowUp, BarChart3, Check, Download, Loader2, MessageSquare, RefreshCw, Save, Sparkles, Undo2 } from "lucide-react";
import * as React from "react";

import { ResultChart } from "@/components/chat/result-chart";
import { Button } from "@/components/ui/button";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { useSession } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";
import { downloadCsv, formatCell } from "@/lib/analytics/helpers";

const ROOT = "/api/v1/analytics/auto";
const STARTERS = [
  { id: "weekly", title: "Last week, explained", description: "Daily sales, units, regions and leading models", prompt: "Generate a report of last week on daily sales" },
  { id: "sales", title: "The sales overview", description: "Four useful views of this month’s performance", prompt: "Create four charts showing sales performance this month" },
  { id: "models", title: "Make & model performance", description: "Revenue, volume and average selling price", prompt: "Show model performance this month" },
  { id: "regions", title: "Where sales happen", description: "Compare permitted regions, states and cities", prompt: "Show regional sales performance this month" },
  { id: "growth", title: "Sales comparison", description: "Sales charts with aligned prior-period KPI totals", prompt: "Compare sales this week with the same elapsed days last week" },
];

export function AskWiz() {
  const { data: user } = useSession();
  const [board, setBoard] = React.useState<AskWizBoard | null>(null);
  const [results, setResults] = React.useState<AskWizResults | null>(null);
  const [loadedBoard, setLoadedBoard] = React.useState<AskWizBoard | null>(null);
  const [narration, setNarration] = React.useState<AskWizNarration | null>(null);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [prompt, setPrompt] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [narrating, setNarrating] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [turns, setTurns] = React.useState<Array<{ question: string; answer: string }>>([]);
  const [panel, setPanel] = React.useState(true);
  const [modelCalls, setModelCalls] = React.useState(0);
  const [operationTokens, setOperationTokens] = React.useState(0);
  const [usageUnknown, setUsageUnknown] = React.useState(false);
  const controller = React.useRef<AbortController | null>(null);
  const requestId = React.useRef(0);
  const saved = useQuery({ queryKey: ["askwiz-saved", user?.id, user?.role, user?.regionAccess], queryFn: () => apiClient.get<AskWizBoard[]>(`${ROOT}/boards`, { industry: "automotive" }), retry: false });
  const templates = useQuery({ queryKey: ["askwiz-templates"], queryFn: () => apiClient.get<{ templates: Array<{ id: string }> }>(`${ROOT}/templates`, { industry: "automotive" }), retry: false });
  React.useEffect(() => () => { controller.current?.abort(); requestId.current += 1; }, []);

  async function work({ recipe, action, open }: { recipe?: string; action?: string; open?: string } = {}) {
    if (status) return;
    controller.current?.abort();
    const current = new AbortController(); controller.current = current;
    const id = ++requestId.current;
    const options = { industry: "automotive" as const, signal: current.signal };
    const valid = () => requestId.current === id && !current.signal.aborted;
    const question = recipe ? STARTERS.find((item) => item.id === recipe)?.prompt ?? recipe : prompt.trim();
    setError(null); setNarrating(false); setUsageUnknown(false);
    setStatus(open ? "Opening saved specification…" : action ? "Validating board change…" : recipe ? "Validating KPI recipe…" : "Understanding your report request…");
    try {
      const next = open
        ? await apiClient.get<AskWizBoard>(`${ROOT}/boards/${open}`, options)
        : board && !recipe
          ? await apiClient.post<AskWizBoard>(`${ROOT}/boards/${board.id}/commands`, { revision: board.revision, prompt: question, selectedChartId: selected, action: action ?? "edit" }, options)
          : await apiClient.post<AskWizBoard>(`${ROOT}/boards`, { prompt: question, recipe: recipe ?? null }, options);
      if (!valid()) return;
      setBoard(next); setPrompt(""); setModelCalls(next.llmCalls); setOperationTokens(next.tokens);
      if (question) setTurns((old) => [...old.slice(-5), { question, answer: next.message }]);
      if (action === "save") { setStatus(""); void saved.refetch(); return; }
      if (selected && !next.definition.charts.some((chart) => chart.id === selected)) setSelected(null);
      setStatus("Running validated sales analyses…");
      const data = await apiClient.post<AskWizResults>(`${ROOT}/boards/${next.id}/run`, { revision: next.revision, action: action === "refresh" ? "refresh" : "retry" }, options);
      if (!valid()) return;
      setResults(data); setLoadedBoard(next); setNarration(null); setStatus("");
      setNarrating(true);
      try {
        const story = await apiClient.post<AskWizNarration>(`${ROOT}/boards/${next.id}/narration`, { revision: next.revision }, options);
        if (valid()) { setNarration(story); setModelCalls(next.llmCalls + story.llmCalls); setOperationTokens(next.tokens + story.tokens); }
      } catch {
        if (valid()) setUsageUnknown(true);
        if (valid()) setNarration({ revision: next.revision, paragraphs: [], aiUsed: false, llmCalls: 0, tokens: 0, limitation: "AI narration could not be loaded. Charts and underlying evidence remain available." });
      } finally { if (valid()) setNarrating(false); }
    } catch (cause) {
      if (valid()) setUsageUnknown(true);
      if (valid()) { setError(cause instanceof Error ? cause.message : "The request could not be completed."); setStatus(""); }
    }
  }

  const current = board && results?.boardId === board.id && results.revision === board.revision;
  const displayedBoard = current ? board : loadedBoard ?? board;
  const currentKpi = results?.kpis.find((item) => item.chartId === "current")?.result;
  const priorKpi = results?.kpis.find((item) => item.chartId === "prior")?.result;
  const available = new Set(templates.data?.templates.map((item) => item.id));
  const scope = board?.definition;

  return <div className="space-y-5">
    <section className="rounded-2xl border border-primary/20 bg-surface-raised p-6">
      <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-primary"><Sparkles className="size-4" /> AskWiz · Automotive</p>
      <h2 className="mt-2 text-2xl font-semibold tracking-tight">Your question. A clearer sales story.</h2>
      <p className="mt-2 max-w-3xl text-sm text-muted-foreground">Turn questions into dashboards in minutes with AskWiz—no dragging or guesswork.</p>
      <div className="mt-5 flex flex-wrap gap-2">{STARTERS.filter((item) => available.has(item.id)).map((item) => <button type="button" key={item.id} title={item.description} disabled={Boolean(status)} onClick={() => void work({ recipe: item.id })} className="rounded-xl border border-border bg-background/60 px-3 py-2 text-left text-xs font-medium hover:border-primary/50 focus-visible:outline-ring disabled:opacity-50">{item.title}</button>)}</div>
      {templates.error ? <p role="alert" className="mt-3 text-xs text-warning">{templates.error.message}</p> : null}
    </section>

    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h3 className="text-lg font-semibold">{board?.title ?? "Start with a business question"}</h3>{scope ? <p className="mt-1 text-xs text-muted-foreground">{scope.start} → {scope.end} · {scope.timezone} · Prior {scope.priorStart} → {scope.priorEnd}<br />{Object.entries(scope.filters).map(([key, values]) => `${key}: ${values.join(", ")}`).join(" · ") || "All data permitted by your access"}</p> : null}</div>
      <div className="flex flex-wrap gap-2">
        {board ? <Button size="sm" variant="secondary" disabled={Boolean(status)} onClick={() => { controller.current?.abort(); requestId.current += 1; setBoard(null); setResults(null); setLoadedBoard(null); setNarration(null); setNarrating(false); setTurns([]); setSelected(null); setError(null); setPrompt(""); }}>New report</Button> : null}
        {board ? <><Button size="sm" variant="secondary" disabled={Boolean(status) || !board.canUndo} onClick={() => void work({ action: "undo" })}><Undo2 className="mr-1 size-3.5" /> Undo</Button><Button size="sm" variant="secondary" disabled={Boolean(status)} onClick={() => void work({ action: "refresh" })}><RefreshCw className="mr-1 size-3.5" /> Refresh</Button><Button size="sm" variant="secondary" disabled={Boolean(status)} onClick={() => void work({ action: "save" })}>{board.saved ? <Check className="mr-1 size-3.5" /> : <Save className="mr-1 size-3.5" />} Save</Button></> : null}
        <Button size="sm" variant="secondary" aria-expanded={panel} onClick={() => setPanel(!panel)}><MessageSquare className="mr-1 size-3.5" /> AskChart</Button>
      </div>
    </div>
    {saved.data?.length ? <label className="block text-xs text-muted-foreground">Saved automotive boards<select aria-label="Open saved automotive board" value="" disabled={Boolean(status)} className="ml-2 max-w-full rounded-lg border border-input bg-background p-2 text-foreground" onChange={(event) => { if (event.target.value) void work({ open: event.target.value }); }}><option value="">Choose a saved report</option>{saved.data.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.definition.start}</option>)}</select></label> : null}
    <div className={`grid items-start gap-5 ${panel ? "xl:grid-cols-[minmax(0,1fr)_340px]" : ""}`}>
      <div className="min-w-0 space-y-5">
        {status ? <p role="status" className="flex items-center gap-2 rounded-xl border border-primary/25 bg-primary/5 p-3 text-sm"><Loader2 className="size-4 animate-spin motion-reduce:animate-none" />{status}{results ? " Previous figures remain below until the updated board is ready." : ""}</p> : null}
        {error ? <div role="alert" className="rounded-xl border border-warning/30 p-3 text-sm">{error} {board ? <button type="button" className="ml-2 text-primary underline" onClick={() => void work({ open: board.id })}>Reload current board</button> : null}</div> : null}
        {results && !current ? <p role="status" className="rounded-xl border border-warning/30 p-3 text-xs">Previous results · computed {new Date(results.computedAt).toLocaleString("en-IN")}. The displayed figures are from revision {results.revision}; they do not yet describe the current selection above.</p> : null}
        {currentKpi ? <div className="grid gap-3 sm:grid-cols-3">{currentKpi.columns.map((column) => {
          const value = Number(currentKpi.rows[0]?.[column]);
          const prior = priorKpi?.rows[0]?.[column];
          return <div key={column} className="rounded-xl border border-border bg-surface-raised p-4"><p className="text-xs text-muted-foreground">{column.replaceAll("_", " ")}</p><p className="mt-2 text-2xl font-semibold tabular-nums"><AnimatedNumber value={Number.isFinite(value) && currentKpi.rows[0]?.[column] != null ? value : null} format={(n) => formatCell(n, column, column.includes("revenue") ? "currency" : "integer")} /></p><p className="mt-2 text-xs text-muted-foreground">Prior: {prior == null ? "Unavailable" : formatCell(prior, column, column.includes("revenue") ? "currency" : "integer")}</p></div>;
        })}</div> : null}
        {current && (narrating || narration) ? <section aria-label="Report briefing" className="rounded-xl border border-border bg-surface-raised p-4"><p className="flex items-center gap-2 text-xs font-semibold text-primary"><Sparkles className="size-3.5" />{narration?.aiUsed ? "AI-curated briefing" : "Report briefing"}</p>{narrating ? <p role="status" className="mt-2 text-xs text-muted-foreground">Composing narration from the returned evidence. Your charts are ready.</p> : <><div className="mt-3 space-y-2">{narration?.paragraphs.map((text, index) => <p key={index} className="whitespace-pre-line text-sm leading-relaxed">{text}</p>)}</div>{narration?.limitation ? <p className="mt-3 text-xs text-muted-foreground">{narration.limitation}</p> : null}</>}</section> : null}
        {displayedBoard ? <div className="grid gap-4 lg:grid-cols-2">{displayedBoard.definition.charts.map((chart, index) => <ChartPanel key={chart.id} chart={chart} index={index} data={results?.charts.find((item) => item.chartId === chart.id)} selected={selected === chart.id} disabled={Boolean(status) || !current} onSelect={() => { setSelected(chart.id); setPanel(true); }} onRetry={() => void work({ action: "retry" })} />)}</div> : <div className="flex min-h-72 flex-col items-center justify-center rounded-2xl border border-dashed border-border p-8 text-center"><BarChart3 className="size-9 text-primary/60" /><p className="mt-4 font-medium">A useful dashboard starts with your question</p><p className="mt-2 max-w-md text-sm text-muted-foreground">Try “Generate last week’s daily sales report.” AskWiz uses governed automotive KPIs and builds up to six charts.</p></div>}
        {results ? <p className="text-[11px] text-muted-foreground">Revision {results.revision} · {results.elapsedMs.toFixed(0)} ms API execution · {results.queryCount} application SQL calls · {results.cacheHits} cached results · {usageUnknown ? "AI usage unavailable for the failed request" : `${modelCalls} AI completion attempts · ${operationTokens} tokens in latest operation`}. Data freshness is shown per chart; cache may be up to five minutes old.</p> : null}
      </div>

      {panel ? <aside aria-label="AskChart conversation" className="order-first min-w-0 rounded-2xl border border-border bg-surface-raised xl:sticky xl:top-4 xl:order-last">
        <div className="border-b border-border p-4"><h3 className="flex items-center gap-2 font-semibold"><MessageSquare className="size-4 text-primary" /> AskChart</h3><p className="mt-1 text-xs text-muted-foreground">{selected ? `Editing: ${board?.definition.charts.find((chart) => chart.id === selected)?.title}` : "Create a report or select a chart to refine it."}</p>{selected ? <button type="button" className="mt-2 text-xs text-primary underline" onClick={() => setSelected(null)}>Clear chart selection</button> : null}</div>
        <div className="max-h-72 space-y-4 overflow-y-auto p-4" aria-live="polite">{turns.length ? turns.map((turn, index) => <div key={index}><p className="rounded-lg bg-primary/10 p-2.5 text-sm">{turn.question}</p><p className="mt-2 text-xs leading-relaxed text-muted-foreground">{turn.answer}</p></div>) : <p className="text-sm leading-relaxed text-muted-foreground">Ask for a weekly report, four charts, or a model breakdown. Then refine the board: “Make chart two a bar chart.”</p>}</div>
        <form className="border-t border-border p-4" onSubmit={(event) => { event.preventDefault(); if (prompt.trim()) void work(); }}><label htmlFor="askchart-question" className="text-xs font-medium">{board ? "Refine this dashboard" : "What would you like to understand?"}</label><textarea id="askchart-question" value={prompt} maxLength={2000} onChange={(event) => setPrompt(event.target.value)} className="mt-2 min-h-28 w-full resize-y rounded-xl border border-input bg-background p-3 text-sm focus-visible:outline-ring" placeholder={board ? "Change chart two to an area chart…" : "Generate last week’s report on daily sales…"} /><Button type="submit" className="mt-2 w-full" disabled={Boolean(status) || !prompt.trim()}><ArrowUp className="mr-2 size-4" />{board ? "Update dashboard" : "Create dashboard"}</Button><p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">Automotive only · read-only analytics · predefined KPI calculations. Exact periods and permissions are validated on the server.</p></form>
      </aside> : null}
    </div>
  </div>;
}

function ChartPanel({ chart, index, data, selected, disabled, onSelect, onRetry }: { chart: AskWizChart; index: number; data?: AskWizChartResult; selected: boolean; disabled: boolean; onSelect: () => void; onRetry: () => void }) {
  const result = data?.result;
  return <section aria-label={`Chart ${index + 1}: ${chart.title}`} className={`min-w-0 rounded-2xl border bg-surface-raised p-4 ${selected ? "border-primary ring-1 ring-primary/20" : "border-border"}`}>
    <div className="flex items-start justify-between gap-3"><div><p className="text-[10px] uppercase tracking-widest text-muted-foreground">Chart {index + 1}</p><h4 className="mt-1 text-sm font-semibold">{chart.title}</h4></div><button type="button" disabled={disabled} aria-pressed={selected} onClick={onSelect} className="shrink-0 rounded-lg border border-border px-2 py-1 text-xs text-primary focus-visible:outline-ring disabled:opacity-50">AskChart</button></div>
    {!data ? <p className="py-16 text-center text-sm text-muted-foreground">Waiting for this revision’s results…</p> : data.error ? <div role="alert" className="py-8 text-sm"><p>{data.error}</p><Button size="sm" variant="secondary" className="mt-3" disabled={disabled} onClick={onRetry}>Retry failed charts</Button></div> : result ? <>
      {!result.rows.length ? <p className="py-12 text-sm text-muted-foreground">No data matches these dates and filters. This is not a zero result.</p> : chart.viz !== "table" && result.chart ? <ResultChart key={`${chart.id}-${chart.viz}`} rows={result.chart.points} columns={Object.keys(result.chart.points[0] ?? {})} xKey={result.chart.x} yKey={result.chart.y} series={result.chart.series} initialType={chart.viz} hideTypeSelect hideControls className="mt-4" /> : null}
      <p className="mt-3 text-[11px] text-muted-foreground">Data through {String(result.meta.dataAsOf ?? "unknown")} · {data.cacheHit ? "Cached result" : "Queried result"}{result.meta.partialPeriod ? " · Partial period / incomplete coverage" : ""}</p>
      <details open={chart.viz === "table"} className="mt-3 text-xs"><summary className="cursor-pointer font-medium text-primary">Inspect data & evidence</summary><div className="mt-3 overflow-x-auto"><table className="w-full text-left"><caption className="sr-only">{chart.title} underlying data</caption><thead><tr>{result.columns.map((column) => <th key={column} className="border-b border-border p-2">{column.replaceAll("_", " ")}</th>)}</tr></thead><tbody>{result.rows.map((row, i) => <tr key={i}>{result.columns.map((column) => <td key={column} className="whitespace-nowrap border-b border-border/40 p-2">{formatCell(row[column], column, String(result.meta.metricFormat ?? ""))}</td>)}</tr>)}</tbody></table></div><Button size="sm" variant="secondary" className="mt-3" onClick={() => downloadCsv(`${chart.title}.csv`, result.columns, result.rows)}><Download className="mr-1 size-3" /> Export CSV</Button><p className="mt-3 whitespace-pre-line leading-relaxed text-muted-foreground">{result.insights?.analyst}</p><ul className="mt-2 list-disc pl-4 text-muted-foreground">{[...(Array.isArray(result.meta.notes) ? result.meta.notes : []), ...(Array.isArray(result.meta.warnings) ? result.meta.warnings : [])].map((note, i) => <li key={i}>{String(note)}</li>)}</ul><details className="mt-3"><summary className="cursor-pointer">Underlying governed SQL</summary><pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-words text-[10px] text-muted-foreground">{result.sql}</pre></details></details>
    </> : null}
  </section>;
}
