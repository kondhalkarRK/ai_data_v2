"use client";

import * as React from "react";
import type { AnalyticsRunResponse, AnalyticsSpec, BiPanel, BiReport, BiTurn, BiUsage } from "@nql/shared-types";
import { apiClient, ApiError } from "@/lib/api-client";

export const BI_ROOT = "/api/v1/analytics/bi";
const options = { industry: "automotive" as const };
type RunResult = { result: AnalyticsRunResponse; evidence: string; queryCount: number; elapsedMs: number };
export type PanelResult = Partial<RunResult> & { scope?: string; resultSpec?: AnalyticsSpec; error?: string; loading?: boolean; revision?: number; loadedAt?: string };
export type ReportAction = "ask" | "save" | "undo" | "refresh" | "remove" | "move_up" | "move_down" | "visualize" | "rename";
export type SavedOption = { id: string; title: string; source?: "analysis" | "board" | "workspace" };
export type Capability = { enabled: boolean; engine: string; schemaVersion: number; advancedEnabled: boolean; migration: string };
const failure = (error: unknown) => error instanceof ApiError ? `${error.message}${error.requestId && error.requestId !== "-" ? ` (reference ${error.requestId})` : ""}` : error instanceof Error ? error.message : "The request failed. Please retry.";
export const panelScope = (panel: BiPanel) => JSON.stringify({ ...panel.spec, viz: undefined, grain: panel.grain ?? null, daily: panel.daily ?? false, calculation: panel.calculation ?? null });
// The reused renderer expects the original workspace scope encoding.
export const rendererScope = (panel: BiPanel) => JSON.stringify({ ...panel.spec, viz: undefined, daily: panel.daily ?? false });

