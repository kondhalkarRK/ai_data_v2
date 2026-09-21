"use client";

import type {
  AnalyticsAnalysisKind,
  AnalyticsFilterSpec,
  AnalyticsRunResponse,
  AnalyticsSpec,
  AnalyticsVizKind,
  SavedAnalysis,
  SemanticPackResponse,
} from "@nql/shared-types";
import {
  BarChart3,
  Boxes,
  Calendar,
  ChevronDown,
  Copy,
  Download,
  FileSpreadsheet,
  FileText,
  Filter,
  Gauge,
  Grid3x3,
  Layers,
  LineChart,
  Link2,
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
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { InsightSummary } from "@/components/chat/insight-summary";
import { ResultChart } from "@/components/chat/result-chart";
import type { InsightDepth } from "@/components/chat/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  EMPTY_SPEC,
  useAnalyticsAssist,
  useAnalyticsRun,
  useFilterValues,
  useSavedAnalyses,
  useSavedAnalysisMutations,
} from "@/hooks/use-analytics";
import {
  DATE_PRESETS,
  type DatePresetId,
  downloadCsv,
  formatDateRangeLabel,
  formatQuerySentence,
  prettyLabel,
  recommendViz,
  resolveDatePreset,
} from "@/lib/analytics/helpers";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const VIZ_OPTIONS: Array<{
  id: AnalyticsVizKind;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { id: "auto", label: "Auto", icon: Sparkles },
  { id: "table", label: "Table", icon: Table2 },
  { id: "bar", label: "Bar", icon: BarChart3 },
  { id: "line", label: "Line", icon: LineChart },
  { id: "area", label: "Area", icon: TrendingUp },
  { id: "pie", label: "Pie", icon: PieChart },
  { id: "donut", label: "Donut", icon: PieChart },
  { id: "scatter", label: "Scatter", icon: BarChart3 },
  { id: "kpi", label: "KPI", icon: Gauge },
  { id: "heatmap", label: "Heatmap", icon: Grid3x3 },
  { id: "treemap", label: "Treemap", icon: Boxes },
];

const COMPOSER_TABS = [
  {
    id: "metrics" as const,
    label: "Metrics",
    hint: "Business measures",
    icon: Gauge,
  },
  {
    id: "dimensions" as const,
    label: "Dimensions",
    hint: "Group and split",
    icon: Layers,
  },
  {
    id: "advanced" as const,
    label: "Advanced Analytics",
    hint: "Ranking, trend, growth",
    icon: SlidersHorizontal,
  },
];

type ComposerTab = (typeof COMPOSER_TABS)[number]["id"];

const DEMO_FILTER_VALUES: Record<string, string[]> = {
  region: ["Mumbai", "Delhi", "Pune", "Bengaluru", "Chennai", "Hyderabad", "Kolkata"],
  city: ["Mumbai", "Navi Mumbai", "Pune", "Thane", "Bengaluru", "Chennai"],
  make: ["Hyundai", "Toyota", "Maruti", "Honda", "Tata", "Kia", "Mahindra"],
  car_type: ["SUV", "Sedan", "Hatchback", "MUV", "EV"],
  colour: ["White", "Silver", "Black", "Red", "Blue"],
  color: ["White", "Silver", "Black", "Red", "Blue"],
  model: ["Creta", "Venue", "Nexon", "City", "Innova", "Swift"],
  dealer_grade: ["Platinum", "Gold", "Silver"],
  claim_status: ["Open", "Paid", "Rejected", "Pending"],
  line_of_business: ["Motor", "Health", "Property", "Life"],
  channel: ["Dealer", "Online", "Broker", "Direct"],
  year: ["2023", "2024", "2025", "2026"],
  quarter: ["Q1", "Q2", "Q3", "Q4"],
  month: ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
};

function demoValuesForDomain(domain: string): Array<{ value: string; label: string }> {
  const listed = DEMO_FILTER_VALUES[domain.toLowerCase()];
  const values = listed ?? [
    `Sample ${prettyLabel(domain)} A`,
    `Sample ${prettyLabel(domain)} B`,
    `Sample ${prettyLabel(domain)} C`,
    `Sample ${prettyLabel(domain)} D`,
  ];
  return values.map((value) => ({ value, label: value }));
}

const ANALYSIS_OPTIONS: Array<{ id: AnalyticsAnalysisKind; label: string; hint: string }> = [
  { id: "basic", label: "Standard", hint: "Grouped aggregation" },
  { id: "breakdown", label: "Breakdown", hint: "Multi-dimension split" },
  { id: "top_n", label: "Top N", hint: "Highest values" },
  { id: "bottom_n", label: "Bottom N", hint: "Lowest values" },
  { id: "ranking", label: "Ranking", hint: "Ordered leaderboard" },
  { id: "contribution", label: "Contribution %", hint: "Share of total" },
  { id: "running_total", label: "Running Total", hint: "Cumulative sum" },
  { id: "moving_average", label: "Moving Average", hint: "Smoothed trend" },
  { id: "period_growth", label: "MoM / YoY", hint: "Period growth %" },
  { id: "trend", label: "Trend", hint: "Over time" },
  { id: "variance", label: "Variance", hint: "Above average" },
];

