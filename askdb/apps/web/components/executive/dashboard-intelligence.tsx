"use client";

import * as Dialog from "@radix-ui/react-dialog";
import type { DashboardAugmentation, DashboardExplanation, DashboardMetric } from "@nql/shared-types";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ChartNoAxesCombined, Loader2, MessageSquare, ShieldCheck, Sparkles, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { myUsageKey, quotaMessage } from "@/hooks/use-my-usage";
import { apiClient, ApiError } from "@/lib/api-client";
import { AUGMENTED_DASHBOARD_ENABLED, dashboardChange, dashboardValue } from "@/lib/executive/dashboard";
import { cn } from "@/lib/utils";

type Actions = { explain: (metricId?: string) => void; ask: (metricId?: string) => void; updating: boolean; metrics: DashboardMetric[] };
const DashboardActions = React.createContext<Actions | null>(null);
export const useDashboardActions = () => React.useContext(DashboardActions);

type Selection = { augmentation: DashboardAugmentation; metricId: string; dimension: string };

/** One shared, scoped drawer for both dashboard adapters. The charts never await it. */
export function DashboardIntelligence({ augmentation, updating = false, updateFailed = false, pendingLabel, onApplyFilters, onRefresh, children }: {
  augmentation?: DashboardAugmentation | null;
  updating?: boolean;
  updateFailed?: boolean;
  pendingLabel?: string;
  onApplyFilters: (filters: Record<string, string>) => void;
  onRefresh: () => void;
  children: React.ReactNode;
}) {
  const [active, setActive] = React.useState<Selection | null>(null);
  const [mode, setMode] = React.useState<"explain" | "ask">("explain");
  const [question, setQuestion] = React.useState("");
  const [reply, setReply] = React.useState<DashboardExplanation | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [asking, setAsking] = React.useState(false);
  const [turns, setTurns] = React.useState<Array<{ question: string; narrative: string }>>([]);
  const request = React.useRef<AbortController | null>(null);
  const opener = React.useRef<HTMLElement | null>(null);
  const queryClient = useQueryClient();
  React.useEffect(() => () => request.current?.abort(), []);

  const enabled = AUGMENTED_DASHBOARD_ENABLED && Boolean(augmentation?.metrics.length);
  const blocked = updating || updateFailed;
  const stale = Boolean(active && (blocked || active.augmentation.context.resultId !== augmentation?.context.resultId));
  const explanation = useQuery({
    queryKey: ["dashboard-explanation", active?.augmentation.context.industry, active?.augmentation.context.resultId, active?.metricId, active?.dimension],
    enabled: enabled && Boolean(active) && mode === "explain",
    queryFn: ({ signal }) => apiClient.post<DashboardExplanation>("/api/v1/executive/explain", {
      snapshotToken: active!.augmentation.snapshotToken, metricId: active!.metricId, dimension: active!.dimension,
    }, { industry: active!.augmentation.context.industry, signal }),
    staleTime: 5 * 60_000,
    gcTime: 10 * 60_000,
    retry: false,
  });

  const panelOpen = Boolean(active);
  const open = React.useCallback((metricId?: string, nextMode: "explain" | "ask" = "explain") => {
    if (!augmentation || blocked) return;
    const metric = augmentation.metrics.find((m) => m.id === metricId) ?? augmentation.metrics[0];
    if (!metric) return;
    if (!panelOpen) opener.current = document.activeElement as HTMLElement | null;
    request.current?.abort();
    setAsking(false); setError(null); setReply(null); setTurns([]); setQuestion("");
    setActive({ augmentation, metricId: metric.id, dimension: metric.dimensions[0] ?? "" });
    setMode(nextMode);
  }, [augmentation, blocked, panelOpen]);

  async function ask(text: string) {
    const q = text.trim();
    if (!active || !q || asking || stale) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setAsking(true); setError(null); setQuestion(q);
    try {
      const result = await apiClient.post<DashboardExplanation>("/api/v1/executive/ask", {
        snapshotToken: active.augmentation.snapshotToken,
        metricId: active.metricId, dimension: active.dimension,
        question: q, conversationId: reply?.conversationId ?? null,
      }, { industry: active.augmentation.context.industry, signal: controller.signal });
      if (request.current !== controller || controller.signal.aborted) return;
      setReply(result); setQuestion("");
      setTurns((previous) => [...previous.slice(-3), { question: q, narrative: result.narrative }]);
      setActive((previous) => previous ? { ...previous, metricId: result.metric.id, dimension: result.dimension } : previous);
    } catch (cause) {
      if (request.current !== controller || controller.signal.aborted) return;
      setError(cause instanceof ApiError && cause.code === "quota_exceeded"
        ? quotaMessage(cause.details)
        : cause instanceof Error ? cause.message : "The answer could not be completed. The dashboard remains available.");
    } finally {
      if (request.current === controller) { setAsking(false); request.current = null; }
      void queryClient.invalidateQueries({ queryKey: myUsageKey });
    }
  }

  const result = mode === "ask" ? reply : explanation.data;
  const metric = active?.augmentation.metrics.find((m) => m.id === active.metricId);
  const context = active?.augmentation.context;
  const actions = React.useMemo<Actions | null>(() => enabled && augmentation ? { explain: (id) => open(id), ask: (id) => open(id, "ask"), updating: blocked, metrics: augmentation.metrics } : null, [enabled, augmentation, blocked, open]);

  return (
    <DashboardActions.Provider value={actions}>
      <div className="space-y-6">
        {enabled && augmentation ? (
          <section className="rounded-2xl border border-border bg-surface-raised p-5" aria-label="Executive briefing">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-widest text-primary"><Sparkles className="size-3.5" /> Executive briefing</p>
                <h2 className="mt-1 text-lg font-semibold tracking-tight text-foreground">What changed in this view</h2>
                <p className="mt-1 text-xs text-muted-foreground">{augmentation.context.periodLabel} · Compared with {augmentation.context.compareLabel}</p>
              </div>
              <Button variant="secondary" size="sm" onClick={() => open(undefined, "ask")} disabled={blocked}><MessageSquare className="mr-1.5 size-3.5" /> Ask about this view</Button>
            </div>
            {blocked ? (
              <p role="status" className="mt-3 rounded-lg border border-warning/25 bg-warning/5 p-2.5 text-xs text-foreground">
                {updateFailed ? "Selection update failed" : `Updating ${pendingLabel ?? "your selection"}`}. Figures and briefing below still describe {augmentation.context.periodLabel}
                {Object.entries(augmentation.context.filters).length ? ` · ${Object.entries(augmentation.context.filters).map(([k, v]) => `${k}: ${v}`).join(" · ")}` : " · all permitted data"}.
              </p>
            ) : null}
            <div className="mt-4 grid gap-3 lg:grid-cols-3">
              {augmentation.highlights.slice(0, 3).map((highlight) => (
                <div key={highlight.metricId} className="flex flex-col rounded-xl border border-border/70 bg-background/40 p-3.5">
                  <p className="flex items-center gap-2 text-xs font-semibold text-foreground"><span className={cn("size-1.5 rounded-full", highlight.tone === "positive" ? "bg-success" : highlight.tone === "negative" ? "bg-warning" : "bg-primary")} />{highlight.title}</p>
                  <p className="mt-2 flex-1 text-sm leading-relaxed text-foreground">{highlight.body}</p>
                  <button type="button" onClick={() => open(highlight.metricId)} disabled={blocked} className="mt-3 inline-flex items-center gap-1 self-start text-xs font-medium text-primary hover:underline disabled:opacity-50">View evidence <ArrowRight className="size-3" /></button>
                </div>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border/60 pt-3 text-2xs text-muted-foreground">
              <span>Data as of {augmentation.context.dataAsOf} · Computed {new Date(augmentation.context.computedAt).toLocaleString("en-IN")}</span>
              <Link href="/data-quality" className="inline-flex items-center gap-1 text-primary hover:underline"><ShieldCheck className="size-3" /> Inspect Data Trust</Link>
            </div>
            {augmentation.caveats.length ? <details className="mt-3 text-2xs text-muted-foreground"><summary className="cursor-pointer">Comparison and data notes</summary><ul className="mt-2 list-disc space-y-1 pl-4">{augmentation.caveats.map((note) => <li key={note}>{note}</li>)}</ul></details> : null}
          </section>
        ) : null}
        {children}
      </div>

      <Dialog.Root open={Boolean(active) && enabled} onOpenChange={(isOpen) => { if (!isOpen) { request.current?.abort(); request.current = null; setAsking(false); setActive(null); } }}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-[80] bg-black/20" />
          <Dialog.Content className="fixed inset-y-0 right-0 z-[81] flex w-full max-w-2xl flex-col border-l border-border bg-surface-raised shadow-overlay focus:outline-none" aria-describedby="dashboard-ai-description" onCloseAutoFocus={(event) => { event.preventDefault(); opener.current?.focus(); }}>
            <div className="shrink-0 border-b border-border px-5 py-4">
              <div className="flex items-center justify-between gap-3"><Dialog.Title className="flex items-center gap-2 text-base font-semibold"><ChartNoAxesCombined className="size-4 text-primary" /> Dashboard intelligence</Dialog.Title><Dialog.Close asChild><button type="button" aria-label="Close dashboard intelligence" className="icon-btn-ghost"><X className="size-4" /></button></Dialog.Close></div>
              <Dialog.Description id="dashboard-ai-description" className="mt-1 text-xs text-muted-foreground">{context?.periodLabel} · {context?.compareLabel}. Answers use this captured view and your current data access.</Dialog.Description>
              {context ? <p className="mt-2 text-2xs text-muted-foreground">{context.start ?? "Full history"} → {context.end} · Prior: {context.priorStart ?? "Unavailable"} → {context.priorEnd ?? "Unavailable"}<br />{Object.entries(context.filters).map(([key, value]) => `${key}: ${value}`).join(" · ") || "All permitted data"}</p> : null}
            </div>
            <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4">
              {stale ? <div role="status" className="rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs"><p>The dashboard selection changed. This panel still describes its earlier captured view.</p><Button size="sm" variant="secondary" className="mt-2" disabled={blocked} onClick={() => open(active?.metricId, mode)}>Use current selection</Button></div> : null}
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant={mode === "explain" ? "primary" : "secondary"} onClick={() => setMode("explain")}>Explain this change</Button>
                <Button size="sm" variant={mode === "ask" ? "primary" : "secondary"} onClick={() => setMode("ask")}>Ask a follow-up</Button>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="text-xs font-medium">Metric<select aria-label="Explanation metric" className="mt-1 w-full rounded-lg border border-input bg-background p-2 text-sm" value={active?.metricId ?? ""} disabled={asking} onChange={(event) => {
                  const selected = active?.augmentation.metrics.find((m) => m.id === event.target.value);
                  if (active && selected) { setActive({ ...active, metricId: selected.id, dimension: selected.dimensions[0] ?? "" }); setReply(null); }
                }}>{active?.augmentation.metrics.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}</select></label>
                <label className="text-xs font-medium">Breakdown<select aria-label="Explanation breakdown" className="mt-1 w-full rounded-lg border border-input bg-background p-2 text-sm" value={active?.dimension ?? ""} disabled={asking} onChange={(event) => { if (active) { setActive({ ...active, dimension: event.target.value }); setReply(null); } }}>{metric?.dimensions.map((dim) => <option key={dim} value={dim}>{dim === "lob" ? "Line of business" : dim === "zone" ? "Region" : dim === "components" ? "Premium / claims components" : dim}</option>)}</select></label>
              </div>
              {mode === "explain" && explanation.isFetching ? <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin motion-reduce:animate-none" /> Checking the captured comparison and contributors…</p> : null}
              {mode === "explain" && explanation.error ? <div role="alert" className="rounded-lg border border-warning/30 p-3 text-sm"><p>{explanation.error.message}</p><Button size="sm" variant="secondary" className="mt-2" onClick={onRefresh}>Refresh dashboard</Button></div> : null}
              {turns.length > 0 && mode === "ask" ? <ol aria-label="Dashboard conversation" className="space-y-3">{turns.map((turn, i) => <li key={i} className="border-l-2 border-primary/30 pl-3"><p className="text-xs font-medium text-primary">{turn.question}</p>{i < turns.length - 1 ? <p className="mt-1 text-sm leading-relaxed">{turn.narrative}</p> : null}</li>)}</ol> : null}
              {result ? <Evidence result={result} disabled={stale || result.evidenceChanged} onApply={(patch) => { onApplyFilters(patch); setActive(null); }} /> : mode === "ask" ? <p className="text-sm text-muted-foreground">Ask which contributors changed, how the selected metric moved, or what its definition means. To change period or geography, use the dashboard filters.</p> : null}
              {result?.suggestedQuestions.length ? <div className="flex flex-wrap gap-2">{result.suggestedQuestions.map((q) => <button type="button" key={q} className="rounded-full border border-border px-3 py-1.5 text-xs text-primary hover:bg-muted disabled:opacity-50" disabled={asking || stale} onClick={() => { setMode("ask"); void ask(q); }}>{q}</button>)}</div> : null}
              {error ? <p role="alert" className="rounded-lg border border-warning/30 p-3 text-sm">{error}</p> : null}
            </div>
            {mode === "ask" ? <form className="shrink-0 border-t border-border bg-surface-raised p-4" onSubmit={(event) => { event.preventDefault(); void ask(question); }}>
              <label htmlFor="dashboard-question" className="text-xs font-medium">Ask about the captured view</label>
              <div className="mt-2 flex items-end gap-2"><textarea id="dashboard-question" className="min-h-20 min-w-0 flex-1 resize-none rounded-lg border border-input bg-background p-3 text-sm focus-visible:outline-ring" value={question} maxLength={2000} onChange={(event) => setQuestion(event.target.value)} disabled={stale} placeholder="Which contributors changed most?" /><Button type="submit" disabled={asking || stale || !question.trim()}>{asking ? "Checking…" : "Ask"}</Button></div>
              {asking ? <p role="status" className="mt-2 text-2xs text-muted-foreground">Resolving your question against the captured view. The dashboard remains available.</p> : <Link href="/chat" className="mt-2 inline-block text-2xs text-primary hover:underline">Open AI Chat for broader analytics</Link>}
            </form> : null}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </DashboardActions.Provider>
  );
}

function Evidence({ result, disabled, onApply }: { result: DashboardExplanation; disabled: boolean; onApply: (filters: Record<string, string>) => void }) {
  const metric = result.metric;
  return <section className="space-y-4" aria-label="Explanation evidence">
    <p className="text-sm leading-relaxed text-foreground">{result.narrative}</p>
    <div className="grid grid-cols-2 gap-3 rounded-xl border border-border bg-background/40 p-3"><div><p className="text-2xs text-muted-foreground">Current · {result.context.periodLabel}</p><p className="mt-1 text-xl font-semibold tabular-nums">{dashboardValue(metric.current, metric)}</p></div><div><p className="text-2xs text-muted-foreground">Prior · {result.context.compareLabel}</p><p className="mt-1 text-xl font-semibold tabular-nums">{dashboardValue(metric.prior, metric)}</p></div></div>
    {result.evidenceChanged ? <p role="status" className="rounded-lg border border-warning/30 p-3 text-sm">This investigation found newer totals. Refresh the dashboard before applying a contributor.</p> : null}
    {result.contributors.length ? <div className="overflow-x-auto rounded-lg border border-border"><table className="w-full text-left text-xs"><caption className="px-3 py-2 text-left font-semibold">{metric.format === "percent" ? "Loss-ratio effects · component amounts in ₹, effects in percentage points" : `Contributors by ${result.dimension}`} · {result.reconciled ? "reconciled to total change" : "review limitations"}</caption><thead className="border-y border-border bg-muted/40 text-muted-foreground"><tr><th className="p-2.5">Contributor</th><th className="p-2.5">Current</th><th className="p-2.5">Prior</th><th className="p-2.5">{metric.format === "percent" ? "Effect (pp)" : "Change"}</th><th className="p-2.5">Explore</th></tr></thead><tbody>{result.contributors.map((row) => <tr key={row.label} className="border-b border-border/50 last:border-0"><td className="p-2.5">{row.label}</td><td className="whitespace-nowrap p-2.5 tabular-nums">{dashboardValue(row.current, { format: metric.id === "loss_ratio" ? "currency" : metric.format })}</td><td className="whitespace-nowrap p-2.5 tabular-nums">{dashboardValue(row.prior, { format: metric.id === "loss_ratio" ? "currency" : metric.format })}</td><td className="whitespace-nowrap p-2.5 font-medium tabular-nums">{dashboardChange(row.change, metric)}</td><td className="p-2.5">{Object.keys(row.filters).length ? <button type="button" disabled={disabled} className="font-medium text-primary hover:underline disabled:opacity-50" onClick={() => onApply(row.filters)}>Apply filter</button> : "—"}</td></tr>)}</tbody></table></div> : null}
    <details className="rounded-lg border border-border p-3"><summary className="cursor-pointer text-xs font-semibold">Definition, data and limitations</summary><div className="mt-3 space-y-3 text-xs text-muted-foreground"><p className="break-words font-mono text-foreground">{metric.definition}</p><p>Sources: {result.sourceTables.join(", ")}</p>{result.evidenceComputedAt ? <p>Breakdown queried: {new Date(result.evidenceComputedAt).toLocaleString("en-IN")}</p> : null}<ul className="list-disc space-y-1 pl-4">{result.caveats.map((c) => <li key={c}>{c}</li>)}</ul><Link href="/data-quality" className="inline-block text-primary hover:underline">Inspect Data Trust</Link></div></details>
    {result.sql ? <details className="rounded-lg border border-border p-3"><summary className="cursor-pointer text-xs font-semibold">View underlying SQL and bindings</summary><pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words text-[11px] text-muted-foreground">{result.sql}{"\n\nParameters: "}{JSON.stringify(result.sqlParameters, null, 2)}{Object.keys(result.priorSqlParameters).length ? `\nPrior parameters: ${JSON.stringify(result.priorSqlParameters, null, 2)}` : ""}</pre></details> : null}
  </section>;
}
