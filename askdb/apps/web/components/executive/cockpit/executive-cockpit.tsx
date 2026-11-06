"use client";

import type { Industry } from "@nql/shared-types";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Download, Loader2, RefreshCw, SlidersHorizontal } from "lucide-react";
import * as React from "react";

import { DashboardIntelligence } from "@/components/executive/dashboard-intelligence";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useRetainedQueryData } from "@/hooks/use-retained-query-data";
import { mergeDashboardFilters } from "@/lib/executive/dashboard";

import { BubbleMatrix } from "@/components/executive/cockpit/bubble-matrix";
import { exportCsv } from "@/components/executive/cockpit/chart-utils";
import { activeFilterCount, FilterPane } from "@/components/executive/cockpit/filter-pane";
import { formatDate } from "@/components/executive/cockpit/format";
import { GeoIntelligence } from "@/components/executive/cockpit/geo-intelligence";
import { KpiStrip } from "@/components/executive/cockpit/kpi-strip";
import { SalesMix } from "@/components/executive/cockpit/mix-treemap";
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
import {
  ModuleFilterChips,
  ModulePageHeader,
  ModuleSection,
  ModuleStatusBanner,
  ModuleToolbarButton,
  ModuleWorkspace,
} from "@/components/shell/module-chrome";
import { Skeleton } from "@/components/ui/skeleton";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { useRegionAccess } from "@/hooks/use-session";

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
const PALETTE_KEY = "ask-me-executive-chart-palette-v1";
const subscribePalette = (notify: () => void) => {
  window.addEventListener("storage", notify);
  window.addEventListener("executive-palette-change", notify);
  return () => { window.removeEventListener("storage", notify); window.removeEventListener("executive-palette-change", notify); };
};
const paletteSnapshot = (): "classic" | "vibrant" => {
  try { return window.localStorage.getItem(PALETTE_KEY) === "vibrant" ? "vibrant" : "classic"; }
  catch { return "classic"; }
};
const serverPalette = (): "classic" => "classic";

function toQuery(filters: CockpitFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
  return params.toString();
}

