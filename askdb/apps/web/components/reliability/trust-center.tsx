"use client";

import { type Industry, roleAtLeast } from "@nql/shared-types";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Download, Loader2, Plus, RefreshCw, X } from "lucide-react";
import * as React from "react";

import { exportCsv } from "@/components/executive/cockpit/chart-utils";
import { AlertCenter } from "@/components/reliability/alert-center";
import { BusinessImpactPanel } from "@/components/reliability/business-impact";
import { DatasetRanking } from "@/components/reliability/dataset-ranking";
import { DimensionCards } from "@/components/reliability/dimension-cards";
import { EntityChangesPanel, SchemaDriftPanel } from "@/components/reliability/drift-entities";
import { DrilldownPanel, type RuleEdits } from "@/components/reliability/drilldown-panel";
import { FreshnessTable } from "@/components/reliability/freshness-table";
import { CapabilitiesPanel, MethodologyPanel } from "@/components/reliability/insights-methodology";
import { type CreateMonitorBody, MonitorDialog } from "@/components/reliability/monitor-dialog";
import { type BulkRequest, RulesCatalog } from "@/components/reliability/rules-catalog";
import { TrustHero } from "@/components/reliability/trust-hero";
import { TrustTrendChart } from "@/components/reliability/trust-trend";
import type {
  DataReliability,
  Drilldown,
  MonitorMutationResult,
  RuleStatus,
  TrustFilters,
} from "@/components/reliability/types";
import { DIMENSION_LABEL, formatWhen } from "@/components/reliability/ui";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/hooks/use-session";
import { ApiError, apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const STATUS_LABEL: Record<RuleStatus, string> = {
  passing: "Passing",
  failing: "Failing",
  error: "Not run",
  no_data: "No data",
  disabled: "Disabled",
};

type Section = "catalog" | "alerts" | "datasets" | "trend";

export function TrustCenter({ industry }: { industry: Industry }) {
  const queryClient = useQueryClient();
  const { data: user } = useSession();
  const canEdit = user ? roleAtLeast(user.role, "admin") : false;
  const [filters, setFilters] = React.useState<TrustFilters>({});
  const [drills, setDrills] = React.useState<Drilldown[]>([]);
  const [monitorOpen, setMonitorOpen] = React.useState(false);
  const [monitorError, setMonitorError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<{ tone: "ok" | "warn"; text: string } | null>(null);
  const refreshNext = React.useRef(false);
  const key = React.useMemo(() => ["data-reliability", industry] as const, [industry]);

  const center = useQuery({
    queryKey: key,
    queryFn: async () => {
      const refresh = refreshNext.current;
      refreshNext.current = false;
      return apiClient.get<DataReliability>(`/api/v1/trust/reliability${refresh ? "?refresh=true" : ""}`, { industry });
    },
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });

  React.useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const settle = React.useCallback(
    async (result: MonitorMutationResult, done: string) => {
      await queryClient.invalidateQueries({ queryKey: key });
      void queryClient.invalidateQueries({ queryKey: ["trust-snapshot", industry] });
      const memo = result.storage === "memory" ? " Saved for this server session only." : "";
      setNotice({
        tone: result.skipped.length ? "warn" : "ok",
        text: `${result.message ?? done}${result.skipped.length ? ` ${result.skipped.length} skipped.` : ""}${memo}`,
      });
    },
    [industry, key, queryClient],
  );
  const failed = (error: unknown) =>
    setNotice({ tone: "warn", text: error instanceof Error ? error.message : "The change could not be saved." });

  const update = useMutation({
    mutationFn: ({ id, edits }: { id: string; edits: RuleEdits }) =>
      apiClient.patch<MonitorMutationResult>(`/api/v1/trust/reliability/monitors/${encodeURIComponent(id)}`, edits, { industry }),
    onMutate: async ({ id, edits }) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<DataReliability>(key);
      if (previous) {
        queryClient.setQueryData<DataReliability>(key, {
          ...previous,
          rules: previous.rules.map((r) => (r.id === id ? { ...r, ...edits } : r)),
        });
      }
      return { previous };
    },
    onSuccess: (result) => settle(result, "Rule updated."),
    onError: (error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous);
      failed(error);
    },
  });
  const bulk = useMutation({
    mutationFn: (body: BulkRequest) =>
      apiClient.post<MonitorMutationResult>("/api/v1/trust/reliability/monitors/bulk", body, { industry }),
    onSuccess: (result) => settle(result, `${result.updated.length} rules updated.`),
    onError: failed,
  });
  const create = useMutation({
    mutationFn: (body: CreateMonitorBody) =>
      apiClient.post<MonitorMutationResult>("/api/v1/trust/reliability/monitors", body, { industry }),
    onSuccess: async (result) => {
      setMonitorOpen(false);
      await settle(result, "Monitor created and checked.");
    },
    onError: (error) =>
      setMonitorError(error instanceof ApiError || error instanceof Error ? error.message : "The monitor could not be created."),
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      apiClient.delete<MonitorMutationResult>(`/api/v1/trust/reliability/monitors/${encodeURIComponent(id)}`, { industry }),
    onSuccess: async (result) => {
      setDrills([]);
      await settle(result, "Monitor deleted.");
    },
    onError: failed,
  });
  const pending = update.isPending || bulk.isPending || create.isPending || remove.isPending;

  const onFilter = React.useCallback((patch: TrustFilters) => setFilters((current) => ({ ...current, ...patch })), []);
  const drill = React.useCallback((next: Drilldown) => {
    if (next.kind === "dimension") setFilters((current) => ({ ...current, dimension: next.key }));
    setDrills((stack) => [...stack.slice(-6), next]);
  }, []);
  const openRule = React.useCallback((id: string) => drill({ kind: "rule", id }), [drill]);
  const jump = (section: Section) =>
    document.getElementById(`trust-${section}`)?.scrollIntoView({ behavior: "smooth", block: "start" });

  const data = center.data;
  const datasetLabel = (name: string) => data?.datasets.find((d) => d.name === name)?.label ?? name;
  const chips: Array<{ key: keyof TrustFilters; label: string; value: string }> = [];
  if (filters.dimension) chips.push({ key: "dimension", label: "Dimension", value: DIMENSION_LABEL[filters.dimension] });
  if (filters.dataset) chips.push({ key: "dataset", label: "Dataset", value: datasetLabel(filters.dataset) });
  if (filters.severity) chips.push({ key: "severity", label: "Severity", value: filters.severity });
  if (filters.status) chips.push({ key: "status", label: "Status", value: STATUS_LABEL[filters.status] });

  const exportSummary = () => {
    if (!data) return;
    exportCsv(
      [
        { section: "Trust score", item: "Overall", score: data.hero.score, detail: data.hero.bandLabel },
        ...data.dimensions.map((d) => ({
          section: "Dimension",
          item: d.label,
          score: d.score,
          detail: `${d.passing} passing, ${d.failing} failing, weight ${Math.round(d.effectiveWeight ?? d.weight)}%`,
        })),
        ...data.rules.map((r) => ({
          section: "Rule",
          item: r.name,
          score: r.passRate,
          detail: `${DIMENSION_LABEL[r.dimension]} | ${r.datasetLabel} | ${r.severity} | ${r.status} | ${r.observed}`,
        })),
        ...data.alerts.map((a) => ({ section: "Alert", item: a.title, score: "", detail: `${a.severity} | ${a.impact}` })),
      ],
      `data-trust-${industry}-${data.computedAt.slice(0, 10)}.csv`,
    );
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#14a3a1]">Executive data reliability center</p>
          <h1 className="mt-0.5 text-xl font-semibold tracking-tight text-slate-900 dark:text-foreground">
            Data Trust Center
            {data ? (
              <span className="ml-2 text-sm font-normal text-slate-500">
                {data.dataAsOf ? `data as of ${formatWhen(data.dataAsOf)} · ` : ""}checked {formatWhen(data.computedAt)}
              </span>
            ) : null}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {center.isFetching && data ? <Loader2 className="size-4 animate-spin text-slate-400" aria-label="Updating" /> : null}
          {canEdit ? (
            <HeaderButton
              onClick={() => {
                refreshNext.current = true;
                void center.refetch();
              }}
              disabled={center.isFetching}
            >
              <RefreshCw className={cn("size-3.5", center.isFetching && "animate-spin")} /> Run checks
            </HeaderButton>
          ) : null}
          <HeaderButton onClick={exportSummary} disabled={!data}>
            <Download className="size-3.5" /> Export
          </HeaderButton>
          {canEdit ? (
            <HeaderButton
              primary
              disabled={!data}
              onClick={() => {
                setMonitorError(null);
                setMonitorOpen(true);
              }}
            >
              <Plus className="size-3.5" /> New monitor
            </HeaderButton>
          ) : null}
        </div>
      </header>

      {chips.length ? (
        <div className="-mt-1 flex flex-wrap items-center gap-1.5">
          {chips.map((c) => (
            <span
              key={c.key}
              className="inline-flex items-center gap-1 rounded-full border border-[#c9dafb] bg-[#f1f6ff] py-0.5 pl-2.5 pr-1 text-2xs text-slate-700"
            >
              <span className="text-slate-500">{c.label}:</span>
              <span className="font-semibold capitalize">{c.value}</span>
              <button
                type="button"
                aria-label={`Remove ${c.label} filter`}
                className="rounded-full p-0.5 hover:bg-[#dce8fd]"
                onClick={() => setFilters((current) => ({ ...current, [c.key]: undefined }))}
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
          <button type="button" className="ml-1 text-2xs font-medium text-[#2f6fed] hover:underline" onClick={() => setFilters({})}>
            Clear all
          </button>
        </div>
      ) : null}

      {notice ? (
        <p
          role="status"
          className={cn(
            "rounded-xl border px-3 py-2 text-xs",
            notice.tone === "ok" ? "border-[#bfe6dd] bg-[#eef9f6] text-[#0f6b5f]" : "border-[#f0d9a8] bg-[#fdf3dc] text-[#7a5a14]",
          )}
        >
          {notice.text}
        </p>
      ) : null}

      {center.isPending ? (
        <TrustSkeleton />
      ) : center.isError && !data ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm dark:border-border dark:bg-surface-raised">
          <p className="font-medium text-slate-800 dark:text-foreground">The Data Trust Center could not be loaded.</p>
          <p className="mt-1 text-xs text-slate-500">
            {(center.error as Error)?.message || "Check that the analytics warehouse is reachable, then retry."}
          </p>
          <button type="button" className="mt-3 text-xs font-medium text-[#2f6fed] hover:underline" onClick={() => void center.refetch()}>
            Retry
          </button>
        </div>
      ) : data ? (
        <div className={cn("space-y-10 transition-opacity", center.isFetching && "opacity-85")}>
          {center.isError ? (
            <p role="alert" className="rounded-xl border border-[#f0d9a8] bg-[#fdf3dc] px-3 py-2 text-xs text-[#7a5a14]">
              The latest check failed to complete. Showing the results from the previous run.
            </p>
          ) : null}
          {data.storage === "memory" ? (
            <p className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-2xs text-slate-500 dark:border-border dark:bg-muted">
              Run history and rule changes are being kept in memory because the reliability tables are not migrated yet.
              Run the database migration to keep trend history and monitor edits across restarts.
            </p>
          ) : null}

          <TrustHero data={data} onFilter={onFilter} onJump={jump} />

          <TrustSection title="Quality by dimension" description="Each dimension's score. Open one to see the rules behind it.">
            <DimensionCards
              dimensions={data.dimensions}
              selected={filters.dimension}
              onOpen={(k) => drill({ kind: "dimension", key: k })}
            />
            <div id="trust-trend" className="scroll-mt-4">
              <TrustTrendChart data={data} filters={filters} onOpenRule={openRule} />
            </div>
          </TrustSection>

          <TrustSection title="Issues & impact" description="What needs attention and which business numbers it affects.">
            <div className="grid gap-6 xl:grid-cols-12">
              <div id="trust-alerts" className="scroll-mt-4 xl:col-span-7">
                <AlertCenter data={data} filters={filters} onFilter={onFilter} onOpenRule={openRule} className="h-full" />
              </div>
              <BusinessImpactPanel data={data} filters={filters} onOpenRule={openRule} className="xl:col-span-5" />
            </div>
          </TrustSection>

          <TrustSection title="Datasets & freshness" description="How each dataset scores and how recently it was loaded.">
            <div className="grid gap-6 xl:grid-cols-12">
              <div id="trust-datasets" className="scroll-mt-4 xl:col-span-7">
                <DatasetRanking data={data} filters={filters} onFilter={onFilter} onDrill={drill} className="h-full" />
              </div>
              <FreshnessTable data={data} filters={filters} onFilter={onFilter} onOpenRule={openRule} className="xl:col-span-5" />
            </div>
          </TrustSection>

          <div id="trust-catalog" className="scroll-mt-4">
            <RulesCatalog
              data={data}
              filters={filters}
              onFilter={onFilter}
              canEdit={canEdit}
              pending={pending}
              onOpenRule={openRule}
              onToggle={(id, enabled) => update.mutate({ id, edits: { enabled } })}
              onBulk={async (body) => {
                try {
                  await bulk.mutateAsync(body);
                  return true;
                } catch {
                  return false;
                }
              }}
              onCreate={() => {
                setMonitorError(null);
                setMonitorOpen(true);
              }}
            />
          </div>

          <details className="group rounded-2xl border border-slate-200/70 bg-white/60 dark:border-border dark:bg-surface-raised/60">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 [&::-webkit-details-marker]:hidden">
              <span>
                <span className="block text-[15px] font-semibold tracking-tight text-slate-800 dark:text-foreground">
                  Monitoring details
                </span>
                <span className="mt-0.5 block text-xs text-slate-500 dark:text-muted-foreground">
                  Schema drift, new business values, scoring method and monitor coverage.
                </span>
              </span>
              <ChevronDown className="size-4 shrink-0 text-slate-400 transition-transform group-open:rotate-180" />
            </summary>
            <div className="space-y-6 border-t border-slate-200/70 p-5 dark:border-border">
              <div className="grid gap-6 lg:grid-cols-2">
                <SchemaDriftPanel data={data} />
                <EntityChangesPanel data={data} />
              </div>
              <MethodologyPanel data={data} />
              <CapabilitiesPanel capabilities={data.capabilities} />
            </div>
          </details>
        </div>
      ) : null}

      {data ? (
        <>
          <DrilldownPanel
            data={data}
            drill={drills.at(-1) ?? null}
            canEdit={canEdit}
            pending={pending}
            onNavigate={drill}
            onBack={drills.length > 1 ? () => setDrills((stack) => stack.slice(0, -1)) : undefined}
            onClose={() => setDrills([])}
            onUpdate={(id, edits) => update.mutate({ id, edits })}
            onDelete={(id) => {
              if (window.confirm("Delete this custom monitor? Its run history is kept.")) remove.mutate(id);
            }}
          />
          <MonitorDialog
            key={monitorOpen ? "open" : "closed"}
            open={monitorOpen}
            catalog={data.catalog}
            pending={create.isPending}
            error={monitorError}
            onClose={() => setMonitorOpen(false)}
            onSubmit={(body) => {
              setMonitorError(null);
              create.mutate(body);
            }}
          />
        </>
      ) : null}
    </div>
  );
}

function TrustSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-5">
      <div className="border-b border-slate-200/70 pb-3 dark:border-border">
        <h2 className="text-base font-semibold tracking-tight text-slate-900 dark:text-foreground">{title}</h2>
        <p className="mt-0.5 text-xs text-slate-500 dark:text-muted-foreground">{description}</p>
      </div>
      <div className="space-y-6">{children}</div>
    </section>
  );
}

function HeaderButton({
  children,
  onClick,
  disabled = false,
  primary = false,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-xs font-medium shadow-sm transition disabled:opacity-50",
        primary
          ? "border-[#2f6fed] bg-[#2f6fed] text-white hover:bg-[#285fd0]"
          : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 dark:border-border dark:bg-surface-raised dark:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function TrustSkeleton() {
  return (
    <div className="space-y-8" aria-busy="true" aria-label="Running data quality checks">
      <div className="grid gap-6 xl:grid-cols-12">
        <Skeleton className="h-[19rem] rounded-2xl xl:col-span-4" />
        <Skeleton className="h-[19rem] rounded-2xl xl:col-span-5" />
        <Skeleton className="h-[19rem] rounded-2xl xl:col-span-3" />
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 lg:gap-5 2xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-[11rem] rounded-2xl" />
        ))}
      </div>
      <p className="text-center text-2xs text-slate-400">Running data quality checks across the warehouse…</p>
    </div>
  );
}