export function useAskBI() {
  const [capability, setCapability] = React.useState<Capability | null>(null);
  const [report, setReport] = React.useState<BiReport | null>(null);
  const [results, setResults] = React.useState<Record<string, PanelResult>>({});
  const [selected, setSelected] = React.useState<string | null>(null);
  const [status, setStatus] = React.useState("");
  const [error, setError] = React.useState("");
  const [briefing, setBriefing] = React.useState<string[]>([]);
  const [narrationUsage, setNarrationUsage] = React.useState<BiUsage | null>(null);
  const [localTurns, setLocalTurns] = React.useState<BiTurn[]>([]);
  const [saved, setSaved] = React.useState<SavedOption[]>([]);
  const [saveError, setSaveError] = React.useState("");
  const [capabilityError, setCapabilityError] = React.useState("");
  const resultsRef = React.useRef(results);
  const reportRef = React.useRef(report);
  const sequence = React.useRef(0);
  const controller = React.useRef<AbortController | null>(null);
  const locked = React.useRef(false);
  const needsSync = React.useRef(false);
  const lastRequest = React.useRef<{ id: string; body: object } | null>(null);
  const setCurrent = (next: BiReport | null) => { reportRef.current = next; setReport(next); };
  const updateResults = React.useCallback((change: (old: Record<string, PanelResult>) => Record<string, PanelResult>) => {
    resultsRef.current = change(resultsRef.current); setResults(resultsRef.current);
  }, []);
  React.useEffect(() => () => { sequence.current++; controller.current?.abort(); }, []);

  const loadSaved = React.useCallback(async (signal?: AbortSignal) => {
    const responses = await Promise.allSettled([
      apiClient.get<BiReport[]>(`${BI_ROOT}/reports`, { ...options, signal }),
      apiClient.get<Array<{ id: string; title: string }>>("/api/v1/analytics/analyses", { ...options, signal }),
      apiClient.get<Array<{ id: string; title: string }>>("/api/v1/analytics/auto/boards", { ...options, signal }),
      apiClient.get<Array<{ id: string; plan: { title: string } }>>("/api/v1/analytics/workspaces", { ...options, signal }),
    ]);
    if (signal?.aborted) return;
    const items: SavedOption[] = [];
    responses.forEach((response, index) => {
      if (response.status !== "fulfilled") { if (index === 0) setSaveError(`Saved AskBI reports: ${failure(response.reason)}`); return; }
      for (const item of response.value) {
        const source = ([undefined, "analysis", "board", "workspace"] as const)[index];
        items.push({ id: item.id, title: "title" in item ? item.title : item.plan.title, source });
      }
    });
    setSaved(items);
  }, []);

  React.useEffect(() => {
    const abort = new AbortController();
    void apiClient.get<Capability>(`${BI_ROOT}/capabilities`, { ...options, signal: abort.signal }).then(value => {
      if (abort.signal.aborted) return;
      if (value.schemaVersion !== 2 || value.engine !== "askbi-v2") {
        setCapabilityError("The frontend and API use different reporting versions. Deploy matching builds before enabling AskBI.");
        return;
      }
      setCapability(value);
      if (value.enabled) void loadSaved(abort.signal);
    }).catch(cause => { if (!abort.signal.aborted) setCapabilityError(failure(cause)); });
    return () => abort.abort();
  }, [loadSaved]);

  function begin() {
    controller.current?.abort(); controller.current = new AbortController();
    const id = ++sequence.current; locked.current = true; setError("");
    return { id, signal: controller.current.signal };
  }
  function stop() {
    needsSync.current = true; sequence.current++; controller.current?.abort(); locked.current = false;
    setStatus(""); setError("Stopped waiting. A running server request may still finish; the next edit checks the saved revision first.");
    updateResults(old => Object.fromEntries(Object.entries(old).map(([key, value]) => [key, { ...value, loading: false, error: value.loading ? "Refresh interrupted. Previous results remain available; retry to update." : value.error }])));
  }

  async function executePanel(current: BiReport, panel: BiPanel, id: number, signal: AbortSignal): Promise<PanelResult | null> {
    if (id !== sequence.current) return null;
    updateResults(old => ({ ...old, [panel.id]: { ...old[panel.id], loading: true, error: undefined } }));
    try {
      const value = await apiClient.post<RunResult>(`${BI_ROOT}/reports/${current.id}/run`, { revision: current.revision, panelId: panel.id }, { ...options, signal });
      if (id !== sequence.current) return null;
      const state = { ...value, scope: panelScope(panel), resultSpec: panel.spec, revision: current.revision, loadedAt: new Date().toISOString() };
      updateResults(old => ({ ...old, [panel.id]: state }));
      return state;
    } catch (cause) {
      if (id === sequence.current) updateResults(old => ({ ...old, [panel.id]: { ...old[panel.id], loading: false, error: failure(cause) } }));
      return null;
    }
  }

  async function display(current: BiReport, id: number, signal: AbortSignal, force = false) {
    const panels = current.state.plan?.panels ?? [];
    if (!panels.length) return;
    if (force || panels.some(panel => !Object.values(resultsRef.current).some(value => value.result && !value.error && value.scope === panelScope(panel)))) {
      setBriefing([]); setNarrationUsage(null);
    }
    setStatus("Loading report data…");
    const pending = new Map<string, Promise<PanelResult | null>>();
    const fresh: string[] = [];
    let cursor = 0;
    let failures = 0;
    let dataChanged = false;
    async function worker() {
      while (cursor < panels.length && id === sequence.current) {
        const panel = panels[cursor++];
        if (!panel) return;
        const scope = panelScope(panel);
        const reusable = !force && Object.values(resultsRef.current).find(value => value.result && !value.error && value.scope === scope);
        if (reusable) { updateResults(old => ({ ...old, [panel.id]: reusable })); continue; }
        dataChanged = true;
        const task = pending.get(scope) ?? executePanel(current, panel, id, signal);
        pending.set(scope, task);
        const state = await task;
        if (id !== sequence.current) return;
        if (state) {
          updateResults(old => ({ ...old, [panel.id]: state }));
          // Only signed evidence for this exact panel may enter the briefing.
          if (state.evidence && !fresh.includes(state.evidence)) fresh.push(state.evidence);
        } else failures++;
      }
    }
    await Promise.all([worker(), worker()]);
    if (id !== sequence.current) return;
    setStatus("");
    if (dataChanged) { setBriefing([]); setNarrationUsage(null); }
    if (failures) setError(`${failures} panel(s) could not finish. Completed results remain available; retry failed panels.`);
    // Unlock core interaction while optional narration runs; sequence checks
    // prevent it overwriting a newer report or filter selection.
    locked.current = false;
    if (fresh.length) {
      try {
        const story = await apiClient.post<{ paragraphs: string[]; limitation?: string | null; usage: BiUsage }>(`${BI_ROOT}/reports/${current.id}/narration`, { revision: current.revision, evidence: fresh }, { ...options, signal });
        if (id === sequence.current) { setBriefing(story.limitation ? [...story.paragraphs, story.limitation] : story.paragraphs); setNarrationUsage(story.usage); }
      } catch { if (id === sequence.current) setBriefing(["AI briefing is unavailable. Each completed panel retains its numerical evidence."]); }
    }
  }

  async function command(action: ReportAction, question = "", value?: string, target = selected, retry = false) {
    if (locked.current || !capability?.enabled) return;
    const work = begin(); setStatus(action === "ask" ? "Understanding your question…" : "Applying report change…");
    try {
      let current = reportRef.current;
      if (!current) {
        // Retain ID even across a failed create response for idempotent retries.
        const draftId = lastRequest.current?.id ?? crypto.randomUUID();
        lastRequest.current = { id: draftId, body: {} };
        current = await apiClient.post<BiReport>(`${BI_ROOT}/reports`, { id: draftId }, { ...options, signal: work.signal });
        if (work.id !== sequence.current) return;
        setCurrent(current);
      }
      if (needsSync.current && !retry) {
        current = await apiClient.get<BiReport>(`${BI_ROOT}/reports/${current.id}`, { ...options, signal: work.signal });
        if (work.id !== sequence.current) return;
        setCurrent(current); needsSync.current = false;
      }
      const retryQuestion = retry ? current.state.turns.at(-1)?.question ?? question : question;
      const body = retry && needsSync.current && lastRequest.current?.id === current.id && "requestId" in lastRequest.current.body ? lastRequest.current.body : { requestId: crypto.randomUUID(), revision: current.revision, question: retryQuestion, selectedPanelId: target, action, value: value ?? null };
      lastRequest.current = { id: current.id, body };
      const next = await apiClient.post<BiReport>(`${BI_ROOT}/reports/${current.id}/turns`, body, { ...options, signal: work.signal });
      if (work.id !== sequence.current) return;
      setCurrent(next); setLocalTurns([]); needsSync.current = false;
      if (selected && !next.state.plan?.panels.some(panel => panel.id === selected)) setSelected(null);
      const last = next.state.turns.at(-1);
      if (last?.kind === "error") { setError(last.answer); return; }
      if (last?.kind === "clarification" || last?.kind === "unsupported") return;
      if (action === "save") { void loadSaved(work.signal); return; }
      await display(next, work.id, work.signal, action === "refresh");
    } catch (cause) {
      if (work.id === sequence.current) {
        needsSync.current = true; setError(failure(cause));
        setLocalTurns([{ id: crypto.randomUUID(), question: question || action, answer: failure(cause), kind: "error", code: cause instanceof ApiError ? cause.code : "network", changedPanelIds: [] }]);
      }
    } finally { if (work.id === sequence.current) { setStatus(""); locked.current = false; } }
  }

  async function open(item: SavedOption) {
    const work = begin(); setStatus("Opening report…");
    try {
      const next = item.source
        ? await apiClient.post<BiReport>(`${BI_ROOT}/reports`, { id: crypto.randomUUID(), source: item.source, sourceId: item.id }, { ...options, signal: work.signal })
        : await apiClient.get<BiReport>(`${BI_ROOT}/reports/${item.id}`, { ...options, signal: work.signal });
      if (work.id !== sequence.current) return;
      setCurrent(next); updateResults(() => ({})); setSelected(null); setLocalTurns([]); setBriefing([]); needsSync.current = false; lastRequest.current = null;
      await display(next, work.id, work.signal);
    } catch (cause) { if (work.id === sequence.current) setError(failure(cause)); }
    finally { if (work.id === sequence.current) { setStatus(""); locked.current = false; } }
  }

  function reset() {
    sequence.current++; controller.current?.abort(); locked.current = false; needsSync.current = false; lastRequest.current = null;
    setCurrent(null); updateResults(() => ({})); setSelected(null); setLocalTurns([]); setBriefing([]); setNarrationUsage(null); setStatus(""); setError("");
  }
  async function retryPanel(panel: BiPanel) {
    if (!reportRef.current || locked.current) return;
    const work = begin(); setStatus("Retrying panel…");
    setBriefing([]); setNarrationUsage(null);
    try { await executePanel(reportRef.current, panel, work.id, work.signal); }
    finally { if (work.id === sequence.current) { setStatus(""); locked.current = false; } }
  }
  return { capability, capabilityError, report, results, selected, setSelected, status, error, briefing, narrationUsage, saved, saveError,
    turns: [...(report?.state.turns ?? []), ...localTurns], command, open, reset, stop, retryPanel };
}