export function ExecutiveCockpit({ industry }: { industry: Industry }) {
  const persistedPalette = React.useSyncExternalStore(subscribePalette, paletteSnapshot, serverPalette);
  const [fallbackPalette, setFallbackPalette] = React.useState<"classic" | "vibrant" | null>(null);
  const chartPalette = fallbackPalette ?? persistedPalette;
  const changePalette = (next: "classic" | "vibrant") => {
    try { window.localStorage.setItem(PALETTE_KEY, next); setFallbackPalette(null); }
    catch { setFallbackPalette(next); }
    window.dispatchEvent(new Event("executive-palette-change"));
  };
  const regionAccess = useRegionAccess();
  const [filters, setFilters] = React.useState<CockpitFilters>({});
  const [paneOpen, setPaneOpen] = React.useState(false);
  const refreshNext = React.useRef(false);
  const rawQs = toQuery(filters);
  const qs = useDebouncedValue(rawQs);

  const cockpit = useQuery({
    queryKey: ["executive-cockpit", industry, qs],
    queryFn: async ({ signal }) => {
      const refresh = refreshNext.current;
      refreshNext.current = false;
      const params = new URLSearchParams(qs);
      if (refresh) params.set("refresh", "true");
      return apiClient.get<CockpitData>(`/api/v1/executive/cockpit?${params.toString()}`, { industry, signal });
    },
    placeholderData: (previous, query) => query?.queryKey[1] === industry ? previous : undefined,
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
  }, [setFilters]);

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

  const data = useRetainedQueryData(cockpit.data, industry);
  const updating = cockpit.isFetching || rawQs !== qs;
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

  const filterChipItems = chips.map(([key, value]) => ({
    key,
    label: FILTER_LABELS[key],
    value: label(key, value),
  }));

  return (
    <div className="executive-cockpit" data-chart-palette={chartPalette}>
    <ModuleWorkspace>
      <ModulePageHeader
        eyebrow="Executive intelligence"
        title={data ? data.period.label : "Sales performance"}
        meta={
          data
            ? `Compared to ${data.period.priorLabel} · Data as of ${formatDate(data.period.dataAsOf)}`
            : "KPI analytics across revenue, volume, and product mix"
        }
        actions={
          <>
            {cockpit.isFetching && data ? (
              <Loader2 className="size-4 animate-spin text-muted-foreground" aria-label="Updating" />
            ) : null}
            <ModuleToolbarButton onClick={() => setPaneOpen((v) => !v)} active={count > 0}>
              <SlidersHorizontal className="size-3.5" /> Filters{count ? ` (${count})` : ""}
            </ModuleToolbarButton>
            <div role="radiogroup" aria-label="Chart colors" className="inline-flex items-center gap-0.5 rounded-lg border border-border bg-surface-sunken p-0.5 text-xs">
              {(["classic", "vibrant"] as const).map((mode) => <button key={mode} type="button" role="radio" aria-checked={chartPalette === mode} onClick={() => changePalette(mode)} className={cn("rounded-md px-2.5 py-1.5 font-medium focus-visible:outline-2 focus-visible:outline-primary", chartPalette === mode ? "bg-surface-raised text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")} title={`${mode === "classic" ? "Restrained blue and teal" : "Expressive, balanced colors"} for charts`}><span className="mr-1.5 inline-block size-2 rounded-full align-middle" style={{ background: mode === "classic" ? "#4d7ce0" : "#9c62e8" }} />{mode === "classic" ? "Classic" : "Vibrant"}</button>)}
            </div>
            <ModuleToolbarButton
              onClick={() => {
                refreshNext.current = true;
                void cockpit.refetch();
              }}
            >
              <RefreshCw className={cn("size-3.5", cockpit.isFetching && "animate-spin")} /> Refresh
            </ModuleToolbarButton>
            <ModuleToolbarButton onClick={exportSummary} disabled={!data}>
              <Download className="size-3.5" /> Export
            </ModuleToolbarButton>
          </>
        }
      />

      <ModuleFilterChips
        chips={filterChipItems}
        onRemove={(key) =>
          setFilters((current) => ({
            ...current,
            [key]: undefined,
            ...(key === "dealer_id" ? { sales_person_id: undefined } : {}),
          }))
        }
        onClear={() => setFilters({})}
      />

      {cockpit.isPending && !data ? (
        <CockpitSkeleton />
      ) : cockpit.isError && !data ? (
        <div className="rounded-2xl border border-border bg-surface-raised p-6 text-sm">
          <p className="font-medium text-foreground">The KPI cockpit could not be loaded.</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {(cockpit.error as Error)?.message || "Check that the automotive warehouse is loaded, then refresh."}
          </p>
          <div className="mt-3 flex gap-3 text-xs font-medium text-[hsl(var(--primary))]">
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
        <div className="empty-state p-10">
          <p className="text-sm font-medium text-foreground">No sales match this selection.</p>
          <button type="button" className="mt-2 text-xs font-medium text-[hsl(var(--primary))] hover:underline" onClick={() => setFilters({})}>
            Clear filters
          </button>
        </div>
      ) : data ? (
        <div className={cn("space-y-10 transition-opacity", cockpit.isFetching && "opacity-80")}>
          {cockpit.isError ? (
            <ModuleStatusBanner tone="warn">
              Update failed. Retaining the last successful view identified in the briefing.
            </ModuleStatusBanner>
          ) : null}
          <DashboardIntelligence
            augmentation={data.augmentation} updating={updating} updateFailed={cockpit.isError}
            pendingLabel={Object.entries(filters).map(([k, v]) => `${k}: ${v}`).join(" · ") || "all permitted data"}
            onApplyFilters={(patch) => setFilters((current) => mergeDashboardFilters({ ...current }, patch))}
            onRefresh={() => { refreshNext.current = true; void cockpit.refetch(); }}
          >
          <KpiStrip data={data} onSelect={select} />

          <ModuleSection
            title="Performance"
            description="Revenue and volume trends with regional growth versus the portfolio average."
          >
            <div className="grid gap-6 xl:grid-cols-12">
              <TrendChart data={data} className="xl:col-span-7" />
              <BubbleMatrix data={data} onSelect={select} className="xl:col-span-5" />
            </div>
          </ModuleSection>

          <ModuleSection
            title="Product mix"
            description="Brand and model contribution, segment share, and ranked performers."
          >
            <div className="grid gap-6 xl:grid-cols-12">
              <RevenueSunburst data={data} onSelect={select} className="xl:col-span-5" />
              <RankedModels data={data} onSelect={select} className="xl:col-span-7" />
            </div>
            <SalesMix data={data} onSelect={select} />
          </ModuleSection>

          <ModuleSection title="Regional performance" description="State and city contribution with drill-down filters.">
            <GeoIntelligence data={data} onSelect={select} />
          </ModuleSection>
          </DashboardIntelligence>
        </div>
      ) : null}

      <FilterPane
        open={paneOpen}
        onOpenChange={setPaneOpen}
        filters={filters}
        options={options.data}
        hideGeography={regionAccess.hideRegionFilter}
        onChange={setFilters}
        onClear={() => setFilters({})}
      />
    </ModuleWorkspace>
    </div>
  );
}

function pct(value: number | null): number | string {
  return value == null ? "" : +(value * 100).toFixed(2);
}

function CockpitSkeleton() {
  return (
    <div className="space-y-10" aria-busy="true" aria-label="Loading KPI cockpit">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:gap-5 xl:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-[8rem] rounded-2xl" />
        ))}
      </div>
      <div className="grid gap-6 xl:grid-cols-12">
        <Skeleton className="h-[22rem] rounded-2xl xl:col-span-8" />
        <Skeleton className="h-[22rem] rounded-2xl xl:col-span-4" />
      </div>
    </div>
  );
}
