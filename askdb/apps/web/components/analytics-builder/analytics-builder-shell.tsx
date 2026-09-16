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
  ChevronDown,
  Copy,
  Download,
  FileSpreadsheet,
  FileText,
  LineChart,
  Link2,
  Loader2,
  PieChart,
  Play,
  Save,
  Search,
  Sparkles,
  Table2,
  Trash2,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { ResultChart } from "@/components/chat/result-chart";
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
import { downloadCsv, recommendViz } from "@/lib/analytics/helpers";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const VIZ_OPTIONS: Array<{ id: AnalyticsVizKind; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { id: "auto", label: "Auto", icon: Sparkles },
  { id: "table", label: "Table", icon: Table2 },
  { id: "bar", label: "Bar", icon: BarChart3 },
  { id: "line", label: "Line", icon: LineChart },
  { id: "area", label: "Area", icon: TrendingUp },
  { id: "pie", label: "Pie", icon: PieChart },
  { id: "donut", label: "Donut", icon: PieChart },
  { id: "scatter", label: "Scatter", icon: BarChart3 },
  { id: "kpi", label: "KPI", icon: TrendingUp },
];

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

type DimOption = { id: string; label: string; group: string };

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
      group: "Entities",
    });
    for (const attr of dim.attributes ?? []) {
      options.push({
        id: attr,
        label: attr.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        group: dim.displayName || key,
      });
    }
  }
  // Dedupe by id keeping first
  const seen = new Set<string>();
  return options.filter((item) => {
    if (seen.has(item.id.toLowerCase())) return false;
    seen.add(item.id.toLowerCase());
    return true;
  });
}

function buildFilterDomains(pack: SemanticPackResponse): Array<{ id: string; label: string }> {
  // Prefer value-domain style labels from common pack attributes
  const domains: Array<{ id: string; label: string }> = [];
  const push = (id: string, label: string) => {
    if (!domains.some((d) => d.id === id)) domains.push({ id, label });
  };
  for (const dim of Object.values(pack.model.dimensions)) {
    for (const attr of dim.attributes ?? []) {
      push(attr, attr.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()));
    }
    if (dim.sourceColumn) {
      push(dim.sourceColumn, dim.displayName);
    }
  }
  // Canonical automotive/insurance domains
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
    if (!domains.some((d) => d.id === id)) {
      push(id, id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()));
    }
  }
  return domains;
}

