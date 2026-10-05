"use client";

import type {
  AnalyticsAnalysisKind,
  AnalyticsCapabilities,
  AnalyticsFilterSpec,
  AnalyticsFix,
  AnalyticsIssue,
  AnalyticsOption,
  AnalyticsRunResponse,
  AnalyticsSpec,
  AnalyticsSuggestion,
  AnalyticsVizKind,
  SavedAnalysis,
  SemanticPackResponse,
} from "@nql/shared-types";
import {
  AlertTriangle,
  BarChart3,
  Boxes,
  Calendar,
  ChevronDown,
  Copy,
  Download,
  Filter,
  Gauge,
  Grid3x3,
  Info,
  Layers,
  LineChart,
  Lightbulb,
  Loader2,
  PieChart,
  Play,
  RotateCcw,
  Save,
  Search,
  SlidersHorizontal,
  Sparkles,
  Table2,
  Trash2,
  TrendingUp,
  Wand2,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { InsightSummary } from "@/components/chat/insight-summary";
import { ResultChart, type ChartKind } from "@/components/chat/result-chart";
import type { InsightDepth, NarrationSections } from "@/components/chat/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  EMPTY_SPEC,
  useAnalyticsAssist,
  useAnalyticsCapabilities,
  useAnalyticsInspect,
  useAnalyticsRun,
  useFilterValues,
  useSavedAnalyses,
  useSavedAnalysisMutations,
} from "@/hooks/use-analytics";
import {
  DATE_PRESETS,
  LIMITED_ANALYSES,
  SINGLE_METRIC_ANALYSES,
  applyFix,
  columnLabel,
  downloadCsv,
  formatCell,
  formatDateRangeLabel,
  formatQuerySentence,
  normalizeSpec,
  prettyLabel,
  recommendViz,
} from "@/lib/analytics/helpers";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const VIZ_OPTIONS: Array<{
  id: AnalyticsVizKind;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { id: "table", label: "Table", icon: Table2 },
  { id: "bar", label: "Bar", icon: BarChart3 },
  { id: "line", label: "Line", icon: LineChart },
  { id: "area", label: "Area", icon: TrendingUp },
  { id: "pie", label: "Pie", icon: PieChart },
  { id: "kpi", label: "KPI", icon: Gauge },
  { id: "heatmap", label: "Heatmap", icon: Grid3x3 },
  { id: "treemap", label: "Treemap", icon: Boxes },
];

const COMPOSER_TABS = [
  { id: "metrics" as const, label: "Metrics", hint: "What to measure", icon: Gauge },
  { id: "dimensions" as const, label: "Dimensions", hint: "How to split it", icon: Layers },
  { id: "advanced" as const, label: "Advanced Analytics", hint: "Ranking, growth, targets", icon: SlidersHorizontal },
];

type ComposerTab = (typeof COMPOSER_TABS)[number]["id"];

const DIM_GROUP_ORDER = ["Time", "Geography", "Vehicle", "Product", "Policy", "Sales Organization", "Distribution", "Claims"];
const ANALYSIS_GROUP_ORDER = ["Basics", "Ranking", "Distribution", "Running", "Moving", "Growth", "Variance"];
const WINDOW_OPTIONS = [3, 6, 12];
const RANK_METHODS: Array<{ id: NonNullable<AnalyticsSpec["rankMethod"]>; label: string; hint: string }> = [
  { id: "rank", label: "Rank", hint: "Ties share a rank; the next rank is skipped (1, 1, 3)" },
  { id: "dense_rank", label: "Dense rank", hint: "Ties share a rank; no gaps (1, 1, 2)" },
  { id: "row_number", label: "Row number", hint: "Unique position for every row (1, 2, 3)" },
];

function startersFor(caps: AnalyticsCapabilities | undefined): Array<{ label: string; spec: AnalyticsSpec }> {
  if (!caps) return [];
  const has = (id: string) => caps.metrics.some((m) => m.id === id && m.supported);
  const items: Array<{ label: string; spec: AnalyticsSpec }> = [];
  const add = (label: string, spec: Partial<AnalyticsSpec>) =>
    items.push({ label, spec: { ...EMPTY_SPEC, ...spec } });
  if (has("revenue")) {
    add("Revenue trend, last 12 months", { metrics: ["revenue"], dimensions: ["month"], analysis: "trend", datePreset: "last_12_months" });
    add("Top 10 models", { metrics: ["revenue"], dimensions: ["model"], analysis: "top_n", limit: 10 });
    add("Market share by brand", { metrics: ["revenue"], dimensions: ["make"], analysis: "contribution" });
    add("Target achievement by brand", { metrics: ["revenue"], dimensions: ["make"], analysis: "actual_vs_target", datePreset: "ytd" });
  }
  if (has("gross_written_premium")) {
    add("Premium trend, last 12 months", { metrics: ["gross_written_premium"], dimensions: ["month"], analysis: "trend", datePreset: "last_12_months" });
    add("Premium share by line", { metrics: ["gross_written_premium"], dimensions: ["line_of_business"], analysis: "contribution" });
    add("Top 10 agents by premium", { metrics: ["gross_written_premium"], dimensions: ["agent"], analysis: "top_n", limit: 10 });
    add("Claims paid YoY", { metrics: ["claims_paid"], dimensions: ["month"], analysis: "yoy_growth", datePreset: "last_12_months" });
  }
  return items.slice(0, 4);
}

function capabilitiesErrorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404) {
      return "The API server is running an older build without the builder endpoints. Restart the API and retry.";
    }
    if (err.isAuthError) return "Your session has expired. Sign in again and retry.";
    return `${err.message}${err.requestId ? ` (request ${err.requestId})` : ""}`;
  }
  return "The API server could not be reached. Make sure it is running on port 8000, then retry.";
}

function issuesFromError(err: unknown): { issues: AnalyticsIssue[]; suggestions: AnalyticsSuggestion[] } {
  if (!(err instanceof ApiError)) return { issues: [], suggestions: [] };
  const details = err.details ?? {};
  return {
    issues: Array.isArray(details.issues) ? (details.issues as AnalyticsIssue[]) : [],
    suggestions: Array.isArray(details.suggestions) ? (details.suggestions as AnalyticsSuggestion[]) : [],
  };
}

