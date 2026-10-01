"use client";

import type { Industry } from "@nql/shared-types";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Download, Loader2, RefreshCw, SlidersHorizontal, X } from "lucide-react";
import * as React from "react";

import { BubbleMatrix } from "@/components/executive/cockpit/bubble-matrix";
import { exportCsv } from "@/components/executive/cockpit/chart-utils";
import { activeFilterCount, FilterPane } from "@/components/executive/cockpit/filter-pane";
import { formatDate } from "@/components/executive/cockpit/format";
import { GeoIntelligence } from "@/components/executive/cockpit/geo-intelligence";
import { InsightRail } from "@/components/executive/cockpit/insight-rail";
import { KpiStrip } from "@/components/executive/cockpit/kpi-strip";
import { SalesMix } from "@/components/executive/cockpit/mix-treemap";
import { PlanBullets } from "@/components/executive/cockpit/plan-bullets";
import { RankedModels } from "@/components/executive/cockpit/ranked-models";
import { RevenueSunburst } from "@/components/executive/cockpit/sunburst";
import { TrendChart } from "@/components/executive/cockpit/trend-chart";
import type {
  CockpitData,
  CockpitFilters,
  CockpitOptions,
  FilterKey,
  SelectHandler,
} from "@/components/executive/cockpit/types";
import { Skeleton } from "@/components/ui/skeleton";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const FILTER_LABELS: Record<FilterKey, string> = {
  year: "Year",
  quarter: "Quarter",
  month: "Month",
  make: "Make",
  model: "Model",
  engine_type: "Fuel",
  car_type: "Vehicle type",
  zone: "Region",
  state: "State",
  city: "City",
  dealer_id: "Dealer",
  sales_person_id: "Salesperson",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function toQuery(filters: CockpitFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
  return params.toString();
}

export function ExecutiveCockpit({ industry }: { industry: Industry }) {
  const [filters, setFilters] = React.useState<CockpitFilters>({});
  const [paneOpen, setPaneOpen] = React.useState(false);
  const refreshNext = React.useRef(false);
  const qs = toQuery(filters);

  const cockpit = useQuery({
    queryKey: ["executive-cockpit", industry, qs],
    queryFn: async () => {
      const refresh = refreshNext.current;
      refreshNext.current = false;
      const params = new URLSearchParams(qs);
      if (refresh) params.set("refresh", "true");
      return apiClient.get<CockpitData>(`/api/v1/executive/cockpit?${params.toString()}`, { industry });
    },
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });

  const options = useQuery({
    queryKey: ["executive-cockpit-options", industry, filters.dealer_id ?? ""],
    queryFn: () =>
      apiClient.get<CockpitOptions>(
        `/api/v1/executive/cockpit/options${filters.dealer_id ? `?dealer_id=${filters.dealer_id}` : ""}`,
        { industry },
      ),
    placeholderData: keepPreviousData,
    staleTime: 300_000,
  });

  const select: SelectHandler = React.useCallback((key, value) => {
    setFilters((current) => ({ ...current, [key]: current[key] === value ? undefined : value }));
  }, []);

  const label = React.useCallback(
    (key: FilterKey, value: string): string => {
      const o = options.data;
      if (key === "month") return MONTHS[Number(value) - 1] ?? value;
      if (key === "quarter") return `Q${value}`;
      if (key === "state") return o?.states.find((s) => s.value === value)?.label ?? value;
      if (key === "dealer_id") return o?.dealers.find((d) => d.value === value)?.label ?? `Dealer ${value}`;
      if (key === "sales_person_id") return o?.salespeople.find((p) => p.value === value)?.label ?? `#${value}`;
      return value;
    },
    [options.data],
  );

  const data = cockpit.data;
  const count = activeFilterCount(filters);
  const chips = (Object.entries(filters) as Array<[FilterKey, string | undefined]>).filter(
    (entry): entry is [FilterKey, string] => Boolean(entry[1]),
  );

  const exportSummary = () => {
    if (!data) return;
    const k = data.kpis;
    exportCsv(
      [
        { section: "KPI", item: "Total revenue", value: k.revenue.value, prior: k.revenue.prior, growth_pct: pct(k.revenue.growth) },
        { section: "KPI", item: "Units sold", value: k.units.value, prior: k.units.prior, growth_pct: pct(k.units.growth) },
        { section: "KPI", item: "Total orders", value: k.orders.value, prior: k.orders.prior, growth_pct: pct(k.orders.growth) },
        { section: "KPI", item: "Average price", value: k.avgPrice.value, prior: k.avgPrice.prior, growth_pct: pct(k.avgPrice.growth) },
        ...(k.topModel ? [{ section: "KPI", item: `Top model: ${k.topModel.name}`, value: k.topModel.revenue, prior: "", growth_pct: pct(k.topModel.growth) }] : []),
        ...(k.topMake ? [{ section: "KPI", item: `Top make: ${k.topMake.name}`, value: k.topMake.revenue, prior: "", growth_pct: pct(k.topMake.growth) }] : []),
        ...data.insights.map((i) => ({ section: "Insight", item: i.headline, value: i.metric ?? "", prior: i.detail, growth_pct: "" })),
      ],
      `executive-kpis-${data.period.label.replace(/[^\w]+/g, "-").toLowerCase()}.csv`,
    );
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#2f6fed]">Executive KPI analytics</p>
          <h1 className="mt-0.5 text-xl font-semibold tracking-tight text-slate-900 dark:text-foreground">
            {data ? data.period.label : "Sales performance"}
            {data ? (
              <span className="ml-2 text-sm font-normal text-slate-500">
                vs {data.period.priorLabel} · data as of {formatDate(data.period.dataAsOf)}
              </span>
            ) : null}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {cockpit.isFetching && data ? <Loader2 className="size-4 animate-spin text-slate-400" aria-label="Updating" /> : null}
          <HeaderButton onClick={() => setPaneOpen((v) => !v)} active={count > 0}>
            <SlidersHorizontal className="size-3.5" /> Filters{count ? ` (${count})` : ""}
          </HeaderButton>
          <HeaderButton
            onClick={() => {
              refreshNext.current = true;
              void cockpit.refetch();
            }}
          >
            <RefreshCw className={cn("size-3.5", cockpit.isFetching && "animate-spin")} /> Refresh
          </HeaderButton>
          <HeaderButton onClick={exportSummary} disabled={!data}>
            <Download className="size-3.5" /> Export
          </HeaderButton>
        </div>
      </header>

      {chips.length ? (
        <div className="-mt-1 flex flex-wrap items-center gap-1.5">
          {chips.map(([key, value]) => (
            <span
              key={key}
              className="inline-flex items-center gap-1 rounded-full border border-[#c9dafb] bg-[#f1f6ff] py-0.5 pl-2.5 pr-1 text-2xs text-slate-700"
            >
              <span className="text-slate-500">{FILTER_LABELS[key]}:</span>
              <span className="font-semibold">{label(key, value)}</span>
              <button
                type="button"
                aria-label={`Remove ${FILTER_LABELS[key]} filter`}
                className="rounded-full p-0.5 hover:bg-[#dce8fd]"
                onClick={() =>
                  setFilters((current) => ({
                    ...current,
                    [key]: undefined,
                    ...(key === "dealer_id" ? { sales_person_id: undefined } : {}),
                  }))
                }
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

      {cockpit.isPending ? (
        <CockpitSkeleton />
      ) : cockpit.isError && !data ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm">
          <p className="font-medium text-slate-800">The KPI cockpit could not be loaded.</p>
          <p className="mt-1 text-xs text-slate-500">
            {(cockpit.error as Error)?.message || "Check that the automotive warehouse is loaded, then refresh."}
          </p>
          <div className="mt-3 flex gap-3 text-xs font-medium text-[#2f6fed]">
            <button type="button" className="hover:underline" onClick={() => void cockpit.refetch()}>
              Retry
            </button>
            {count ? (
              <button type="button" className="hover:underline" onClick={() => setFilters({})}>
                Clear filters
              </button>
            ) : null}
          </div>
        </div>
      ) : data?.empty ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white/70 p-10 text-center">
          <p className="text-sm font-medium text-slate-700">No sales match this selection.</p>
          <button type="button" className="mt-2 text-xs font-medium text-[#2f6fed] hover:underline" onClick={() => setFilters({})}>
            Clear filters
          </button>
        </div>
      ) : data ? (
        <div className={cn("space-y-4 transition-opacity", cockpit.isFetching && "opacity-80")}>
          {cockpit.isError ? (
            <p role="alert" className="rounded-xl border border-[#f0d9a8] bg-[#fdf3dc] px-3 py-2 text-xs text-[#7a5a14]">
              Refresh failed. Showing the figures last loaded for this selection.
            </p>
          ) : null}
          <KpiStrip data={data} onSelect={select} />
          <div className="grid gap-4 xl:grid-cols-12">
            <TrendChart data={data} className="xl:col-span-5" />
            <BubbleMatrix data={data} onSelect={select} className="xl:col-span-4" />
            <div className="relative min-h-[18rem] xl:col-span-3">
              <InsightRail insights={data.insights} onSelect={select} className="h-full xl:absolute xl:inset-0" />
            </div>
          </div>
          <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-12">
            <RevenueSunburst data={data} onSelect={select} className="xl:col-span-4" />
            <RankedModels data={data} onSelect={select} className="xl:col-span-4" />
            <SalesMix data={data} onSelect={select} className="lg:col-span-2 xl:col-span-4" />
          </div>
          <div className="grid gap-4 xl:grid-cols-12">
            <GeoIntelligence data={data} onSelect={select} className="xl:col-span-7" />
            <PlanBullets data={data} onSelect={select} className="xl:col-span-5" />
          </div>
        </div>
      ) : null}

      <FilterPane
        open={paneOpen}
        onOpenChange={setPaneOpen}
        filters={filters}
        options={options.data}
        onChange={setFilters}
        onClear={() => setFilters({})}
      />
    </div>
  );
}

function pct(value: number | null): number | string {
  return value == null ? "" : +(value * 100).toFixed(2);
}

function HeaderButton({
  children,
  onClick,
  active = false,
  disabled = false,
}: {
  children: React.ReactNode;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-xs font-medium shadow-sm transition disabled:opacity-50",
        active
          ? "border-[#8fb3f5] bg-[#eef4ff] text-[#2f6fed]"
          : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 dark:border-border dark:bg-surface-raised dark:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function CockpitSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading KPI cockpit">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-[7.5rem] rounded-2xl" />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-12">
        <Skeleton className="h-[21rem] rounded-2xl xl:col-span-5" />
        <Skeleton className="h-[21rem] rounded-2xl xl:col-span-4" />
        <Skeleton className="h-[21rem] rounded-2xl xl:col-span-3" />
      </div>
    </div>
  );
}