export function AnalyticsBuilderShell({ pack }: { pack: SemanticPackResponse }) {
  const [spec, setSpec] = React.useState<AnalyticsSpec>(EMPTY_SPEC);
  const [aiPrompt, setAiPrompt] = React.useState("");
  const [sqlOpen, setSqlOpen] = React.useState(false);
  const [result, setResult] = React.useState<AnalyticsRunResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [flash, setFlash] = React.useState<string | null>(null);
  const [activeAnalysisId, setActiveAnalysisId] = React.useState<string | null>(null);
  const [saveTitle, setSaveTitle] = React.useState("");

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

  const effectiveViz = result?.recommendedViz ?? recommendViz(spec);

  function showFlash(message: string) {
    setFlash(message);
    window.setTimeout(() => setFlash(null), 2400);
  }

  async function handleRun() {
    setError(null);
    try {
      const payload = await run.mutateAsync(spec);
      setResult(payload);
      if (spec.viz === "auto") {
        setSpec((prev) => ({ ...prev, viz: "auto" }));
      }
    } catch (err) {
      setResult(null);
      setError(err instanceof ApiError ? err.message : "Analysis failed.");
    }
  }

  async function handleAssist() {
    if (!aiPrompt.trim()) return;
    setError(null);
    try {
      const response = await assist.mutateAsync(aiPrompt.trim());
      setSpec({
        ...EMPTY_SPEC,
        ...response.spec,
        metrics: response.spec.metrics ?? [],
        dimensions: response.spec.dimensions ?? [],
        filters: response.spec.filters ?? [],
        analysis: response.spec.analysis ?? "basic",
        limit: response.spec.limit ?? 25,
        orderDirection: response.spec.orderDirection ?? "desc",
        viz: "auto",
      });
      showFlash(response.explanation.slice(0, 120));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not interpret the prompt.");
    }
  }

  function toggleMetric(id: string) {
    setSpec((prev) => {
      const exists = prev.metrics.includes(id);
      const metrics = exists ? prev.metrics.filter((m) => m !== id) : [...prev.metrics, id].slice(0, 3);
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

  function loadSaved(item: SavedAnalysis) {
    const loaded = item.spec as AnalyticsSpec;
    setSpec({
      ...EMPTY_SPEC,
      ...loaded,
      metrics: loaded.metrics ?? [],
      dimensions: loaded.dimensions ?? [],
      filters: loaded.filters ?? [],
    });
    setActiveAnalysisId(item.id);
    setSaveTitle(item.title);
    setResult(null);
    showFlash(`Loaded “${item.title}”`);
  }

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
          <Link
            href="/semantic/ontology"
            className="text-xs font-medium text-primary hover:underline"
          >
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

      <div className="relative grid gap-4 lg:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
        <aside className="space-y-3">
          <ConfigCard title="Metrics" subtitle="Select one or more business measures">
            <SearchableChips
              items={measures.map((m) => ({
                id: m.id,
                label: m.label,
                keywords: [...m.synonyms, ...(glossaryByMeasure.get(m.id) ?? [])],
              }))}
              selected={spec.metrics}
              onToggle={toggleMetric}
            />
          </ConfigCard>

          <ConfigCard title="Dimensions" subtitle="Primary breakdown and secondary cuts">
            <SearchableChips
              items={dimensionOptions.map((d) => ({
                id: d.id,
                label: d.label,
                keywords: [d.group],
              }))}
              selected={spec.dimensions}
              onToggle={toggleDimension}
            />
          </ConfigCard>

          <ConfigCard title="Filters" subtitle="Value dictionary · cascading where available">
            <FilterBuilder
              domains={filterDomains}
              filters={spec.filters}
              onChange={upsertFilter}
            />
          </ConfigCard>

          <ConfigCard title="Advanced analytics" subtitle="No SQL required">
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
                  onClick={() => setSpec((prev) => ({ ...prev, analysis: item.id }))}
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
          </ConfigCard>

          <ConfigCard title="Visualization" subtitle="Auto-recommended from your selection">
            <div className="flex flex-wrap gap-1.5">
              {VIZ_OPTIONS.map((item) => {
                const Icon = item.icon;
                const active = spec.viz === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium",
                      active
                        ? "border-primary/40 bg-primary/15 text-foreground"
                        : "border-transparent bg-muted/40 text-muted-foreground hover:bg-muted",
                    )}
                    onClick={() => setSpec((prev) => ({ ...prev, viz: item.id }))}
                  >
                    <Icon className="size-3" />
                    {item.label}
                  </button>
                );
              })}
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Suggested: <span className="font-medium text-foreground">{recommendViz({ ...spec, viz: "auto" })}</span>
            </p>
          </ConfigCard>

          <Button
            type="button"
            className="h-11 w-full text-sm"
            disabled={run.isPending || spec.metrics.length === 0}
            onClick={() => void handleRun()}
          >
            {run.isPending ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
            Run analysis
          </Button>
        </aside>

        <main className="space-y-3">
          <div className="rounded-2xl border border-border/60 bg-surface-raised/80 p-4 shadow-[var(--shadow-card)] backdrop-blur">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-base font-semibold tracking-tight">
                  {result?.title ?? "Chart / table preview"}
                </h3>
                <p className="text-xs text-muted-foreground">
                  {result
                    ? `${result.rows.length} rows · ${String(result.meta.path ?? "semantic")}`
                    : "Configure metrics and dimensions, then run."}
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
                  downloadCsv(
                    `analysis-${Date.now()}.csv`,
                    result.columns,
                    result.rows,
                  );
                  showFlash("CSV downloaded");
                }}
                onStub={(label) => showFlash(`${label} — coming soon`)}
                saving={mutations.create.isPending || mutations.update.isPending}
              />
            </div>

            {error ? (
              <p className="mt-4 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
                {error}
              </p>
            ) : null}

            <div className="mt-4 min-h-[280px]">
              {!result && !run.isPending ? (
                <EmptyPreview />
              ) : run.isPending ? (
                <div className="flex h-[280px] items-center justify-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  Compiling governed SQL and running…
                </div>
              ) : result ? (
                <ResultPreview result={result} viz={spec.viz === "auto" ? effectiveViz : spec.viz} />
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
            onLoad={loadSaved}
            loading={saved.isPending}
          />
        </main>
      </div>
    </div>
  );
}

function ConfigCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-border/60 bg-surface-raised/85 p-3 shadow-sm backdrop-blur">
      <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
      <p className="mb-2 text-[11px] text-muted-foreground">{subtitle}</p>
      {children}
    </section>
  );
}