const PRIMARY_ONLY = new Set<AnalyticsAnalysisKind>([
  "top_n",
  "bottom_n",
  "ranking",
  "contribution",
  "running_total",
  "moving_average",
  "period_growth",
  "trend",
  "variance",
]);

const DIM_GROUP_ORDER = ["Time", "Geography", "Product", "Organization", "Entities"] as const;

type DimOption = { id: string; label: string; group: string };

function classifyDimensionGroup(id: string, fallback: string): string {
  const key = id.toLowerCase();
  if (["month", "quarter", "year", "date"].includes(key)) return "Time";
  if (["region", "city", "state", "state_code", "country"].includes(key)) return "Geography";
  if (
    ["car", "car_type", "make", "model", "colour", "color", "vehicle", "product", "brand"].includes(
      key,
    )
  ) {
    return "Product";
  }
  if (["dealer", "salesperson", "salesman", "channel", "branch"].includes(key)) {
    return "Organization";
  }
  if (fallback === "Time" || fallback === "Geography") return fallback;
  return fallback || "Entities";
}

function buildDimensionOptions(pack: SemanticPackResponse): DimOption[] {
  const options: DimOption[] = [
    { id: "month", label: "Month", group: "Time" },
    { id: "quarter", label: "Quarter", group: "Time" },
    { id: "year", label: "Year", group: "Time" },
  ];
  for (const [key, dim] of Object.entries(pack.model.dimensions)) {
    options.push({
      id: key,
      label: dim.displayName || key,
      group: classifyDimensionGroup(key, "Entities"),
    });
    for (const attr of dim.attributes ?? []) {
      options.push({
        id: attr,
        label: prettyLabel(attr),
        group: classifyDimensionGroup(attr, dim.displayName || "Entities"),
      });
    }
  }
  const seen = new Set<string>();
  return options.filter((item) => {
    if (seen.has(item.id.toLowerCase())) return false;
    seen.add(item.id.toLowerCase());
    return true;
  });
}

function buildFilterDomains(pack: SemanticPackResponse): Array<{ id: string; label: string }> {
  const domains: Array<{ id: string; label: string }> = [];
  const push = (id: string, label: string) => {
    if (!domains.some((d) => d.id === id)) domains.push({ id, label });
  };
  for (const dim of Object.values(pack.model.dimensions)) {
    for (const attr of dim.attributes ?? []) {
      push(attr, prettyLabel(attr));
    }
    if (dim.sourceColumn) {
      push(dim.sourceColumn, dim.displayName);
    }
  }
  for (const id of [
    "region",
    "city",
    "make",
    "car_type",
    "colour",
    "model",
    "dealer_grade",
    "claim_status",
    "line_of_business",
    "channel",
  ]) {
    if (!domains.some((d) => d.id === id)) push(id, prettyLabel(id));
  }
  return domains;
}

function startersForPack(pack: SemanticPackResponse): Array<{ label: string; spec: AnalyticsSpec }> {
  const measures = pack.model.measures;
  const hasRevenue = Boolean(measures.revenue);
  const hasUnits = Boolean(measures.units_sold);
  const hasPremium = Boolean(measures.premium || measures.written_premium);
  const items: Array<{ label: string; spec: AnalyticsSpec }> = [];
  if (hasRevenue) {
    items.push({
      label: "Revenue by Month",
      spec: {
        ...EMPTY_SPEC,
        metrics: ["revenue"],
        dimensions: ["month"],
        analysis: "trend",
        viz: "auto",
      },
    });
    items.push({
      label: "Top dealers",
      spec: {
        ...EMPTY_SPEC,
        metrics: ["revenue"],
        dimensions: ["dealer"],
        analysis: "top_n",
        limit: 10,
        viz: "auto",
      },
    });
  }
  if (hasUnits) {
    items.push({
      label: "Units by Vehicle Type",
      spec: {
        ...EMPTY_SPEC,
        metrics: ["units_sold"],
        dimensions: ["car_type"],
        analysis: "basic",
        viz: "auto",
      },
    });
  }
  if (hasPremium) {
    items.push({
      label: "Premium by Region",
      spec: {
        ...EMPTY_SPEC,
        metrics: [measures.premium ? "premium" : "written_premium"],
        dimensions: ["region"],
        analysis: "basic",
        viz: "auto",
      },
    });
  }
  return items.slice(0, 4);
}

