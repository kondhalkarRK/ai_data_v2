"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Layers3, TrendingUp } from "lucide-react";
import * as React from "react";

import type { ExecutiveIntelligence } from "@/components/executive/types";
import { CHART_SERIES } from "@/lib/design";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";

type RegionPoint = {
  regionId: number;
  regionName: string;
  city: string | null;
  unitsSold: number;
  revenue: number;
  unitsFormatted: string;
  revenueFormatted: string;
  topMake: string | null;
  topModel: string | null;
  dealerCount: number;
};

type DealerRow = {
  dealerId: number;
  dealerName: string;
  city: string | null;
  dealerGrade: string | null;
  unitsSold: number;
  revenue: number;
  unitsFormatted: string;
  revenueFormatted: string;
  topModel: string | null;
  topMake: string | null;
};

type ModelRow = {
  make: string;
  model: string;
  carType: string | null;
  unitsSold: number;
  revenue: number;
  unitsFormatted: string;
  revenueFormatted: string;
};

type DrillLevel = "region" | "dealer" | "brand" | "model";

/**
 * Guided Region → Dealer → Brand → Model explorer.
 * Replaces the cluttered multi-chart + bubble-map layout with progressive storytelling.
 */
export function ProgressiveExplorer({
  data,
  industry,
  presenterMode,
  regionFilter,
  makeFilter,
  onRegionChange,
  onMakeChange,
}: {
  data: ExecutiveIntelligence;
  industry: string;
  presenterMode?: boolean;
  regionFilter: string;
  makeFilter: string;
  onRegionChange: (region: string) => void;
  onMakeChange: (make: string) => void;
}) {
  const isAutomotive = industry === "automotive";
  const [selectedRegion, setSelectedRegion] = React.useState<RegionPoint | null>(null);
  const [selectedDealer, setSelectedDealer] = React.useState<DealerRow | null>(null);
  const [selectedBrand, setSelectedBrand] = React.useState<string | null>(null);
  const [metric, setMetric] = React.useState<"revenue" | "units">("revenue");

  const regions = useQuery({
    queryKey: ["exec-progressive-regions", industry],
    queryFn: () =>
      apiClient.get<RegionPoint[]>("/api/v1/executive/region-map?metric=revenue", {
        industry,
      }),
  });

  const dealers = useQuery({
    queryKey: ["exec-progressive-dealers", industry, selectedRegion?.regionId],
    queryFn: () =>
      apiClient.get<DealerRow[]>(
        `/api/v1/executive/region-map/${selectedRegion!.regionId}/dealers`,
        { industry },
      ),
    enabled: Boolean(isAutomotive && selectedRegion),
  });

  const models = useQuery({
    queryKey: ["exec-progressive-models", industry, selectedDealer?.dealerId],
    queryFn: () =>
      apiClient.get<ModelRow[]>(
        `/api/v1/executive/dealers/${selectedDealer!.dealerId}/models`,
        { industry },
      ),
    enabled: Boolean(isAutomotive && selectedDealer),
  });

  // Sync explorer when external filter bar changes
  React.useEffect(() => {
    if (!regionFilter) {
      setSelectedRegion(null);
      setSelectedDealer(null);
      setSelectedBrand(null);
      return;
    }
    const match = (regions.data ?? []).find(
      (r) => r.regionName.toLowerCase() === regionFilter.toLowerCase(),
    );
    if (match && match.regionId !== selectedRegion?.regionId) {
      setSelectedRegion(match);
      setSelectedDealer(null);
      setSelectedBrand(null);
    }
  }, [regionFilter, regions.data]); // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    if (makeFilter) setSelectedBrand(makeFilter);
    else if (!selectedDealer) setSelectedBrand(null);
  }, [makeFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const level: DrillLevel = selectedBrand
    ? "brand"
    : selectedDealer
      ? "dealer"
      : selectedRegion
        ? "dealer"
        : "region";

  const regionRows = React.useMemo(() => {
    const list = [...(regions.data ?? [])];
    list.sort((a, b) =>
      metric === "revenue" ? b.revenue - a.revenue : b.unitsSold - a.unitsSold,
    );
    return list;
  }, [regions.data, metric]);

  const brandGroups = React.useMemo(() => {
    const source = models.data ?? [];
    const map = new Map<string, { make: string; units: number; revenue: number; models: ModelRow[] }>();
    for (const row of source) {
      const entry = map.get(row.make) ?? { make: row.make, units: 0, revenue: 0, models: [] };
      entry.units += row.unitsSold;
      entry.revenue += row.revenue;
      entry.models.push(row);
      map.set(row.make, entry);
    }
    return [...map.values()].sort((a, b) =>
      metric === "revenue" ? b.revenue - a.revenue : b.units - a.units,
    );
  }, [models.data, metric]);

  const filteredModels = React.useMemo(() => {
    const list = models.data ?? [];
    const filtered = selectedBrand
      ? list.filter((m) => m.make.toLowerCase() === selectedBrand.toLowerCase())
      : list;
    return [...filtered].sort((a, b) =>
      metric === "revenue" ? b.revenue - a.revenue : b.unitsSold - a.unitsSold,
    );
  }, [models.data, selectedBrand, metric]);

  const revenueMetric =
    data.chartMetrics.find((m) => /revenue|premium|sales/i.test(m)) ?? data.chartMetrics[0];

  function selectRegion(point: RegionPoint) {
    setSelectedRegion(point);
    setSelectedDealer(null);
    setSelectedBrand(null);
    onRegionChange(point.regionName);
  }

  function selectDealer(row: DealerRow) {
    setSelectedDealer(row);
    setSelectedBrand(null);
  }

  function selectBrand(make: string) {
    setSelectedBrand(make);
    onMakeChange(make);
  }

  function resetTo(target: "all" | "region" | "dealer") {
    if (target === "all") {
      setSelectedRegion(null);
      setSelectedDealer(null);
      setSelectedBrand(null);
      onRegionChange("");
      onMakeChange("");
      return;
    }
    if (target === "region") {
      setSelectedDealer(null);
      setSelectedBrand(null);
      onMakeChange("");
      return;
    }
    setSelectedBrand(null);
    onMakeChange("");
  }

  // Insurance: hierarchical bars from breakdowns only
  if (!isAutomotive) {
    return (
      <InsuranceExplorer
        data={data}
        presenterMode={Boolean(presenterMode)}
        regionFilter={regionFilter}
        onRegionChange={onRegionChange}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumb
          region={selectedRegion?.regionName}
          dealer={selectedDealer?.dealerName}
          brand={selectedBrand}
          onReset={resetTo}
        />
        <div className="inline-flex rounded-full border border-border/70 bg-muted/30 p-0.5 text-[11px]">
          {(["revenue", "units"] as const).map((option) => (
            <button
              key={option}
              type="button"
              className={cn(
                "rounded-full px-3 py-1 capitalize",
                metric === option
                  ? "bg-background font-medium text-foreground shadow-sm"
                  : "text-muted-foreground",
              )}
              onClick={() => setMetric(option)}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Explore → Understand → Drill down. Select a region to reveal dealers, brands, and models.
      </p>

      {!selectedRegion ? (
        <HeatmapList
          title="Revenue by Region"
          subtitle="Click a region to drill into dealers and product mix"
          rows={regionRows.map((r) => ({
            id: String(r.regionId),
            label: r.regionName,
            detail: r.city || `${r.dealerCount} dealers`,
            value: metric === "revenue" ? r.revenue : r.unitsSold,
            formatted: metric === "revenue" ? r.revenueFormatted : r.unitsFormatted,
            meta: r.topMake ? `Top brand · ${r.topMake}` : undefined,
          }))}
          onSelect={(id) => {
            const point = regionRows.find((r) => String(r.regionId) === id);
            if (point) selectRegion(point);
          }}
          presenterMode={Boolean(presenterMode)}
          loading={regions.isPending}
          error={regions.isError ? "Could not load regional performance." : null}
          accent={CHART_SERIES.primary}
        />
      ) : (
        <div className="space-y-4">
          <ContextBanner
            title={selectedRegion.regionName}
            stats={[
              { label: "Revenue", value: selectedRegion.revenueFormatted },
              { label: "Units", value: selectedRegion.unitsFormatted },
              { label: "Dealers", value: String(selectedRegion.dealerCount) },
              {
                label: "Top brand",
                value: selectedRegion.topMake ?? "—",
              },
            ]}
          />

          {!selectedDealer ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <HeatmapList
                title={`Top Dealers in ${selectedRegion.regionName}`}
                subtitle="Select a dealer to inspect brand and model mix"
                rows={(dealers.data ?? []).map((d) => ({
                  id: String(d.dealerId),
                  label: d.dealerName,
                  detail: [d.city, d.dealerGrade].filter(Boolean).join(" · "),
                  value: metric === "revenue" ? d.revenue : d.unitsSold,
                  formatted: metric === "revenue" ? d.revenueFormatted : d.unitsFormatted,
                  meta: d.topMake ? `Top · ${d.topMake}` : undefined,
                }))}
                onSelect={(id) => {
                  const row = (dealers.data ?? []).find((d) => String(d.dealerId) === id);
                  if (row) selectDealer(row);
                }}
                presenterMode={Boolean(presenterMode)}
                loading={dealers.isPending}
                error={dealers.isError ? "Could not load dealers." : null}
                accent={CHART_SERIES.secondary}
              />
              <div className="space-y-4">
                <BreakdownSnapshot
                  title={`Top Brands in ${selectedRegion.regionName}`}
                  items={(data.breakdowns.make ?? []).slice(0, 6)}
                  onSelect={selectBrand}
                  active={selectedBrand}
                />
                <BreakdownSnapshot
                  title={`Top Models in ${selectedRegion.regionName}`}
                  items={(data.breakdowns.model ?? []).slice(0, 6)}
                />
                {revenueMetric ? (
                  <MiniTrend
                    title={`Trend in ${selectedRegion.regionName}`}
                    series={data.series}
                    metric={revenueMetric}
                    presenterMode={Boolean(presenterMode)}
                  />
                ) : null}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <ContextBanner
                title={selectedDealer.dealerName}
                stats={[
                  { label: "Revenue", value: selectedDealer.revenueFormatted },
                  { label: "Units", value: selectedDealer.unitsFormatted },
                  { label: "City", value: selectedDealer.city ?? "—" },
                  { label: "Grade", value: selectedDealer.dealerGrade ?? "—" },
                ]}
              />
              <div className="grid gap-4 lg:grid-cols-2">
                <HeatmapList
                  title="Top Brands"
                  subtitle="Select a brand to focus models"
                  rows={brandGroups.map((b) => ({
                    id: b.make,
                    label: b.make,
                    detail: `${b.models.length} models`,
                    value: metric === "revenue" ? b.revenue : b.units,
                    formatted:
                      metric === "revenue"
                        ? formatCompact(b.revenue, true)
                        : formatCompact(b.units, false),
                  }))}
                  onSelect={selectBrand}
                  activeId={selectedBrand ?? undefined}
                  presenterMode={Boolean(presenterMode)}
                  loading={models.isPending}
                  error={models.isError ? "Could not load models." : null}
                  accent={CHART_SERIES.secondary}
                />
                <HeatmapList
                  title={selectedBrand ? `Models · ${selectedBrand}` : "Top Models"}
                  subtitle="Product mix for this dealer"
                  rows={filteredModels.map((m) => ({
                    id: `${m.make}-${m.model}`,
                    label: m.model,
                    detail: [m.make, m.carType].filter(Boolean).join(" · "),
                    value: metric === "revenue" ? m.revenue : m.unitsSold,
                    formatted: metric === "revenue" ? m.revenueFormatted : m.unitsFormatted,
                  }))}
                  presenterMode={Boolean(presenterMode)}
                  loading={models.isPending}
                  accent={CHART_SERIES.primary}
                />
              </div>
              {revenueMetric ? (
                <MiniTrend
                  title="Sales trend (window)"
                  series={data.series}
                  metric={revenueMetric}
                  presenterMode={Boolean(presenterMode)}
                />
              ) : null}
            </div>
          )}
        </div>
      )}

      {/* Quiet secondary trend when still at region root */}
      {!selectedRegion && revenueMetric ? (
        <MiniTrend
          title="Overall revenue trend"
          series={data.series}
          metric={revenueMetric}
          presenterMode={Boolean(presenterMode)}
        />
      ) : null}

      <p className="sr-only" aria-live="polite">
        Drill level: {level}
      </p>
    </div>
  );
}

function InsuranceExplorer({
  data,
  presenterMode,
  regionFilter,
  onRegionChange,
}: {
  data: ExecutiveIntelligence;
  presenterMode: boolean;
  regionFilter: string;
  onRegionChange: (region: string) => void;
}) {
  const regions = data.breakdowns.region ?? [];
  const metric =
    data.chartMetrics.find((m) => /premium|incurred|revenue/i.test(m)) ?? data.chartMetrics[0];

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Progressive explorer for insurance: Region → Line of business. Select a region to focus the
        dashboard.
      </p>
      <HeatmapList
        title="Performance by Region"
        subtitle="Click a region to update KPIs and insights"
        rows={regions.map((r) => ({
          id: r.name,
          label: r.name,
          detail: "",
          value: r.value,
          formatted: r.formatted,
        }))}
        onSelect={(id) => onRegionChange(id === regionFilter ? "" : id)}
        activeId={regionFilter || undefined}
        presenterMode={presenterMode}
        accent={CHART_SERIES.primary}
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <BreakdownSnapshot title="Line of business" items={data.breakdowns.lob ?? []} />
        <BreakdownSnapshot title="Claim status" items={data.breakdowns.status ?? []} />
      </div>
      {metric ? (
        <MiniTrend
          title="Trend"
          series={data.series}
          metric={metric}
          presenterMode={presenterMode}
        />
      ) : null}
    </div>
  );
}

function Breadcrumb({
  region,
  dealer,
  brand,
  onReset,
}: {
  region?: string;
  dealer?: string;
  brand?: string | null;
  onReset: (target: "all" | "region" | "dealer") => void;
}) {
  return (
    <nav aria-label="Drill path" className="flex flex-wrap items-center gap-1 text-xs">
      <button
        type="button"
        className={cn(
          "inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-medium",
          !region ? "bg-primary/15 text-foreground" : "text-muted-foreground hover:text-foreground",
        )}
        onClick={() => onReset("all")}
      >
        <Layers3 className="size-3.5" />
        All regions
      </button>
      {region ? (
        <>
          <ChevronRight className="size-3 text-muted-foreground" />
          <button
            type="button"
            className={cn(
              "rounded-full px-2.5 py-1 font-medium",
              !dealer ? "bg-primary/15 text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
            onClick={() => onReset("region")}
          >
            {region}
          </button>
        </>
      ) : null}
      {dealer ? (
        <>
          <ChevronRight className="size-3 text-muted-foreground" />
          <button
            type="button"
            className={cn(
              "rounded-full px-2.5 py-1 font-medium",
              !brand ? "bg-primary/15 text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
            onClick={() => onReset("dealer")}
          >
            {dealer}
          </button>
        </>
      ) : null}
      {brand ? (
        <>
          <ChevronRight className="size-3 text-muted-foreground" />
          <span className="rounded-full bg-primary/15 px-2.5 py-1 font-medium text-foreground">
            {brand}
          </span>
        </>
      ) : null}
    </nav>
  );
}

function HeatmapList({
  title,
  subtitle,
  rows,
  onSelect,
  activeId,
  presenterMode,
  loading,
  error,
  accent,
}: {
  title: string;
  subtitle?: string;
  rows: Array<{
    id: string;
    label: string;
    detail: string;
    value: number;
    formatted: string;
    meta?: string;
  }>;
  onSelect?: (id: string) => void;
  activeId?: string;
  presenterMode: boolean;
  loading?: boolean;
  error?: string | null;
  accent: string;
}) {
  const max = Math.max(...rows.map((r) => r.value), 1);

  return (
    <div className="rounded-2xl border border-border/60 bg-surface-raised/80 p-4 shadow-sm">
      <div className="mb-3">
        <h3
          className={cn(
            "font-semibold tracking-tight",
            presenterMode ? "text-base" : "text-sm",
          )}
        >
          {title}
        </h3>
        {subtitle ? <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p> : null}
      </div>
      {loading ? (
        <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
      ) : error ? (
        <p className="py-6 text-center text-sm text-danger">{error}</p>
      ) : !rows.length ? (
        <p className="py-8 text-center text-sm text-muted-foreground">No rows for this level.</p>
      ) : (
        <ul className="space-y-2">
          {rows.slice(0, 12).map((row, index) => {
            const intensity = 0.22 + (row.value / max) * 0.78;
            const active = activeId === row.id;
            const inner = (
              <>
                <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
                  <span className="truncate font-medium">
                    <span className="mr-2 tabular-nums text-muted-foreground">{index + 1}.</span>
                    {row.label}
                  </span>
                  <span className="shrink-0 tabular-nums text-muted-foreground">{row.formatted}</span>
                </div>
                <div className="h-2.5 overflow-hidden rounded-full bg-muted/60">
                  <div
                    className="h-full rounded-full transition-[width]"
                    style={{
                      width: `${Math.max((row.value / max) * 100, row.value > 0 ? 3 : 0)}%`,
                      backgroundColor: accent,
                      opacity: intensity,
                    }}
                  />
                </div>
                {(row.detail || row.meta) && (
                  <p className="mt-1 truncate text-[10px] text-muted-foreground">
                    {[row.detail, row.meta].filter(Boolean).join(" · ")}
                  </p>
                )}
              </>
            );
            return (
              <li key={row.id}>
                {onSelect ? (
                  <button
                    type="button"
                    className={cn(
                      "w-full rounded-xl px-2 py-2 text-left transition-colors hover:bg-muted/40",
                      active && "bg-primary/10 ring-1 ring-primary/30",
                    )}
                    onClick={() => onSelect(row.id)}
                  >
                    {inner}
                  </button>
                ) : (
                  <div className="px-2 py-2">{inner}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function BreakdownSnapshot({
  title,
  items,
  onSelect,
  active,
}: {
  title: string;
  items: Array<{ name: string; value: number; formatted: string }>;
  onSelect?: (name: string) => void;
  active?: string | null;
}) {
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <div className="rounded-2xl border border-border/60 bg-surface-raised/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold tracking-tight">{title}</h3>
      {!items.length ? (
        <p className="text-xs text-muted-foreground">No data in this window.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li key={item.name}>
              {onSelect ? (
                <button
                  type="button"
                  className={cn(
                    "w-full rounded-lg px-1 py-1 text-left hover:bg-muted/40",
                    active === item.name && "bg-primary/10",
                  )}
                  onClick={() => onSelect(item.name)}
                >
                  <RowBar item={item} max={max} />
                </button>
              ) : (
                <RowBar item={item} max={max} />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RowBar({
  item,
  max,
}: {
  item: { name: string; value: number; formatted: string };
  max: number;
}) {
  return (
    <>
      <div className="mb-1 flex justify-between gap-2 text-xs">
        <span className="truncate">{item.name}</span>
        <span className="tabular-nums text-muted-foreground">{item.formatted}</span>
      </div>
      <div className="h-1.5 rounded-full bg-muted">
        <div
          className="h-1.5 rounded-full bg-primary/80"
          style={{ width: `${(item.value / max) * 100}%` }}
        />
      </div>
    </>
  );
}

function ContextBanner({
  title,
  stats,
}: {
  title: string;
  stats: Array<{ label: string; value: string }>;
}) {
  return (
    <div className="rounded-2xl border border-info/20 bg-gradient-to-r from-info/10 via-surface-raised to-transparent px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-info">
            Focused view
          </p>
          <h3 className="text-base font-semibold tracking-tight">{title}</h3>
        </div>
        <div className="flex flex-wrap gap-4">
          {stats.map((stat) => (
            <div key={stat.label}>
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
                {stat.label}
              </p>
              <p className="text-sm font-semibold tabular-nums">{stat.value}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MiniTrend({
  title,
  series,
  metric,
  presenterMode,
}: {
  title: string;
  series: ExecutiveIntelligence["series"];
  metric: string;
  presenterMode: boolean;
}) {
  const points = series.slice(-14);
  const values = points.map((p) => Number(p.values[metric] || 0));
  const max = Math.max(...values, 1);

  if (!points.length) return null;

  return (
    <div className="rounded-2xl border border-border/60 bg-surface-raised/80 p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <TrendingUp className="size-3.5 text-info" />
        <h3 className={cn("font-semibold", presenterMode ? "text-base" : "text-sm")}>{title}</h3>
      </div>
      <div className={cn("flex items-end gap-1", presenterMode ? "h-32" : "h-24")}>
        {points.map((point, index) => {
          const value = values[index] ?? 0;
          return (
            <div
              key={point.period}
              className="flex-1 rounded-t bg-info/70"
              style={{ height: `${Math.max((value / max) * 100, value > 0 ? 4 : 0)}%` }}
              title={`${point.period}: ${value.toLocaleString()}`}
            />
          );
        })}
      </div>
    </div>
  );
}

function formatCompact(value: number, money: boolean): string {
  const abs = Math.abs(value);
  const prefix = money ? "₹" : "";
  if (abs >= 1_00_00_000) return `${prefix}${(value / 1_00_00_000).toFixed(1)}Cr`;
  if (abs >= 1_00_000) return `${prefix}${(value / 1_00_000).toFixed(1)}L`;
  if (abs >= 1_000) return `${prefix}${(value / 1_000).toFixed(1)}k`;
  return `${prefix}${Math.round(value).toLocaleString()}`;
}