function SearchableChips({
  items,
  selected,
  onToggle,
}: {
  items: Array<{ id: string; label: string; keywords?: string[] }>;
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
              className={cn(
                "rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
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
        {!filtered.length ? (
          <p className="text-[11px] text-muted-foreground">No matches.</p>
        ) : null}
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
  const [domain, setDomain] = React.useState(domains[0]?.id ?? "region");
  const [q, setQ] = React.useState("");
  const parentRegion = filters.find((f) => f.domain === "region");
  const valuesQuery = useFilterValues(domain, {
    q: q || undefined,
    parentDomain: domain === "city" && parentRegion?.values.length ? "region" : undefined,
    parentValues: domain === "city" ? parentRegion?.values : undefined,
  });
  const selected = filters.find((f) => f.domain === domain)?.values ?? [];

  return (
    <div className="space-y-2">
      <select
        className="h-8 w-full rounded-[var(--radius-control)] border border-border bg-background px-2 text-xs"
        value={domain}
        onChange={(event) => setDomain(event.target.value)}
        aria-label="Filter domain"
      >
        {domains.map((item) => (
          <option key={item.id} value={item.id}>
            {item.label}
          </option>
        ))}
      </select>
      <Input
        value={q}
        onChange={(event) => setQ(event.target.value)}
        placeholder="Search values…"
        className="h-8 text-xs"
      />
      <div className="flex max-h-32 flex-wrap gap-1 overflow-y-auto">
        {(valuesQuery.data?.values ?? []).map((item) => {
          const active = selected.includes(item.value);
          return (
            <button
              key={item.value}
              type="button"
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px] font-medium",
                active
                  ? "border-info/40 bg-info/15 text-foreground"
                  : "border-border/40 text-muted-foreground hover:bg-muted/40",
              )}
              onClick={() => {
                const next = active
                  ? selected.filter((value) => value !== item.value)
                  : [...selected, item.value];
                onChange(domain, next);
              }}
            >
              {item.label ?? item.value}
            </button>
          );
        })}
        {valuesQuery.isPending ? (
          <span className="text-[11px] text-muted-foreground">Loading values…</span>
        ) : null}
        {valuesQuery.isError ? (
          <span className="text-[11px] text-danger">Could not load values for this domain.</span>
        ) : null}
      </div>
      {filters.length ? (
        <div className="flex flex-wrap gap-1 pt-1">
          {filters.flatMap((filt) =>
            filt.values.map((value) => (
              <span
                key={`${filt.domain}-${value}`}
                className="inline-flex items-center gap-1 rounded-full bg-muted/60 px-2 py-0.5 text-[10px]"
              >
                {filt.domain}={value}
                <button
                  type="button"
                  className="text-muted-foreground hover:text-foreground"
                  aria-label={`Remove ${value}`}
                  onClick={() =>
                    onChange(
                      filt.domain,
                      filt.values.filter((entry) => entry !== value),
                    )
                  }
                >
                  ×
                </button>
              </span>
            )),
          )}
        </div>
      ) : null}
    </div>
  );
}

function ResultPreview({
  result,
  viz,
}: {
  result: AnalyticsRunResponse;
  viz: AnalyticsVizKind;
}) {
  if (viz === "kpi") {
    const key = result.columns[0];
    const value = result.rows[0]?.[key];
    return (
      <div className="flex h-[240px] flex-col items-center justify-center rounded-xl bg-gradient-to-b from-info/10 to-transparent">
        <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{result.title}</p>
        <p className="mt-2 text-4xl font-semibold tracking-tight tabular-nums">
          {formatValue(value)}
        </p>
      </div>
    );
  }

  if (viz === "table" || result.columns.length > 3) {
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
              <tr key={index} className="odd:bg-muted/20">
                {result.columns.map((column) => (
                  <td key={column} className="border-b border-border/40 px-3 py-1.5 tabular-nums">
                    {formatValue(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
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

  return (
    <ResultChart
      rows={result.rows}
      columns={result.columns}
      xKey={result.chart?.x ?? result.columns[0] ?? ""}
      yKey={result.chart?.y ?? result.columns[1] ?? result.columns[0] ?? ""}
      initialType={chartType}
      className={cn(chartType === "pie" && "max-w-md")}
    />
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

function EmptyPreview() {
  return (
    <div className="flex h-[280px] flex-col items-center justify-center rounded-xl border border-dashed border-border/70 bg-muted/20 text-center">
      <BarChart3 className="mb-2 size-8 text-muted-foreground/70" />
      <p className="text-sm font-medium">Your insight appears here</p>
      <p className="mt-1 max-w-sm text-xs text-muted-foreground">
        Pick Revenue by Month, or use AI Assist to draft the builder from a sentence.
      </p>
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
      <Button type="button" size="sm" variant="ghost" onClick={onExportCsv}>
        <Download className="size-3.5" />
        CSV
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={() => onStub("Share link")}>
        <Link2 className="size-3.5" />
        Share
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={() => onStub("Excel export")}>
        <FileSpreadsheet className="size-3.5" />
        Excel
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={() => onStub("PDF export")}>
        <FileText className="size-3.5" />
        PDF
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
      <p className="mb-3 text-[11px] text-muted-foreground">Metadata only — reopen and re-run anytime.</p>
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