export function AnalyticsBuilderShell({ pack }: { pack: SemanticPackResponse }) {
  const [spec, setSpec] = React.useState<AnalyticsSpec>(EMPTY_SPEC);
  const [aiPrompt, setAiPrompt] = React.useState("");
  const [sqlOpen, setSqlOpen] = React.useState(false);
  const [result, setResult] = React.useState<AnalyticsRunResponse | null>(null);
  const [previewTab, setPreviewTab] = React.useState<"chart" | "table" | "narration">("chart");
  const [error, setError] = React.useState<string | null>(null);
  const [flash, setFlash] = React.useState<string | null>(null);
  const [activeAnalysisId, setActiveAnalysisId] = React.useState<string | null>(null);
  const [saveTitle, setSaveTitle] = React.useState("");
  const [composerTab, setComposerTab] = React.useState<ComposerTab>("metrics");
  const [showFilters, setShowFilters] = React.useState(false);

  const run = useAnalyticsRun();
  const assist = useAnalyticsAssist();
  const saved = useSavedAnalyses();
  const mutations = useSavedAnalysisMutations();

  const measures = React.useMemo(
    () =>
      Object.entries(pack.model.measures).map(([id, measure]) => ({
        id,
        label: measure.displayName,
        synonyms: measure.synonyms ?? [],
      })),
    [pack.model.measures],
  );

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

  const dimensionOptions = React.useMemo(() => buildDimensionOptions(pack), [pack]);
  const filterDomains = React.useMemo(() => buildFilterDomains(pack), [pack]);
  const starters = React.useMemo(() => startersForPack(pack), [pack]);

  const metricLabels = React.useMemo(
    () => Object.fromEntries(measures.map((m) => [m.id, m.label])),
    [measures],
  );
  const dimensionLabels = React.useMemo(
    () => Object.fromEntries(dimensionOptions.map((d) => [d.id, d.label])),
    [dimensionOptions],
  );

  const sentence = formatQuerySentence(spec, {
    metrics: metricLabels,
    dimensions: dimensionLabels,
  });
  const dateLabel = formatDateRangeLabel(spec);
  const dateInvalid = Boolean(
    spec.datePreset === "custom" &&
      spec.dateFrom &&
      spec.dateTo &&
      spec.dateFrom > spec.dateTo,
  );
  const effectiveViz = result?.recommendedViz ?? recommendViz(spec);
  const primaryOnly = PRIMARY_ONLY.has(spec.analysis);
  const ontologyHref = spec.metrics[0]
    ? `/semantic?tab=graph&focus=${encodeURIComponent(spec.metrics[0])}`
    : "/semantic?tab=graph";

  function showFlash(message: string) {
    setFlash(message);
    window.setTimeout(() => setFlash(null), 2400);
  }

  const executeSpec = React.useCallback(
    async (next: AnalyticsSpec) => {
      setError(null);
      try {
        const payload = await run.mutateAsync(next);
        setResult(payload);
        setPreviewTab(next.viz === "table" || next.viz === "kpi" ? "table" : "chart");
      } catch (err) {
        setResult(null);
        setError(err instanceof ApiError ? err.message : "Analysis failed.");
      }
    },
    [run],
  );

  async function handleRun() {
    if (dateInvalid) {
      setError("End date cannot be earlier than start date.");
      return;
    }
    await executeSpec(spec);
  }

  function applyDatePreset(preset: DatePresetId | "") {
    if (!preset) {
      setSpec((prev) => ({
        ...prev,
        datePreset: null,
        dateFrom: null,
        dateTo: null,
      }));
      return;
    }
    const resolved = resolveDatePreset(preset, {
      from: spec.dateFrom,
      to: spec.dateTo,
    });
    setSpec((prev) => ({
      ...prev,
      datePreset: preset,
      dateFrom: resolved.from,
      dateTo: resolved.to,
      timeGrain: resolved.timeGrain ?? prev.timeGrain,
      analysis: resolved.analysis ?? prev.analysis,
    }));
  }

  function handleResetBuilder() {
    setSpec({ ...EMPTY_SPEC });
    setResult(null);
    setError(null);
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
      const next: AnalyticsSpec = {
        ...EMPTY_SPEC,
        ...response.spec,
        metrics: response.spec.metrics ?? [],
        dimensions: response.spec.dimensions ?? [],
        filters: response.spec.filters ?? [],
        analysis: response.spec.analysis ?? "basic",
        limit: response.spec.limit ?? 25,
        orderDirection: response.spec.orderDirection ?? "desc",
        viz: "auto",
      };
      setSpec(next);
      showFlash(response.explanation.slice(0, 120));
      if (next.metrics.length) await executeSpec(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not interpret the prompt.");
    }
  }

  function toggleMetric(id: string) {
    setSpec((prev) => {
      const exists = prev.metrics.includes(id);
      if (!exists && PRIMARY_ONLY.has(prev.analysis) && prev.metrics.length >= 1) {
        return { ...prev, metrics: [id] };
      }
      const metrics = exists
        ? prev.metrics.filter((m) => m !== id)
        : [...prev.metrics, id].slice(0, 3);
      return { ...prev, metrics };
    });
  }

  function toggleDimension(id: string) {
    setSpec((prev) => {
      const exists = prev.dimensions.includes(id);
      const dimensions = exists
        ? prev.dimensions.filter((d) => d !== id)
        : [...prev.dimensions, id].slice(0, 4);
      return { ...prev, dimensions };
    });
  }

  function upsertFilter(domain: string, values: string[]) {
    setSpec((prev) => {
      const rest = prev.filters.filter((f) => f.domain !== domain);
      const filters: AnalyticsFilterSpec[] =
        values.length > 0 ? [...rest, { domain, values, operator: "=" }] : rest;
      return { ...prev, filters };
    });
  }

  async function applyResultFilter(domain: string, value: string) {
    const existing = spec.filters.find((f) => f.domain === domain)?.values ?? [];
    const values = existing.includes(value) ? existing : [...existing, value];
    const next: AnalyticsSpec = {
      ...spec,
      filters: [
        ...spec.filters.filter((f) => f.domain !== domain),
        { domain, values, operator: "=" },
      ],
    };
    setSpec(next);
    await executeSpec(next);
  }

  async function handleSave() {
    const title = saveTitle.trim() || result?.title || "Untitled analysis";
    try {
      if (activeAnalysisId) {
        await mutations.update.mutateAsync({
          id: activeAnalysisId,
          title,
          spec,
          sqlSnapshot: result?.sql ?? null,
          viz: spec.viz,
        });
        showFlash("Analysis updated");
      } else {
        const created = await mutations.create.mutateAsync({
          title,
          spec,
          sqlSnapshot: result?.sql ?? null,
          viz: spec.viz,
        });
        setActiveAnalysisId(created.id);
        setSaveTitle(created.title);
        showFlash("Analysis saved");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save analysis.");
    }
  }

  async function loadSaved(item: SavedAnalysis) {
    const loaded = item.spec as AnalyticsSpec;
    const next: AnalyticsSpec = {
      ...EMPTY_SPEC,
      ...loaded,
      metrics: loaded.metrics ?? [],
      dimensions: loaded.dimensions ?? [],
      filters: loaded.filters ?? [],
    };
    setSpec(next);
    setShowFilters(Boolean(next.filters.length));
    setActiveAnalysisId(item.id);
    setSaveTitle(item.title);
    showFlash(`Loaded “${item.title}”`);
    if (next.metrics.length) await executeSpec(next);
  }

  async function applyStarter(starter: { label: string; spec: AnalyticsSpec }) {
    setSpec(starter.spec);
    setActiveAnalysisId(null);
    await executeSpec(starter.spec);
  }

  const groupedDimensions = React.useMemo(() => {
    const groups = new Map<string, DimOption[]>();
    for (const dim of dimensionOptions) {
      const list = groups.get(dim.group) ?? [];
      list.push(dim);
      groups.set(dim.group, list);
    }
    return DIM_GROUP_ORDER.filter((g) => groups.has(g)).map((g) => ({
      group: g,
      items: groups.get(g) ?? [],
    }));
  }, [dimensionOptions]);

  const filterDomain = spec.dimensions[0] ?? "region";

  return (
    <div className="analytics-builder relative min-h-[70vh]">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -top-6 h-40 bg-[radial-gradient(ellipse_at_top,color-mix(in_oklab,hsl(var(--info))_18%,transparent),transparent_70%)]"
      />

      {flash ? (
        <div className="fixed bottom-6 right-6 z-50 rounded-xl border border-border/60 bg-surface-raised/95 px-4 py-2 text-sm shadow-lg backdrop-blur">
          {flash}
        </div>
      ) : null}

      <section className="relative mb-4 overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-br from-surface-raised via-surface-raised to-info/5 p-4 shadow-[var(--shadow-card)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-info">
              Business analytics
            </p>
            <h2 className="mt-1 text-lg font-semibold tracking-tight">Ask in concepts, not tables</h2>
            <p className="mt-1 max-w-xl text-sm text-muted-foreground">
              Compose metrics, dimensions, and filters from the semantic layer. Joins and SQL stay
              behind the scenes.
            </p>
          </div>
          <Link href={ontologyHref} className="text-xs font-medium text-primary hover:underline">
            Inspect in Ontology →
          </Link>
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
              placeholder='Try “Top selling SUV in Mumbai”'
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

      <div className="relative grid gap-4 lg:grid-cols-[17.5rem_minmax(0,1fr)]">
        <aside className="space-y-2 lg:sticky lg:top-3 lg:self-start">
          <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Configure
          </p>
          <div className="flex flex-col gap-1.5" role="tablist" aria-label="Builder sections">
            {COMPOSER_TABS.map((tab) => {
              const Icon = tab.icon;
              const active = composerTab === tab.id;
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
                  <span>
                    <span className="block text-sm font-semibold text-foreground">{tab.label}</span>
                    <span className="block text-[11px]">{tab.hint}</span>
                  </span>
                </button>
              );
            })}
          </div>

          <section className="rounded-2xl border border-border/60 bg-surface-raised/85 p-3 shadow-sm">
          {composerTab === "metrics" ? (
            <>
              <SelectedPills
                ids={spec.metrics}
                labels={metricLabels}
                onRemove={(id) => toggleMetric(id)}
              />
              {primaryOnly ? (
                <p className="mb-2 text-[10px] text-muted-foreground">
                  Advanced analyses use the first metric.
                </p>
              ) : null}
              <SearchableChips
                items={measures.map((m) => ({
                  id: m.id,
                  label: m.label,
                  keywords: [...m.synonyms, ...(glossaryByMeasure.get(m.id) ?? [])],
                  disabled: primaryOnly && spec.metrics.length >= 1 && !spec.metrics.includes(m.id),
                  title:
                    primaryOnly && spec.metrics.length >= 1 && !spec.metrics.includes(m.id)
                      ? "Advanced analyses use the first metric."
                      : undefined,
                }))}
                selected={spec.metrics}
                onToggle={toggleMetric}
              />
            </>
          ) : null}
          {composerTab === "dimensions" ? (
            <>
              <SelectedPills
                ids={spec.dimensions}
                labels={dimensionLabels}
                onRemove={(id) => toggleDimension(id)}
              />
              <GroupedDimensionChips
                groups={groupedDimensions}
                selected={spec.dimensions}
                onToggle={toggleDimension}
              />
            </>
          ) : null}
          {composerTab === "advanced" ? (
            <>
              <div className="flex flex-wrap gap-1.5">
                {ANALYSIS_OPTIONS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    title={item.hint}
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
                      spec.analysis === item.id
                        ? "border-info/40 bg-info/15 text-foreground"
                        : "border-transparent bg-muted/40 text-muted-foreground hover:bg-muted",
                    )}
                    onClick={() =>
                      setSpec((prev) => ({
                        ...prev,
                        analysis: item.id,
                        metrics: PRIMARY_ONLY.has(item.id) ? prev.metrics.slice(0, 1) : prev.metrics,
                      }))
                    }
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <div className="mt-3 flex items-center gap-2">
                <label className="text-[11px] text-muted-foreground" htmlFor="limit">
                  Limit
                </label>
                <Input
                  id="limit"
                  type="number"
                  min={1}
                  max={500}
                  value={spec.limit}
                  onChange={(event) =>
                    setSpec((prev) => ({
                      ...prev,
                      limit: Math.min(500, Math.max(1, Number(event.target.value) || 25)),
                    }))
                  }
                  className="h-8 w-20 text-xs"
                />
              </div>
            </>
          ) : null}
        </section>
        </aside>

        <div className="min-w-0 space-y-4">
        <section className="rounded-2xl border border-border/60 bg-surface-raised/85 p-3 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex min-w-[220px] flex-1 items-center gap-2 text-[11px] text-muted-foreground">
              <Calendar className="size-3.5 shrink-0" />
              <span className="sr-only">Date filter</span>
              <select
                className="h-10 w-full rounded-[var(--radius-control)] border border-border bg-background px-2 text-sm text-foreground"
                value={spec.datePreset ?? ""}
                onChange={(event) => applyDatePreset(event.target.value as DatePresetId | "")}
                aria-label="Date filter"
              >
                <option value="">Date filter</option>
                {DATE_PRESETS.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <Button
              type="button"
              variant="secondary"
              className="h-10"
              onClick={() => setShowFilters((open) => !open)}
            >
              <Filter className="size-3.5" />
              {showFilters ? "Hide Filters" : spec.filters.length ? `Filters (${spec.filters.length})` : "Show Filters"}
            </Button>
            <Button type="button" variant="ghost" className="h-10" onClick={handleResetBuilder}>
              <RotateCcw className="size-3.5" />
              Clear Analytics
            </Button>
          </div>

          {spec.datePreset === "custom" ? (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <label className="text-[11px] text-muted-foreground">
                Start Date
                <Input
                  type="date"
                  className="mt-1 h-10"
                  value={spec.dateFrom ?? ""}
                  onChange={(event) =>
                    setSpec((prev) => ({ ...prev, dateFrom: event.target.value || null }))
                  }
                />
              </label>
              <label className="text-[11px] text-muted-foreground">
                End Date
                <Input
                  type="date"
                  className="mt-1 h-10"
                  min={spec.dateFrom ?? undefined}
                  value={spec.dateTo ?? ""}
                  onChange={(event) =>
                    setSpec((prev) => ({ ...prev, dateTo: event.target.value || null }))
                  }
                />
              </label>
              {dateInvalid ? (
                <p className="text-[11px] text-danger sm:col-span-2">
                  End date cannot be earlier than start date.
                </p>
              ) : null}
            </div>
          ) : null}

          {showFilters ? (
            <div className="mt-3 border-t border-border/50 pt-3">
              <FilterBuilder domains={filterDomains} filters={spec.filters} onChange={upsertFilter} />
            </div>
          ) : null}
        </section>

        <section className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-surface-raised/90 p-4 shadow-sm md:flex-row md:items-center md:justify-between">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-info">Query summary</p>
            <p className="mt-1 text-sm font-medium leading-snug">{sentence}</p>
            <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
              <SummaryChip
                label="Metrics"
                value={
                  spec.metrics.map((id) => metricLabels[id] ?? prettyLabel(id)).join(", ") || "None"
                }
              />
              <SummaryChip
                label="Dimensions"
                value={
                  spec.dimensions.map((id) => dimensionLabels[id] ?? prettyLabel(id)).join(", ") ||
                  "None"
                }
              />
              <SummaryChip
                label="Date"
                value={dateLabel || "All time"}
              />
              <SummaryChip
                label="Filters"
                value={
                  spec.filters
                    .map((item) => `${prettyLabel(item.domain)}: ${item.values.join(", ")}`)
                    .join(" · ") || "None"
                }
              />
              <SummaryChip
                label="Advanced"
                value={`${ANALYSIS_OPTIONS.find((item) => item.id === spec.analysis)?.label ?? spec.analysis} · ${spec.limit}`}
              />
            </div>
          </div>
          <Button
            type="button"
            className="h-12 shrink-0 px-6 text-sm"
            disabled={run.isPending || spec.metrics.length === 0 || dateInvalid}
            onClick={() => void handleRun()}
          >
            {run.isPending ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
            Run Query
          </Button>
        </section>

        <main className="space-y-3">
          <div className="rounded-2xl border border-border/60 bg-surface-raised/80 p-4 shadow-[var(--shadow-card)] backdrop-blur">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-base font-semibold tracking-tight">
                  {result?.title ?? "Chart / table preview"}
                </h3>
                <p className="text-xs text-muted-foreground">
                  {result
                    ? `${result.rows.length} rows · ${sentence}`
                    : "Configure metrics and dimensions, then run — or pick a starter."}
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
                onStub={(label) => showFlash(`${label} — coming soon`)}
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
                      onClick={() =>
                        upsertFilter(
                          filt.domain,
                          filt.values.filter((entry) => entry !== value),
                        )
                      }
                    >
                      {filt.domain}={value} ×
                    </button>
                  )),
                )}
              </div>
            ) : null}

            {error ? (
              <p className="mt-4 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
                {error}
              </p>
            ) : null}

            <div className="mt-4 min-h-[320px] w-full">
              {result || run.isPending ? (
                <div
                  className="mb-3 flex w-full gap-1 overflow-x-auto rounded-xl border border-border/60 bg-muted/25 p-1"
                  role="toolbar"
                  aria-label="Visualization"
                >
                  {VIZ_OPTIONS.filter((item) => item.id !== "auto").map((item) => {
                    const Icon = item.icon;
                    const active =
                      spec.viz === item.id ||
                      (spec.viz === "auto" && effectiveViz === item.id && previewTab !== "narration");
                    return (
                      <button
                        key={item.id}
                        type="button"
                        className={cn(
                          "inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium",
                          active
                            ? "bg-background text-foreground shadow-sm"
                            : "text-muted-foreground hover:bg-background/60",
                        )}
                        onClick={() => {
                          setSpec((prev) => ({ ...prev, viz: item.id }));
                          setPreviewTab(item.id === "table" || item.id === "kpi" ? "table" : "chart");
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
                      previewTab === "narration"
                        ? "bg-background text-foreground shadow-sm"
                        : "text-muted-foreground hover:bg-background/60",
                    )}
                    onClick={() => setPreviewTab("narration")}
                  >
                    Narration
                  </button>
                </div>
              ) : null}
              {!result && !run.isPending ? (
                <EmptyPreview starters={starters} onPick={(item) => void applyStarter(item)} />
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
                  filterDomain={filterDomain}
                  onFilterValue={(value) => void applyResultFilter(filterDomain, value)}
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
              <ChevronDown
                className={cn("size-4 text-muted-foreground transition-transform", sqlOpen && "rotate-180")}
              />
            </button>
            {sqlOpen ? (
              <pre className="overflow-x-auto border-t border-border/50 bg-surface-sunken/40 px-4 py-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
                {result?.sql ?? "Run an analysis to inspect the generated SQL."}
              </pre>
            ) : null}
          </div>

          <SavedList
            items={saved.data ?? []}
            activeId={activeAnalysisId}
            onLoad={(item) => void loadSaved(item)}
            loading={saved.isPending}
          />
        </main>
        </div>
      </div>
    </div>
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
  items: Array<{
    id: string;
    label: string;
    keywords?: string[];
    disabled?: boolean;
    title?: string;
  }>;
  selected: string[];
  onToggle: (id: string) => void;
}) {
  const [q, setQ] = React.useState("");
  const filtered = items.filter((item) => {
    const needle = q.trim().toLowerCase();
    if (!needle) return true;
    const hay = [item.id, item.label, ...(item.keywords ?? [])].join(" ").toLowerCase();
    return hay.includes(needle);
  });

  return (
    <div>
      <div className="relative mb-2">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="Search…"
          className="h-8 pl-8 text-xs"
        />
      </div>
      <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto">
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
                item.disabled && "cursor-not-allowed opacity-40",
              )}
              onClick={() => onToggle(item.id)}
            >
              {item.label}
            </button>
          );
        })}
        {!filtered.length ? <p className="text-[11px] text-muted-foreground">No matches.</p> : null}
      </div>
    </div>
  );
}