export function AnalyticsBuilderShell({ pack }: { pack: SemanticPackResponse }) {
  const [spec, setSpec] = React.useState<AnalyticsSpec>(EMPTY_SPEC);
  const [aiPrompt, setAiPrompt] = React.useState("");
  const [sqlOpen, setSqlOpen] = React.useState(false);
  const [result, setResult] = React.useState<AnalyticsRunResponse | null>(null);
  const [previewTab, setPreviewTab] = React.useState<"chart" | "table" | "narration">("chart");
  const [error, setError] = React.useState<string | null>(null);
  const [errorSuggestions, setErrorSuggestions] = React.useState<AnalyticsSuggestion[]>([]);
  const [flash, setFlash] = React.useState<string | null>(null);
  const [activeAnalysisId, setActiveAnalysisId] = React.useState<string | null>(null);
  const [saveTitle, setSaveTitle] = React.useState("");
  const [composerTab, setComposerTab] = React.useState<ComposerTab>("metrics");
  const [showFilters, setShowFilters] = React.useState(false);
  const [focusDomain, setFocusDomain] = React.useState<string | null>(null);

  const run = useAnalyticsRun();
  const assist = useAnalyticsAssist();
  const saved = useSavedAnalyses();
  const mutations = useSavedAnalysisMutations();
  const capsQuery = useAnalyticsCapabilities();
  const caps = capsQuery.data;
  const inspection = useAnalyticsInspect(spec);
  const report = inspection.data;

  const glossaryByMeasure = React.useMemo(() => {
    const map = new Map<string, string[]>();
    for (const [name, term] of Object.entries(pack.glossary.terms)) {
      if (term.mapsToMeasure) {
        const list = map.get(term.mapsToMeasure) ?? [];
        list.push(term.displayLabel ?? name, ...term.synonyms);
        map.set(term.mapsToMeasure, list);
      }
    }
    return map;
  }, [pack.glossary.terms]);

  const metricLabels = React.useMemo(
    () => Object.fromEntries((caps?.metrics ?? []).map((m) => [m.id, m.label])),
    [caps],
  );
  const dimensionLabels = React.useMemo(
    () => Object.fromEntries((caps?.dimensions ?? []).map((d) => [d.id, d.label])),
    [caps],
  );
  const datePresets = caps?.datePresets ?? DATE_PRESETS;
  const dateLabels = React.useMemo(
    () => Object.fromEntries(datePresets.map((d) => [d.id, d.label])),
    [datePresets],
  );
  const analysisCaps = React.useMemo(
    () => new Map((caps?.analyses ?? []).map((a) => [a.id, a])),
    [caps],
  );
  const optionMap = (items: AnalyticsOption[] | undefined) =>
    new Map((items ?? []).map((item) => [item.id, item]));
  const metricOptions = React.useMemo(() => optionMap(report?.metrics), [report]);
  const dimensionOptions = React.useMemo(() => optionMap(report?.dimensions), [report]);
  const analysisOptions = React.useMemo(() => optionMap(report?.analyses), [report]);
  const starters = React.useMemo(() => startersFor(caps), [caps]);

  const errors = (report?.issues ?? []).filter((issue) => issue.severity === "error");
  const warnings = (report?.issues ?? []).filter((issue) => issue.severity === "warning");
  const settled = !inspection.isFetching && !inspection.isPlaceholderData;
  const blocked = Boolean(report && !report.valid);

  const sentence = formatQuerySentence(spec, {
    metrics: metricLabels,
    dimensions: dimensionLabels,
    dates: dateLabels,
  });
  const dateLabel = formatDateRangeLabel(spec, dateLabels);
  const effectiveViz = result?.recommendedViz ?? recommendViz(spec);
  const singleMetric = SINGLE_METRIC_ANALYSES.has(spec.analysis);
  const ontologyHref = spec.metrics[0]
    ? `/semantic?tab=graph&focus=${encodeURIComponent(spec.metrics[0])}`
    : "/semantic?tab=graph";
  const resultFilterDomain = React.useMemo(() => {
    const firstCategory = spec.dimensions.find((id) => !["month", "quarter", "year"].includes(id));
    return caps?.dimensions.find((d) => d.id === firstCategory)?.filterDomain ?? null;
  }, [caps, spec.dimensions]);

  function showFlash(message: string) {
    setFlash(message);
    window.setTimeout(() => setFlash(null), 2600);
  }

  const executeSpec = React.useCallback(
    async (next: AnalyticsSpec) => {
      setError(null);
      setErrorSuggestions([]);
      try {
        const payload = await run.mutateAsync(next);
        setResult(payload);
        setPreviewTab(next.viz === "table" || payload.recommendedViz === "table" ? "table" : "chart");
      } catch (err) {
        setResult(null);
        const { suggestions } = issuesFromError(err);
        setErrorSuggestions(suggestions);
        setError(
          err instanceof ApiError
            ? err.message
            : "Something went wrong while running the analysis. Please try again.",
        );
      }
    },
    [run],
  );

  async function handleRun() {
    await executeSpec(spec);
  }

  function update(next: AnalyticsSpec | ((prev: AnalyticsSpec) => AnalyticsSpec)) {
    setError(null);
    setErrorSuggestions([]);
    setSpec(next);
  }

  function handleFix(fix: AnalyticsFix) {
    if (fix.action === "open_filters") {
      setShowFilters(true);
      setFocusDomain(fix.value ?? null);
      return;
    }
    update((prev) => applyFix(prev, fix));
    if (fix.action === "add_dimension") setComposerTab("dimensions");
    if (fix.action === "set_analysis") setComposerTab("advanced");
  }

  function applyDatePreset(preset: string) {
    update((prev) => ({
      ...prev,
      datePreset: preset || null,
      dateFrom: preset === "custom" ? prev.dateFrom : null,
      dateTo: preset === "custom" ? prev.dateTo : null,
    }));
  }

  function handleResetBuilder() {
    setSpec({ ...EMPTY_SPEC });
    setResult(null);
    setError(null);
    setErrorSuggestions([]);
    setComposerTab("metrics");
    setShowFilters(false);
    setPreviewTab("chart");
    setActiveAnalysisId(null);
    setSaveTitle("");
    setAiPrompt("");
    showFlash("Builder cleared");
  }

  async function handleAssist() {
    if (!aiPrompt.trim()) return;
    setError(null);
    try {
      const response = await assist.mutateAsync(aiPrompt.trim());
      const next = normalizeSpec({ ...response.spec, viz: "auto" }, EMPTY_SPEC);
      setSpec(next);
      showFlash(response.explanation.slice(0, 160));
      if (next.metrics.length) await executeSpec(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not interpret the prompt.");
    }
  }

  function toggleMetric(id: string) {
    update((prev) => {
      const exists = prev.metrics.includes(id);
      if (exists) return { ...prev, metrics: prev.metrics.filter((m) => m !== id) };
      if (SINGLE_METRIC_ANALYSES.has(prev.analysis)) return { ...prev, metrics: [id] };
      return { ...prev, metrics: [...prev.metrics, id].slice(0, 3) };
    });
  }

  function toggleDimension(id: string) {
    update((prev) => {
      if (prev.dimensions.includes(id)) {
        return { ...prev, dimensions: prev.dimensions.filter((d) => d !== id) };
      }
      return applyFix(prev, { label: "", action: "add_dimension", value: id });
    });
  }

  function upsertFilter(domain: string, values: string[]) {
    update((prev) => {
      const rest = prev.filters.filter((f) => f.domain !== domain);
      const filters: AnalyticsFilterSpec[] =
        values.length > 0 ? [...rest, { domain, values, operator: "=" }] : rest;
      return { ...prev, filters };
    });
  }

  async function applyResultFilter(value: string) {
    if (!resultFilterDomain) return;
    const existing = spec.filters.find((f) => f.domain === resultFilterDomain)?.values ?? [];
    const values = existing.includes(value) ? existing : [...existing, value];
    const next: AnalyticsSpec = {
      ...spec,
      filters: [
        ...spec.filters.filter((f) => f.domain !== resultFilterDomain),
        { domain: resultFilterDomain, values, operator: "=" },
      ],
    };
    setSpec(next);
    await executeSpec(next);
  }

  async function applySuggestion(suggestion: AnalyticsSuggestion) {
    const next = normalizeSpec({ ...suggestion.spec, viz: "auto" }, EMPTY_SPEC);
    setSpec(next);
    setActiveAnalysisId(null);
    await executeSpec(next);
  }

  async function handleSave() {
    const title = saveTitle.trim() || result?.title || "Untitled analysis";
    try {
      if (activeAnalysisId) {
        await mutations.update.mutateAsync({ id: activeAnalysisId, title, spec, sqlSnapshot: result?.sql ?? null, viz: spec.viz });
        showFlash("Analysis updated");
      } else {
        const created = await mutations.create.mutateAsync({ title, spec, sqlSnapshot: result?.sql ?? null, viz: spec.viz });
        setActiveAnalysisId(created.id);
        setSaveTitle(created.title);
        showFlash("Analysis saved");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save analysis.");
    }
  }

  async function loadSaved(item: SavedAnalysis) {
    const next = normalizeSpec(item.spec as Partial<AnalyticsSpec>, EMPTY_SPEC);
    setSpec(next);
    setShowFilters(Boolean(next.filters.length));
    setActiveAnalysisId(item.id);
    setSaveTitle(item.title);
    showFlash(`Loaded “${item.title}”`);
    if (next.metrics.length) await executeSpec(next);
  }

  const groupedDimensions = React.useMemo(() => {
    const groups = new Map<string, Array<{ id: string; label: string }>>();
    for (const dim of caps?.dimensions ?? []) {
      const list = groups.get(dim.group) ?? [];
      list.push({ id: dim.id, label: dim.label });
      groups.set(dim.group, list);
    }
    const order = [...DIM_GROUP_ORDER, ...[...groups.keys()].filter((g) => !DIM_GROUP_ORDER.includes(g))];
    return order.filter((g) => groups.has(g)).map((g) => ({ group: g, items: groups.get(g) ?? [] }));
  }, [caps]);

  const groupedAnalyses = React.useMemo(() => {
    const groups = new Map<string, NonNullable<typeof caps>["analyses"]>();
    for (const item of caps?.analyses ?? []) {
      const list = groups.get(item.group) ?? [];
      list.push(item);
      groups.set(item.group, list);
    }
    return ANALYSIS_GROUP_ORDER.filter((g) => groups.has(g)).map((g) => ({ group: g, items: groups.get(g) ?? [] }));
  }, [caps]);

  const currentAnalysis = analysisCaps.get(spec.analysis);
  const runDisabled = run.isPending || spec.metrics.length === 0 || (settled && blocked);

  return (
    <div className="analytics-builder relative min-h-[70vh]">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -top-6 h-40 bg-[radial-gradient(ellipse_at_top,color-mix(in_oklab,hsl(var(--info))_18%,transparent),transparent_70%)]"
      />

      {flash ? (
        <div className="fixed bottom-6 right-6 z-50 max-w-sm rounded-xl border border-border/60 bg-surface-raised/95 px-4 py-2 text-sm shadow-lg backdrop-blur">
          {flash}
        </div>
      ) : null}

      <section className="relative mb-4 overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-br from-surface-raised via-surface-raised to-info/5 p-4 shadow-[var(--shadow-card)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-info">Business analytics</p>
            <h2 className="mt-1 text-lg font-semibold tracking-tight">Ask in concepts, not tables</h2>
            <p className="mt-1 max-w-xl text-sm text-muted-foreground">
              Pick a metric, how to split it and an analysis. Options that don&apos;t fit your
              selection are explained, and every result comes with a business summary.
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <Link href={ontologyHref} className="text-xs font-medium text-primary hover:underline">
              Inspect in Ontology →
            </Link>
            {caps?.dataAsOf ? (
              <span className="text-[11px] text-muted-foreground">Data through {caps.dataAsOf}</span>
            ) : null}
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Sparkles className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-info" />
            <Input
              value={aiPrompt}
              onChange={(event) => setAiPrompt(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void handleAssist();
              }}
              placeholder="Try “Top 3 models within each brand” or “Revenue trend last 12 months”"
              className="h-10 border-border/60 bg-background/70 pl-10"
              aria-label="AI assisted builder prompt"
            />
          </div>
          <Button
            type="button"
            variant="secondary"
            className="h-10"
            disabled={assist.isPending || !aiPrompt.trim()}
            onClick={() => void handleAssist()}
          >
            {assist.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            Populate builder
          </Button>
        </div>
      </section>

      <div className="relative grid gap-4 lg:grid-cols-[19rem_minmax(0,1fr)]">
        <aside className="space-y-2 lg:sticky lg:top-3 lg:self-start">
          <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Configure</p>
          <div className="flex flex-col gap-1.5" role="tablist" aria-label="Builder sections">
            {COMPOSER_TABS.map((tab) => {
              const Icon = tab.icon;
              const active = composerTab === tab.id;
              const summary =
                tab.id === "metrics"
                  ? spec.metrics.map((id) => metricLabels[id] ?? prettyLabel(id)).join(", ")
                  : tab.id === "dimensions"
                    ? spec.dimensions.map((id) => dimensionLabels[id] ?? prettyLabel(id)).join(", ")
                    : currentAnalysis?.label;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  className={cn(
                    "flex items-center gap-3 rounded-2xl border px-3 py-2.5 text-left shadow-sm transition-colors",
                    active
                      ? "border-primary/50 bg-primary/10 text-foreground"
                      : "border-border/60 bg-surface-raised/85 text-muted-foreground hover:bg-muted/40",
                  )}
                  onClick={() => setComposerTab(tab.id)}
                >
                  <span
                    className={cn(
                      "flex size-8 items-center justify-center rounded-xl border",
                      active ? "border-primary/30 bg-background" : "border-border/50 bg-muted/30",
                    )}
                  >
                    <Icon className="size-4" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-foreground">{tab.label}</span>
                    <span className="block truncate text-[11px]">{summary || tab.hint}</span>
                  </span>
                </button>
              );
            })}
          </div>

          <section className="rounded-2xl border border-border/60 bg-surface-raised/85 p-3 shadow-sm">
            {!caps ? (
              <div className="flex flex-col gap-2 py-6 text-xs text-muted-foreground">
                {capsQuery.isError ? (
                  <>
                    <p className="font-medium text-foreground">Could not load the builder options.</p>
                    <p>{capabilitiesErrorText(capsQuery.error)}</p>
                    <Button
                      size="sm"
                      variant="secondary"
                      className="w-fit"
                      disabled={capsQuery.isFetching}
                      onClick={() => void capsQuery.refetch()}
                    >
                      {capsQuery.isFetching ? <Loader2 className="size-3.5 animate-spin" /> : null}
                      Retry
                    </Button>
                  </>
                ) : (
                  <p className="flex items-center gap-2">
                    <Loader2 className="size-3.5 animate-spin" /> Loading options…
                  </p>
                )}
              </div>
            ) : composerTab === "metrics" ? (
              <>
                <SelectedPills ids={spec.metrics} labels={metricLabels} onRemove={toggleMetric} />
                {singleMetric ? (
                  <p className="mb-2 text-[10px] text-muted-foreground">
                    {currentAnalysis?.label ?? "This analysis"} uses one metric; picking another replaces it.
                  </p>
                ) : null}
                <SearchableChips
                  items={caps.metrics.map((m) => {
                    const option = metricOptions.get(m.id);
                    const reason = !m.supported ? m.reason : option && !option.available ? option.reason : null;
                    return {
                      id: m.id,
                      label: m.label,
                      keywords: [m.description ?? "", ...(glossaryByMeasure.get(m.id) ?? [])],
                      disabled: Boolean(reason) && !spec.metrics.includes(m.id),
                      title: reason ?? m.description ?? undefined,
                    };
                  })}
                  selected={spec.metrics}
                  onToggle={toggleMetric}
                />
              </>
            ) : composerTab === "dimensions" ? (
              <>
                <SelectedPills ids={spec.dimensions} labels={dimensionLabels} onRemove={toggleDimension} />
                <GroupedChips
                  groups={groupedDimensions}
                  selected={spec.dimensions}
                  onToggle={toggleDimension}
                  reasonFor={(id) => {
                    const option = dimensionOptions.get(id);
                    return option && !option.available ? (option.reason ?? "Not available") : null;
                  }}
                />
              </>
            ) : (
              <AdvancedPanel
                spec={spec}
                groups={groupedAnalyses}
                options={analysisOptions}
                onSelect={(id) =>
                  update((prev) => ({
                    ...prev,
                    analysis: id,
                    metrics: SINGLE_METRIC_ANALYSES.has(id) ? prev.metrics.slice(0, 1) : prev.metrics,
                  }))
                }
                onChange={(patch) => update((prev) => ({ ...prev, ...patch }))}
              />
            )}
          </section>
        </aside>

        <div className="min-w-0 space-y-4">
          <section className="rounded-2xl border border-border/60 bg-surface-raised/85 p-3 shadow-sm">
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex min-w-[220px] flex-1 items-center gap-2 text-[11px] text-muted-foreground">
                <Calendar className="size-3.5 shrink-0" />
                <span className="sr-only">Date range</span>
                <select
                  className="h-10 w-full rounded-[var(--radius-control)] border border-border bg-background px-2 text-sm text-foreground"
                  value={spec.datePreset ?? ""}
                  onChange={(event) => applyDatePreset(event.target.value)}
                  aria-label="Date range"
                >
                  <option value="">All dates</option>
                  {datePresets.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <Button type="button" variant="secondary" className="h-10" onClick={() => setShowFilters((open) => !open)}>
                <Filter className="size-3.5" />
                {showFilters ? "Hide Filters" : spec.filters.length ? `Filters (${spec.filters.length})` : "Show Filters"}
              </Button>
              <Button type="button" variant="ghost" className="h-10" onClick={handleResetBuilder}>
                <RotateCcw className="size-3.5" />
                Clear
              </Button>
            </div>
            {spec.datePreset && spec.datePreset !== "custom" && caps?.dataAsOf ? (
              <p className="mt-2 text-[11px] text-muted-foreground">
                Relative ranges count back from the latest loaded data ({caps.dataAsOf}), not today.
              </p>
            ) : null}

            {spec.datePreset === "custom" ? (
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <label className="text-[11px] text-muted-foreground">
                  Start date
                  <Input
                    type="date"
                    className="mt-1 h-10"
                    max={caps?.dataAsOf ?? undefined}
                    value={spec.dateFrom ?? ""}
                    onChange={(event) => update((prev) => ({ ...prev, dateFrom: event.target.value || null }))}
                  />
                </label>
                <label className="text-[11px] text-muted-foreground">
                  End date
                  <Input
                    type="date"
                    className="mt-1 h-10"
                    min={spec.dateFrom ?? undefined}
                    value={spec.dateTo ?? ""}
                    onChange={(event) => update((prev) => ({ ...prev, dateTo: event.target.value || null }))}
                  />
                </label>
              </div>
            ) : null}

            {showFilters ? (
              <div className="mt-3 border-t border-border/50 pt-3">
                <FilterBuilder
                  key={focusDomain ?? "filters"}
                  domains={caps?.filterDomains ?? []}
                  filters={spec.filters}
                  focusDomain={focusDomain}
                  onChange={upsertFilter}
                />
              </div>
            ) : null}
          </section>

          {errors.length || warnings.length ? (
            <IssuesPanel errors={errors} warnings={warnings} onFix={handleFix} />
          ) : null}

          <section className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-surface-raised/90 p-4 shadow-sm md:flex-row md:items-center md:justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-info">Query summary</p>
              <p className="mt-1 text-sm font-medium leading-snug">{sentence}</p>
              <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                <SummaryChip label="Analysis" value={currentAnalysis?.label ?? prettyLabel(spec.analysis)} />
                <SummaryChip label="Date" value={dateLabel || "All dates"} />
                <SummaryChip
                  label="Filters"
                  value={spec.filters.map((item) => `${item.domain}: ${item.values.join(", ")}`).join(" · ") || "None"}
                />
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-stretch gap-1">
              <Button
                type="button"
                className="h-12 px-6 text-sm"
                disabled={runDisabled}
                title={blocked ? errors[0]?.message : undefined}
                onClick={() => void handleRun()}
              >
                {run.isPending ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
                Run analysis
              </Button>
              {settled && blocked ? (
                <span className="text-center text-[10px] text-muted-foreground">Fix the highlighted issue to run</span>
              ) : null}
            </div>
          </section>

          {report?.suggestions.length && spec.metrics.length ? (
            <SuggestionStrip suggestions={report.suggestions} onPick={(s) => void applySuggestion(s)} />
          ) : null}

          <main className="space-y-3">
            <div className="rounded-2xl border border-border/60 bg-surface-raised/80 p-4 shadow-[var(--shadow-card)] backdrop-blur">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="text-base font-semibold tracking-tight">{result?.title ?? "Chart / table preview"}</h3>
                  <p className="text-xs text-muted-foreground">
                    {result ? <ResultMetaLine result={result} /> : "Configure the analysis and run it, or pick a starter."}
                  </p>
                </div>
                <AnalysisActions
                  result={result}
                  saveTitle={saveTitle}
                  onSaveTitle={setSaveTitle}
                  onSave={() => void handleSave()}
                  onDuplicate={() => {
                    if (!activeAnalysisId) {
                      showFlash("Save the analysis first");
                      return;
                    }
                    void mutations.duplicate.mutateAsync(activeAnalysisId).then((row) => {
                      setActiveAnalysisId(row.id);
                      setSaveTitle(row.title);
                      showFlash("Duplicated");
                    });
                  }}
                  onDelete={() => {
                    if (!activeAnalysisId) return;
                    void mutations.remove.mutateAsync(activeAnalysisId).then(() => {
                      setActiveAnalysisId(null);
                      setSaveTitle("");
                      showFlash("Deleted");
                    });
                  }}
                  onExportCsv={() => {
                    if (!result?.rows.length) {
                      showFlash("Nothing to export");
                      return;
                    }
                    downloadCsv(`analysis-${Date.now()}.csv`, result.columns, result.rows);
                    showFlash("CSV downloaded");
                  }}
                  saving={mutations.create.isPending || mutations.update.isPending}
                />
              </div>

              {spec.filters.length ? (
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] text-muted-foreground">Focus:</span>
                  {spec.filters.flatMap((filt) =>
                    filt.values.map((value) => (
                      <button
                        key={`${filt.domain}-${value}`}
                        type="button"
                        className="rounded-full bg-info/15 px-2 py-0.5 text-[10px] font-medium"
                        onClick={() => upsertFilter(filt.domain, filt.values.filter((entry) => entry !== value))}
                      >
                        {filt.domain}: {value} ×
                      </button>
                    )),
                  )}
                </div>
              ) : null}

              {error ? (
                <div className="mt-4 rounded-xl border border-orange/40 bg-orange/10 px-3 py-2.5 text-sm">
                  <p className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-orange" />
                    <span>{error}</span>
                  </p>
                  {errorSuggestions.length ? (
                    <div className="mt-2 flex flex-wrap gap-1.5 pl-6">
                      {errorSuggestions.map((s) => (
                        <Button key={s.label} type="button" size="sm" variant="secondary" onClick={() => void applySuggestion(s)}>
                          {s.label}
                        </Button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className="mt-4 min-h-[320px] w-full">
                {result || run.isPending ? (
                  <div
                    className="mb-3 flex w-full gap-1 overflow-x-auto rounded-xl border border-border/60 bg-muted/25 p-1"
                    role="toolbar"
                    aria-label="Visualization"
                  >
                    {VIZ_OPTIONS.map((item) => {
                      const Icon = item.icon;
                      const active =
                        previewTab !== "narration" &&
                        (spec.viz === item.id || (spec.viz === "auto" && effectiveViz === item.id));
                      return (
                        <button
                          key={item.id}
                          type="button"
                          className={cn(
                            "inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium",
                            active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:bg-background/60",
                          )}
                          onClick={() => {
                            setSpec((prev) => ({ ...prev, viz: item.id }));
                            setPreviewTab(item.id === "table" ? "table" : "chart");
                          }}
                        >
                          <Icon className="size-3.5" />
                          {item.label}
                        </button>
                      );
                    })}
                    <button
                      type="button"
                      className={cn(
                        "ml-auto inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium",
                        previewTab === "narration" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:bg-background/60",
                      )}
                      onClick={() => setPreviewTab("narration")}
                    >
                      <Lightbulb className="size-3.5" />
                      Insight
                    </button>
                  </div>
                ) : null}
                {!result && !run.isPending ? (
                  <EmptyPreview starters={starters} onPick={(item) => void applySuggestion({ ...item, description: "" })} />
                ) : run.isPending ? (
                  <div className="flex h-[320px] items-center justify-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" />
                    Compiling governed SQL and running…
                  </div>
                ) : result ? (
                  <ResultPreview
                    result={result}
                    viz={spec.viz === "auto" ? effectiveViz : spec.viz}
                    tab={previewTab}
                    filterLabel={resultFilterDomain}
                    onFilterValue={resultFilterDomain ? (value) => void applyResultFilter(value) : undefined}
                  />
                ) : null}
              </div>
            </div>

            <div className="rounded-2xl border border-border/60 bg-surface-raised/70">
              <button
                type="button"
                className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium"
                onClick={() => setSqlOpen((value) => !value)}
              >
                <span>View SQL</span>
                <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", sqlOpen && "rotate-180")} />
              </button>
              {sqlOpen ? (
                <pre className="overflow-x-auto border-t border-border/50 bg-surface-sunken/40 px-4 py-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
                  {result?.sql ?? "Run an analysis to inspect the generated SQL."}
                </pre>
              ) : null}
            </div>

            <SavedList items={saved.data ?? []} activeId={activeAnalysisId} onLoad={(item) => void loadSaved(item)} loading={saved.isPending} />
          </main>
        </div>
      </div>
    </div>
  );
}

function ResultMetaLine({ result }: { result: AnalyticsRunResponse }) {
  const meta = result.meta ?? {};
  const parts = [
    `${result.rows.length}${meta.truncated ? "+" : ""} rows`,
    meta.dateLabel ? String(meta.dateLabel) : null,
    meta.dataAsOf ? `data through ${String(meta.dataAsOf)}` : null,
  ].filter(Boolean);
  return <>{parts.join(" · ")}</>;
}

function IssuesPanel({
  errors,
  warnings,
  onFix,
}: {
  errors: AnalyticsIssue[];
  warnings: AnalyticsIssue[];
  onFix: (fix: AnalyticsFix) => void;
}) {
  return (
    <section className="space-y-2" aria-live="polite">
      {[...errors, ...warnings].map((issue) => {
        const isError = issue.severity === "error";
        return (
          <div
            key={`${issue.code}-${issue.message}`}
            className={cn(
              "rounded-2xl border px-3 py-2.5 text-sm",
              isError ? "border-orange/40 bg-orange/10" : "border-border/60 bg-muted/30",
            )}
          >
            <p className="flex items-start gap-2">
              {isError ? (
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-orange" />
              ) : (
                <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              )}
              <span>{issue.message}</span>
            </p>
            {issue.fixes.length ? (
              <div className="mt-2 flex flex-wrap gap-1.5 pl-6">
                {issue.fixes.map((fix) => (
                  <Button
                    key={`${fix.action}-${fix.value ?? ""}`}
                    type="button"
                    size="sm"
                    variant="secondary"
                    className="h-7 text-[11px]"
                    onClick={() => onFix(fix)}
                  >
                    <Wand2 className="size-3" />
                    {fix.label}
                  </Button>
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </section>
  );
}

function SuggestionStrip({
  suggestions,
  onPick,
}: {
  suggestions: AnalyticsSuggestion[];
  onPick: (suggestion: AnalyticsSuggestion) => void;
}) {
  return (
    <section className="rounded-2xl border border-border/60 bg-surface-raised/70 px-3 py-2.5">
      <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <Lightbulb className="size-3.5 text-info" />
        Suggested analyses
      </p>
      <div className="flex flex-wrap gap-1.5">
        {suggestions.map((s) => (
          <button
            key={s.label}
            type="button"
            title={s.description}
            className="rounded-full border border-border/60 bg-background/60 px-2.5 py-1 text-[11px] font-medium hover:border-info/40 hover:bg-info/10"
            onClick={() => onPick(s)}
          >
            {s.label}
          </button>
        ))}
      </div>
    </section>
  );
}

function AdvancedPanel({
  spec,
  groups,
  options,
  onSelect,
  onChange,
}: {
  spec: AnalyticsSpec;
  groups: Array<{ group: string; items: AnalyticsCapabilities["analyses"] }>;
  options: Map<string, AnalyticsOption>;
  onSelect: (id: AnalyticsAnalysisKind) => void;
  onChange: (patch: Partial<AnalyticsSpec>) => void;
}) {
  const current = groups.flatMap((g) => g.items).find((item) => item.id === spec.analysis);
  return (
    <div className="space-y-3">
      <div className="max-h-[22rem] space-y-2.5 overflow-y-auto pr-1">
        {groups.map(({ group, items }) => (
          <div key={group}>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{group}</p>
            <div className="flex flex-wrap gap-1.5">
              {items.map((item) => {
                const option = options.get(item.id);
                const unavailable = option ? !option.available : false;
                const active = spec.analysis === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    aria-disabled={unavailable}
                    title={unavailable ? (option?.reason ?? undefined) : item.description}
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
                      active
                        ? "border-info/40 bg-info/15 text-foreground"
                        : "border-transparent bg-muted/40 text-muted-foreground hover:bg-muted",
                      unavailable && !active && "border-dashed border-border/70 bg-transparent opacity-55",
                    )}
                    onClick={() => onSelect(item.id)}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      {current ? (
        <div className="rounded-xl bg-muted/30 px-2.5 py-2 text-[11px]">
          <p className="text-foreground">{current.description}</p>
          <p className="mt-0.5 text-muted-foreground">Needs: {current.requirement}</p>
        </div>
      ) : null}
      {spec.analysis === "moving_average" ? (
        <OptionRow label="Window">
          {WINDOW_OPTIONS.map((size) => (
            <Pill key={size} active={(spec.window ?? 3) === size} onClick={() => onChange({ window: size })}>
              {size} periods
            </Pill>
          ))}
        </OptionRow>
      ) : null}
      {spec.analysis === "ranking" ? (
        <OptionRow label="Method">
          {RANK_METHODS.map((method) => (
            <Pill key={method.id} active={(spec.rankMethod ?? "rank") === method.id} title={method.hint} onClick={() => onChange({ rankMethod: method.id })}>
              {method.label}
            </Pill>
          ))}
        </OptionRow>
      ) : null}
      {LIMITED_ANALYSES.has(spec.analysis) ? (
        <div className="flex items-center gap-2">
          <label className="text-[11px] text-muted-foreground" htmlFor="limit">
            {spec.analysis === "top_n_per_group" ? "Top per group" : "Show top"}
          </label>
          <Input
            id="limit"
            type="number"
            min={1}
            max={500}
            value={spec.limit}
            onChange={(event) => onChange({ limit: Math.min(500, Math.max(1, Number(event.target.value) || 10)) })}
            className="h-8 w-20 text-xs"
          />
        </div>
      ) : null}
    </div>
  );
}

function OptionRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-[11px] text-muted-foreground">{label}</p>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function Pill({
  active,
  onClick,
  title,
  children,
}: {
  active: boolean;
  onClick: () => void;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      className={cn(
        "rounded-full border px-2.5 py-1 text-[11px] font-medium",
        active ? "border-info/40 bg-info/15 text-foreground" : "border-border/50 bg-background/50 text-muted-foreground hover:bg-muted/50",
      )}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function SummaryChip({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1 rounded-full border border-border/60 bg-muted/30 px-2.5 py-1">
      <span className="font-semibold text-muted-foreground">{label}:</span>
      <span className="truncate text-foreground">{value}</span>
    </span>
  );
}

function SelectedPills({
  ids,
  labels,
  onRemove,
}: {
  ids: string[];
  labels: Record<string, string>;
  onRemove: (id: string) => void;
}) {
  if (!ids.length) return null;
  return (
    <div className="mb-2 flex flex-wrap gap-1">
      {ids.map((id) => (
        <button
          key={id}
          type="button"
          className="rounded-full border border-success/40 bg-success/15 px-2 py-0.5 text-[10px] font-medium"
          onClick={() => onRemove(id)}
        >
          {labels[id] ?? prettyLabel(id)} ×
        </button>
      ))}
    </div>
  );
}

function SearchableChips({
  items,
  selected,
  onToggle,
}: {
  items: Array<{ id: string; label: string; keywords?: string[]; disabled?: boolean; title?: string }>;
  selected: string[];
  onToggle: (id: string) => void;
}) {
  const [q, setQ] = React.useState("");
  const filtered = items.filter((item) => {
    const needle = q.trim().toLowerCase();
    if (!needle) return true;
    return [item.id, item.label, ...(item.keywords ?? [])].join(" ").toLowerCase().includes(needle);
  });
  return (
    <div>
      <div className="relative mb-2">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Search metrics…" className="h-8 pl-8 text-xs" />
      </div>
      <div className="flex max-h-52 flex-wrap gap-1.5 overflow-y-auto">
        {filtered.map((item) => {
          const active = selected.includes(item.id);
          return (
            <button
              key={item.id}
              type="button"
              title={item.title}
              disabled={item.disabled}
              className={cn(
                "rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
                active
                  ? "border-success/40 bg-success/15 text-foreground"
                  : "border-border/50 bg-background/50 text-muted-foreground hover:bg-muted/50",
                item.disabled && "cursor-not-allowed border-dashed opacity-45",
              )}
              onClick={() => onToggle(item.id)}
            >
              {item.label}
            </button>
          );
        })}
        {!filtered.length ? <p className="text-[11px] text-muted-foreground">No matches.</p> : null}
      </div>
      <p className="mt-2 text-[10px] text-muted-foreground">Dimmed options don&apos;t fit the current selection; hover to see why.</p>
    </div>
  );
}

function GroupedChips({
  groups,
  selected,
  onToggle,
  reasonFor,
}: {
  groups: Array<{ group: string; items: Array<{ id: string; label: string }> }>;
  selected: string[];
  onToggle: (id: string) => void;
  reasonFor: (id: string) => string | null;
}) {
  const [q, setQ] = React.useState("");
  return (
    <div>
      <div className="relative mb-2">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Search dimensions…" className="h-8 pl-8 text-xs" />
      </div>
      <div className="max-h-64 space-y-2 overflow-y-auto">
        {groups.map(({ group, items }) => {
          const needle = q.trim().toLowerCase();
          const visible = items.filter((item) => !needle || `${item.id} ${item.label} ${group}`.toLowerCase().includes(needle));
          if (!visible.length) return null;
          return (
            <div key={group}>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{group}</p>
              <div className="flex flex-wrap gap-1.5">
                {visible.map((item) => {
                  const active = selected.includes(item.id);
                  const reason = reasonFor(item.id);
                  const disabled = Boolean(reason) && !active;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      disabled={disabled}
                      title={reason ?? undefined}
                      className={cn(
                        "rounded-full border px-2.5 py-1 text-[11px] font-medium",
                        active
                          ? "border-success/40 bg-success/15 text-foreground"
                          : "border-border/50 bg-background/50 text-muted-foreground hover:bg-muted/50",
                        disabled && "cursor-not-allowed border-dashed opacity-45",
                      )}
                      onClick={() => onToggle(item.id)}
                    >
                      {item.label}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FilterBuilder({
  domains,
  filters,
  focusDomain,
  onChange,
}: {
  domains: Array<{ id: string; label: string }>;
  filters: AnalyticsFilterSpec[];
  focusDomain: string | null;
  onChange: (domain: string, values: string[]) => void;
}) {
  const [draftDomain, setDraftDomain] = React.useState(focusDomain ?? "");
  const extra =
    draftDomain && !filters.some((item) => item.domain === draftDomain)
      ? [{ domain: draftDomain, values: [] as string[] }]
      : [];
  const rows = [...filters, ...extra];
  const labelFor = (id: string) => domains.find((d) => d.id === id)?.label ?? prettyLabel(id);

  function setRowDomain(previous: string, next: string) {
    if (previous && previous !== next) onChange(previous, []);
    setDraftDomain(next);
    if (next) onChange(next, filters.find((item) => item.domain === next)?.values ?? []);
  }

  return (
    <div className="space-y-3">
      {(rows.length ? rows : [{ domain: "", values: [] }]).map((row, index) => (
        <FilterRow
          key={`${row.domain || "new"}-${index}`}
          domains={domains}
          domain={row.domain}
          domainLabel={row.domain ? labelFor(row.domain) : ""}
          selected={row.values}
          filters={filters}
          onDomainChange={(next) => setRowDomain(row.domain, next)}
          onValuesChange={(values) => {
            if (row.domain) onChange(row.domain, values);
          }}
          onRemove={
            row.domain
              ? () => {
                  onChange(row.domain, []);
                  if (draftDomain === row.domain) setDraftDomain("");
                }
              : undefined
          }
        />
      ))}
      <Button
        type="button"
        size="sm"
        variant="secondary"
        onClick={() => {
          const unused = domains.find((item) => !filters.some((filt) => filt.domain === item.id));
          if (unused) setDraftDomain(unused.id);
        }}
      >
        Add filter
      </Button>
    </div>
  );
}

function FilterRow({
  domains,
  domain,
  domainLabel,
  selected,
  filters,
  onDomainChange,
  onValuesChange,
  onRemove,
}: {
  domains: Array<{ id: string; label: string }>;
  domain: string;
  domainLabel: string;
  selected: string[];
  filters: AnalyticsFilterSpec[];
  onDomainChange: (domain: string) => void;
  onValuesChange: (values: string[]) => void;
  onRemove?: () => void;
}) {
  const [fieldQuery, setFieldQuery] = React.useState("");
  const [valueQuery, setValueQuery] = React.useState("");
  const parentRegion = filters.find((f) => f.domain.toLowerCase() === "region");
  const isCity = domain.toLowerCase() === "city";
  const valuesQuery = useFilterValues(domain || null, {
    q: valueQuery || undefined,
    parentDomain: isCity && parentRegion?.values.length ? parentRegion.domain : undefined,
    parentValues: isCity ? parentRegion?.values : undefined,
  });
  const options = valuesQuery.data?.values ?? [];
  const fieldOptions = domains.filter((item) => {
    const needle = fieldQuery.trim().toLowerCase();
    return !needle || `${item.id} ${item.label}`.toLowerCase().includes(needle);
  });

  return (
    <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto]">
      <SearchableMenu
        label="Filter field"
        placeholder="Search fields…"
        display={domain ? domainLabel : "Select field"}
        query={fieldQuery}
        onQuery={setFieldQuery}
      >
        {fieldOptions.map((item) => (
          <button
            key={item.id}
            type="button"
            className={cn("flex w-full px-3 py-1.5 text-left text-sm hover:bg-muted/60", domain === item.id && "bg-info/10 font-medium")}
            onClick={() => {
              onDomainChange(item.id);
              setFieldQuery("");
            }}
          >
            {item.label}
          </button>
        ))}
      </SearchableMenu>
      <SearchableMenu
        label="Values"
        placeholder={domain ? `Search ${domainLabel}…` : "Select a field first"}
        display={
          selected.length
            ? selected.slice(0, 3).join(", ") + (selected.length > 3 ? ` +${selected.length - 3}` : "")
            : domain
              ? "Select values"
              : "—"
        }
        query={valueQuery}
        onQuery={setValueQuery}
        disabled={!domain}
      >
        {valuesQuery.isPending && domain ? (
          <p className="px-3 py-2 text-[11px] text-muted-foreground">Loading values…</p>
        ) : null}
        {valuesQuery.isError ? (
          <p className="px-3 py-2 text-[11px] text-muted-foreground">Values couldn&apos;t be loaded. Try again shortly.</p>
        ) : null}
        {options.map((item) => {
          const active = selected.includes(item.value);
          return (
            <button
              key={item.value}
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-muted/60"
              onClick={() => onValuesChange(active ? selected.filter((v) => v !== item.value) : [...selected, item.value])}
            >
              <span className={cn("flex size-3.5 items-center justify-center rounded border text-[9px]", active ? "border-info bg-info/20" : "border-border")}>
                {active ? "✓" : ""}
              </span>
              <span className="flex-1 truncate">{item.label ?? item.value}</span>
              {item.frequency ? (
                <span className="text-[10px] tabular-nums text-muted-foreground">{item.frequency.toLocaleString("en-IN")}</span>
              ) : null}
            </button>
          );
        })}
        {!options.length && domain && !valuesQuery.isPending && !valuesQuery.isError ? (
          <p className="px-3 py-2 text-[11px] text-muted-foreground">No matching values.</p>
        ) : null}
      </SearchableMenu>
      {onRemove ? (
        <Button type="button" size="sm" variant="ghost" className="mt-5 h-10" onClick={onRemove}>
          Remove
        </Button>
      ) : (
        <span className="hidden md:block" />
      )}
    </div>
  );
}

function SearchableMenu({
  label,
  placeholder,
  display,
  query,
  onQuery,
  disabled,
  children,
}: {
  label: string;
  placeholder: string;
  display: string;
  query: string;
  onQuery: (value: string) => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="relative">
      <p className="mb-1 text-[11px] text-muted-foreground">{label}</p>
      <button
        type="button"
        disabled={disabled}
        className="flex h-10 w-full items-center justify-between rounded-[var(--radius-control)] border border-border bg-background px-3 text-left text-sm disabled:opacity-50"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="truncate">{display}</span>
        <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
      </button>
      {open && !disabled ? (
        <div className="absolute z-30 mt-1 w-full overflow-hidden rounded-xl border border-border/70 bg-surface-raised shadow-lg">
          <div className="border-b border-border/50 p-2">
            <Input autoFocus value={query} onChange={(event) => onQuery(event.target.value)} placeholder={placeholder} className="h-8 text-xs" />
          </div>
          <div className="max-h-48 overflow-y-auto py-1">{children}</div>
        </div>
      ) : null}
    </div>
  );
}

function toChartKind(viz: AnalyticsVizKind, fallback: string | undefined): ChartKind {
  if (viz === "pie" || viz === "donut") return "pie";
  if (viz === "line" || viz === "area" || viz === "scatter" || viz === "bar") return viz;
  if (fallback === "pie" || fallback === "line" || fallback === "area" || fallback === "scatter") return fallback;
  return "bar";
}

function ResultPreview({
  result,
  viz,
  tab,
  filterLabel,
  onFilterValue,
}: {
  result: AnalyticsRunResponse;
  viz: AnalyticsVizKind;
  tab: "chart" | "table" | "narration";
  filterLabel: string | null;
  onFilterValue?: (value: string) => void;
}) {
  const [insightDepth, setInsightDepth] = React.useState<InsightDepth>("executive");
  const meta = result.meta ?? {};
  const metricFormat = typeof meta.metricFormat === "string" ? meta.metricFormat : undefined;
  const notes = Array.isArray(meta.notes) ? (meta.notes as string[]) : [];
  const warnings = Array.isArray(meta.warnings) ? (meta.warnings as string[]) : [];
  const narration = result.insights?.narration
    ? ({
        summary: result.insights.narration.summary,
        highlights: result.insights.narration.highlights ?? [],
        insight: result.insights.narration.insight ?? null,
        focus: result.insights.narration.focus ?? null,
      } as NarrationSections)
    : undefined;

  if (!result.rows.length) {
    return (
      <div className="flex min-h-[240px] flex-col items-center justify-center rounded-xl border border-dashed border-border/70 bg-muted/20 px-4 text-center">
        <p className="text-sm font-medium">No data for this selection</p>
        <p className="mt-1 max-w-sm text-xs text-muted-foreground">
          Widen the date range or remove a filter. {meta.dataAsOf ? `Data runs through ${String(meta.dataAsOf)}.` : ""}
        </p>
      </div>
    );
  }

  if (tab === "narration") {
    const executive = result.insights?.executive;
    if (!executive && !narration) {
      return <p className="py-8 text-center text-sm text-muted-foreground">No insight is available for this result.</p>;
    }
    return (
      <InsightSummary
        executive={executive || narration?.summary || ""}
        analyst={result.insights?.analyst || executive || ""}
        narration={narration}
        depth={insightDepth}
        onDepthChange={setInsightDepth}
      />
    );
  }

  const footer = (
    <>
      {narration ? <InsightCard narration={narration} /> : null}
      {[...warnings, ...notes].length ? (
        <ul className="mt-2 space-y-0.5 text-[11px] text-muted-foreground">
          {[...warnings, ...notes].map((note) => (
            <li key={note} className="flex items-start gap-1.5">
              <Info className="mt-0.5 size-3 shrink-0" />
              {note}
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );

  if (tab === "table" || viz === "table" || !result.chart) {
    if (viz === "kpi" || (!result.chart && result.rows.length === 1)) {
      const key = String(meta.valueColumn ?? result.columns[result.columns.length - 1] ?? "");
      return (
        <div>
          <div className="flex h-[220px] flex-col items-center justify-center rounded-xl bg-gradient-to-b from-info/10 to-transparent">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{result.title}</p>
            <p className="mt-2 text-4xl font-semibold tracking-tight tabular-nums">
              {formatCell(result.rows[0]?.[key], key, metricFormat)}
            </p>
          </div>
          {footer}
        </div>
      );
    }
    const labelCol = filterLabel ? result.columns[0] : null;
    return (
      <div>
        <div className="max-h-[420px] overflow-auto rounded-xl border border-border/50">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-surface-raised">
              <tr>
                {result.columns.map((column) => (
                  <th key={column} className="whitespace-nowrap border-b border-border px-3 py-2 font-semibold">
                    {columnLabel(column)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, index) => (
                <tr
                  key={index}
                  className={cn("odd:bg-muted/20", onFilterValue && labelCol && "cursor-pointer hover:bg-info/10")}
                  onClick={() => {
                    const raw = labelCol ? row[labelCol] : null;
                    if (onFilterValue && raw != null && String(raw)) onFilterValue(String(raw));
                  }}
                  title={onFilterValue && filterLabel ? `Filter ${filterLabel} to this value` : undefined}
                >
                  {result.columns.map((column) => (
                    <td key={column} className="whitespace-nowrap border-b border-border/40 px-3 py-1.5 tabular-nums">
                      {formatCell(row[column], column, metricFormat)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {onFilterValue && filterLabel ? (
            <p className="px-3 py-2 text-[10px] text-muted-foreground">Click a row to focus on that {filterLabel} and re-run.</p>
          ) : null}
        </div>
        {footer}
      </div>
    );
  }

  const chart = result.chart;
  const points = chart.points.length ? chart.points : result.rows;
  const pointKeys = Object.keys(points[0] ?? {});
  if (viz === "heatmap" || viz === "treemap") {
    const Preview = viz === "heatmap" ? HeatmapPreview : TreemapPreview;
    return (
      <div>
        <Preview points={points} labelCol={chart.x} valueCol={chart.y} metricFormat={metricFormat} />
        {footer}
      </div>
    );
  }
  const chartType = toChartKind(viz, chart.type);
  return (
    <div>
      <ResultChart
        rows={points}
        columns={pointKeys}
        xKey={chart.x}
        yKey={chart.y}
        series={chart.series ?? []}
        initialType={chartType}
        hideTypeSelect
        className={cn("w-full", chartType === "pie" && "max-w-xl")}
      />
      {chart.note ? <p className="mt-1 text-[11px] text-muted-foreground">{chart.note}</p> : null}
      {footer}
    </div>
  );
}

function InsightCard({ narration }: { narration: NarrationSections }) {
  return (
    <div className="mt-3 rounded-xl border border-info/25 bg-info/5 px-3 py-2.5 text-sm">
      <p className="flex items-start gap-2 font-medium">
        <Lightbulb className="mt-0.5 size-4 shrink-0 text-info" />
        {narration.summary}
      </p>
      {narration.highlights.length ? (
        <ul className="mt-1.5 list-disc space-y-0.5 pl-10 text-xs text-muted-foreground">
          {narration.highlights.slice(0, 4).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
      {narration.insight ? <p className="mt-1.5 pl-6 text-xs">{narration.insight}</p> : null}
    </div>
  );
}

function HeatmapPreview({
  points,
  labelCol,
  valueCol,
  metricFormat,
}: {
  points: Array<Record<string, unknown>>;
  labelCol: string;
  valueCol: string;
  metricFormat?: string;
}) {
  const max = Math.max(...points.map((row) => Math.abs(Number(row[valueCol]) || 0)), 1);
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
      {points.slice(0, 24).map((row, index) => {
        const intensity = Math.abs(Number(row[valueCol]) || 0) / max;
        return (
          <div
            key={index}
            className="rounded-xl border border-border/50 px-3 py-3 text-xs"
            style={{ background: `color-mix(in oklab, hsl(var(--info)) ${Math.round(intensity * 55)}%, transparent)` }}
          >
            <p className="truncate font-medium">{formatCell(row[labelCol], labelCol)}</p>
            <p className="mt-1 tabular-nums text-muted-foreground">{formatCell(row[valueCol], valueCol, metricFormat)}</p>
          </div>
        );
      })}
    </div>
  );
}

function TreemapPreview({
  points,
  labelCol,
  valueCol,
  metricFormat,
}: {
  points: Array<Record<string, unknown>>;
  labelCol: string;
  valueCol: string;
  metricFormat?: string;
}) {
  const items = points.slice(0, 12).map((row) => ({
    label: formatCell(row[labelCol], labelCol),
    value: Math.abs(Number(row[valueCol]) || 0),
  }));
  const total = items.reduce((sum, item) => sum + item.value, 0) || 1;
  return (
    <div className="flex min-h-[280px] flex-wrap overflow-hidden rounded-xl border border-border/50">
      {items.map((item, index) => (
        <div
          key={`${item.label}-${index}`}
          className="flex min-w-[20%] flex-col justify-end border border-background/40 bg-info/20 p-2 text-xs"
          style={{ flexGrow: Math.max(item.value / total, 0.08), minHeight: 88 }}
        >
          <p className="truncate font-medium">{item.label}</p>
          <p className="tabular-nums text-muted-foreground">{formatCell(item.value, valueCol, metricFormat)}</p>
        </div>
      ))}
    </div>
  );
}

function EmptyPreview({
  starters,
  onPick,
}: {
  starters: Array<{ label: string; spec: AnalyticsSpec }>;
  onPick: (item: { label: string; spec: AnalyticsSpec }) => void;
}) {
  return (
    <div className="flex min-h-[280px] flex-col items-center justify-center rounded-xl border border-dashed border-border/70 bg-muted/20 px-4 py-8 text-center">
      <BarChart3 className="mb-2 size-8 text-muted-foreground/70" />
      <p className="text-sm font-medium">Your insight appears here</p>
      <p className="mt-1 max-w-sm text-xs text-muted-foreground">
        Start with a guided analysis, or compose a metric, dimensions and an analysis on the left.
      </p>
      {starters.length ? (
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {starters.map((item) => (
            <Button key={item.label} type="button" size="sm" variant="secondary" onClick={() => onPick(item)}>
              {item.label}
            </Button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function AnalysisActions({
  result,
  saveTitle,
  onSaveTitle,
  onSave,
  onDuplicate,
  onDelete,
  onExportCsv,
  saving,
}: {
  result: AnalyticsRunResponse | null;
  saveTitle: string;
  onSaveTitle: (value: string) => void;
  onSave: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onExportCsv: () => void;
  saving: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Input
        value={saveTitle}
        onChange={(event) => onSaveTitle(event.target.value)}
        placeholder={result?.title ?? "Analysis name"}
        className="h-8 w-40 text-xs sm:w-52"
      />
      <Button type="button" size="sm" variant="secondary" disabled={saving} onClick={onSave}>
        <Save className="size-3.5" />
        Save
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={onDuplicate}>
        <Copy className="size-3.5" />
        Duplicate
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={onDelete}>
        <Trash2 className="size-3.5" />
        Delete
      </Button>
      <Button type="button" size="sm" variant="ghost" disabled={!result?.rows.length} onClick={onExportCsv}>
        <Download className="size-3.5" />
        CSV
      </Button>
    </div>
  );
}

function SavedList({
  items,
  activeId,
  onLoad,
  loading,
}: {
  items: SavedAnalysis[];
  activeId: string | null;
  onLoad: (item: SavedAnalysis) => void;
  loading: boolean;
}) {
  return (
    <section className="rounded-2xl border border-border/60 bg-surface-raised/70 p-4">
      <h3 className="text-sm font-semibold">Saved analyses</h3>
      <p className="mb-3 text-[11px] text-muted-foreground">Definitions only; reopening re-runs against the latest data.</p>
      {loading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : !items.length ? (
        <p className="text-xs text-muted-foreground">No saved analyses yet.</p>
      ) : (
        <ul className="divide-y divide-border/50">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className={cn(
                  "flex w-full items-center justify-between gap-3 py-2.5 text-left text-sm hover:bg-muted/30",
                  activeId === item.id && "text-primary",
                )}
                onClick={() => onLoad(item)}
              >
                <span className="truncate font-medium">{item.title}</span>
                <span className="shrink-0 text-[10px] text-muted-foreground">{new Date(item.updatedAt).toLocaleDateString()}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