function GroupedDimensionChips({
  groups,
  selected,
  onToggle,
}: {
  groups: Array<{ group: string; items: DimOption[] }>;
  selected: string[];
  onToggle: (id: string) => void;
}) {
  const [q, setQ] = React.useState("");
  return (
    <div>
      <div className="relative mb-2">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="Search dimensions…"
          className="h-8 pl-8 text-xs"
        />
      </div>
      <div className="max-h-52 space-y-2 overflow-y-auto">
        {groups.map(({ group, items }) => {
          const visible = items.filter((item) => {
            const needle = q.trim().toLowerCase();
            if (!needle) return true;
            return `${item.id} ${item.label} ${group}`.toLowerCase().includes(needle);
          });
          if (!visible.length) return null;
          return (
            <div key={group}>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {group}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {visible.map((item) => {
                  const active = selected.includes(item.id);
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={cn(
                        "rounded-full border px-2.5 py-1 text-[11px] font-medium",
                        active
                          ? "border-success/40 bg-success/15 text-foreground"
                          : "border-border/50 bg-background/50 text-muted-foreground hover:bg-muted/50",
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
  onChange,
}: {
  domains: Array<{ id: string; label: string }>;
  filters: AnalyticsFilterSpec[];
  onChange: (domain: string, values: string[]) => void;
}) {
  const [draftDomain, setDraftDomain] = React.useState("");
  const extra =
    draftDomain && !filters.some((item) => item.domain === draftDomain)
      ? [{ domain: draftDomain, values: [] as string[] }]
      : [];
  const rows = [...filters, ...extra];

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
  selected,
  filters,
  onDomainChange,
  onValuesChange,
  onRemove,
}: {
  domains: Array<{ id: string; label: string }>;
  domain: string;
  selected: string[];
  filters: AnalyticsFilterSpec[];
  onDomainChange: (domain: string) => void;
  onValuesChange: (values: string[]) => void;
  onRemove?: () => void;
}) {
  const [fieldQuery, setFieldQuery] = React.useState("");
  const [valueQuery, setValueQuery] = React.useState("");
  const parentRegion = filters.find((f) => f.domain === "region");
  const valuesQuery = useFilterValues(domain || null, {
    q: valueQuery || undefined,
    parentDomain: domain === "city" && parentRegion?.values.length ? "region" : undefined,
    parentValues: domain === "city" ? parentRegion?.values : undefined,
  });
  const live = valuesQuery.data?.values ?? [];
  const demo = domain ? demoValuesForDomain(domain) : [];
  const options = (live.length ? live : demo).filter((item) => {
    const needle = valueQuery.trim().toLowerCase();
    if (!needle) return true;
    return `${item.value} ${item.label ?? ""}`.toLowerCase().includes(needle);
  });
  const fieldOptions = domains.filter((item) => {
    const needle = fieldQuery.trim().toLowerCase();
    if (!needle) return true;
    return `${item.id} ${item.label}`.toLowerCase().includes(needle);
  });

  return (
    <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto]">
      <SearchableMenu
        label="Filter field"
        placeholder="Search fields…"
        display={domain ? prettyLabel(domain) : "Select field"}
        query={fieldQuery}
        onQuery={setFieldQuery}
      >
        {fieldOptions.map((item) => (
          <button
            key={item.id}
            type="button"
            className={cn(
              "flex w-full px-3 py-1.5 text-left text-sm hover:bg-muted/60",
              domain === item.id && "bg-info/10 font-medium",
            )}
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
        label="Value"
        placeholder={domain ? `Search ${prettyLabel(domain)}…` : "Select a field first"}
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
        {valuesQuery.isPending && !live.length ? (
          <p className="px-3 py-2 text-[11px] text-muted-foreground">Loading values…</p>
        ) : null}
        {options.map((item) => {
          const active = selected.includes(item.value);
          return (
            <button
              key={item.value}
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-muted/60"
              onClick={() => {
                const next = active
                  ? selected.filter((value) => value !== item.value)
                  : [...selected, item.value];
                onValuesChange(next);
              }}
            >
              <span
                className={cn(
                  "flex size-3.5 items-center justify-center rounded border text-[9px]",
                  active ? "border-info bg-info/20" : "border-border",
                )}
              >
                {active ? "✓" : ""}
              </span>
              {item.label ?? item.value}
            </button>
          );
        })}
        {!options.length && domain ? (
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
            <Input
              autoFocus
              value={query}
              onChange={(event) => onQuery(event.target.value)}
              placeholder={placeholder}
              className="h-8 text-xs"
            />
          </div>
          <div className="max-h-48 overflow-y-auto py-1">{children}</div>
        </div>
      ) : null}
    </div>
  );
}

function ResultPreview({
  result,
  viz,
  tab,
  filterDomain,
  onFilterValue,
}: {
  result: AnalyticsRunResponse;
  viz: AnalyticsVizKind;
  tab: "chart" | "table" | "narration";
  filterDomain: string;
  onFilterValue: (value: string) => void;
}) {
  const [insightDepth, setInsightDepth] = React.useState<InsightDepth>("executive");

  if (tab === "narration") {
    const executive = result.insights?.executive;
    const analyst = result.insights?.analyst;
    if (!executive && !analyst) {
      return (
        <p className="py-8 text-center text-sm text-muted-foreground">
          Narration will appear after the analysis runs.
        </p>
      );
    }
    return (
      <InsightSummary
        executive={executive || ""}
        analyst={analyst || executive || ""}
        depth={insightDepth}
        onDepthChange={setInsightDepth}
      />
    );
  }

  if (tab === "chart" && viz === "heatmap") {
    return <HeatmapPreview result={result} />;
  }
  if (tab === "chart" && viz === "treemap") {
    return <TreemapPreview result={result} />;
  }

  if (tab === "table" || viz === "table" || viz === "kpi") {
    if (viz === "kpi" && tab !== "table") {
      const key = result.columns[0] ?? "";
      const value = key ? result.rows[0]?.[key] : undefined;
      return (
        <div className="flex h-[240px] flex-col items-center justify-center rounded-xl bg-gradient-to-b from-info/10 to-transparent">
          <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{result.title}</p>
          <p className="mt-2 text-4xl font-semibold tracking-tight tabular-nums">
            {formatValue(value)}
          </p>
        </div>
      );
    }
    const labelCol = result.columns[0] ?? "";
    return (
      <div className="max-h-[420px] overflow-auto rounded-xl border border-border/50">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-surface-raised">
            <tr>
              {result.columns.map((column) => (
                <th key={column} className="border-b border-border px-3 py-2 font-semibold">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, index) => (
              <tr
                key={index}
                className="cursor-pointer odd:bg-muted/20 hover:bg-info/10"
                onClick={() => {
                  const raw = row[labelCol];
                  if (raw != null && String(raw)) onFilterValue(String(raw));
                }}
                title={`Filter ${filterDomain} to this value`}
              >
                {result.columns.map((column) => (
                  <td key={column} className="border-b border-border/40 px-3 py-1.5 tabular-nums">
                    {formatValue(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="px-3 py-2 text-[10px] text-muted-foreground">
          Click a row to add a {prettyLabel(filterDomain)} filter and re-run.
        </p>
      </div>
    );
  }

  const chartType =
    viz === "donut" || viz === "pie"
      ? "pie"
      : viz === "line" || viz === "area"
        ? viz === "area"
          ? "area"
          : "line"
        : viz === "scatter"
          ? "scatter"
          : "bar";

  const labelCol = result.chart?.x ?? result.columns[0] ?? "";

  return (
    <div>
      <ResultChart
        rows={result.rows}
        columns={result.columns}
        xKey={labelCol}
        yKey={result.chart?.y ?? result.columns[1] ?? result.columns[0] ?? ""}
        initialType={chartType}
        hideTypeSelect
        className={cn("w-full", chartType === "pie" && "max-w-xl")}
      />
      <div className="mt-2 flex flex-wrap gap-1">
        {result.rows.slice(0, 12).map((row, index) => {
          const value = String(row[labelCol] ?? "");
          if (!value) return null;
          return (
            <button
              key={`${value}-${index}`}
              type="button"
              className="rounded-full border border-border/50 px-2 py-0.5 text-[10px] text-muted-foreground hover:bg-muted/50"
              onClick={() => onFilterValue(value)}
            >
              Filter {value}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function HeatmapPreview({ result }: { result: AnalyticsRunResponse }) {
  const labelCol = result.columns[0] ?? "";
  const valueCol = result.columns[1] ?? result.columns[0] ?? "";
  const nums = result.rows.map((row) => Number(valueCol ? row[valueCol] : 0) || 0);
  const max = Math.max(...nums, 1);
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
      {result.rows.slice(0, 24).map((row, index) => {
        const intensity = (Number(row[valueCol]) || 0) / max;
        return (
          <div
            key={index}
            className="rounded-xl border border-border/50 px-3 py-3 text-xs"
            style={{
              background: `color-mix(in oklab, hsl(var(--info)) ${Math.round(intensity * 55)}%, transparent)`,
            }}
          >
            <p className="truncate font-medium">{String(row[labelCol] ?? "—")}</p>
            <p className="mt-1 tabular-nums text-muted-foreground">{formatValue(row[valueCol])}</p>
          </div>
        );
      })}
    </div>
  );
}

function TreemapPreview({ result }: { result: AnalyticsRunResponse }) {
  const labelCol = result.columns[0] ?? "";
  const valueCol = result.columns[1] ?? result.columns[0] ?? "";
  const items = result.rows.slice(0, 12).map((row) => ({
    label: String((labelCol ? row[labelCol] : undefined) ?? "—"),
    value: Math.abs(Number(valueCol ? row[valueCol] : 0) || 0),
  }));
  const total = items.reduce((sum, item) => sum + item.value, 0) || 1;
  return (
    <div className="flex min-h-[280px] flex-wrap overflow-hidden rounded-xl border border-border/50">
      {items.map((item) => (
        <div
          key={item.label}
          className="flex min-w-[20%] flex-col justify-end border border-background/40 bg-info/20 p-2 text-xs"
          style={{ flexGrow: Math.max(item.value / total, 0.08), minHeight: 88 }}
        >
          <p className="truncate font-medium">{item.label}</p>
          <p className="tabular-nums text-muted-foreground">{formatValue(item.value)}</p>
        </div>
      ))}
    </div>
  );
}

function formatValue(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(value);
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
        Start with a guided analysis, or compose metrics, dimensions, and filters above.
      </p>
      {starters.length ? (
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {starters.map((item) => (
            <Button
              key={item.label}
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => onPick(item)}
            >
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
  onStub,
  saving,
}: {
  result: AnalyticsRunResponse | null;
  saveTitle: string;
  onSaveTitle: (value: string) => void;
  onSave: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onExportCsv: () => void;
  onStub: (label: string) => void;
  saving: boolean;
}) {
  const [exportOpen, setExportOpen] = React.useState(false);

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
      <div className="relative">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => setExportOpen((value) => !value)}
        >
          <Download className="size-3.5" />
          Export
        </Button>
        {exportOpen ? (
          <div className="absolute right-0 z-20 mt-1 min-w-[160px] overflow-hidden rounded-xl border border-border/70 bg-surface-raised py-1 shadow-lg">
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-muted/50"
              onClick={() => {
                onExportCsv();
                setExportOpen(false);
              }}
            >
              <Download className="size-3.5" />
              CSV
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-muted/50"
              onClick={() => {
                onStub("Share link");
                setExportOpen(false);
              }}
            >
              <Link2 className="size-3.5" />
              Share link
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-muted/50"
              onClick={() => {
                onStub("Excel export");
                setExportOpen(false);
              }}
            >
              <FileSpreadsheet className="size-3.5" />
              Excel
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-muted/50"
              onClick={() => {
                onStub("PDF export");
                setExportOpen(false);
              }}
            >
              <FileText className="size-3.5" />
              PDF
            </button>
          </div>
        ) : null}
      </div>
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
      <p className="mb-3 text-[11px] text-muted-foreground">
        Metadata only — reopen and re-run anytime.
      </p>
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
                <span className="shrink-0 text-[10px] text-muted-foreground">
                  {new Date(item.updatedAt).toLocaleDateString()}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
