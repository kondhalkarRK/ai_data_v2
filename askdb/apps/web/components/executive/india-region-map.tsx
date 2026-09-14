"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, MapPin } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { CHART_SERIES } from "@/lib/design";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";

type RegionPoint = {
  region_id: number;
  region_name: string;
  city: string | null;
  state_code: string | null;
  units_sold: number;
  revenue: number;
  units_formatted: string;
  revenue_formatted: string;
  top_make: string | null;
  top_model: string | null;
  dealer_count: number;
  x_pct: number;
  y_pct: number;
};

type DealerRow = {
  dealer_id: number;
  dealer_name: string;
  city: string | null;
  dealer_grade: string | null;
  units_sold: number;
  revenue: number;
  units_formatted: string;
  revenue_formatted: string;
  top_model: string | null;
  top_make: string | null;
};

type ModelRow = {
  make: string;
  model: string;
  car_type: string | null;
  units_sold: number;
  revenue: number;
  units_formatted: string;
  revenue_formatted: string;
};

type MetricMode = "units" | "revenue";
/** panel = inline beside map; modal = full-width overlay sheet under the map */
export type RegionMapDisplayMode = "panel" | "modal";

export function IndiaRegionMap({
  industry,
  presenterMode,
  displayMode = "panel",
}: {
  industry: string;
  presenterMode?: boolean;
  displayMode?: RegionMapDisplayMode;
}) {
  const [metric, setMetric] = useState<MetricMode>("units");
  const [selectedRegion, setSelectedRegion] = useState<RegionPoint | null>(null);
  const [selectedDealer, setSelectedDealer] = useState<DealerRow | null>(null);

  const regions = useQuery({
    queryKey: ["executive-region-map", industry, metric],
    queryFn: () =>
      apiClient.get<RegionPoint[]>(`/api/v1/executive/region-map?metric=${metric}`, {
        industry,
      }),
  });

  const dealers = useQuery({
    queryKey: ["executive-region-dealers", industry, selectedRegion?.region_id],
    queryFn: () =>
      apiClient.get<DealerRow[]>(
        `/api/v1/executive/region-map/${selectedRegion!.region_id}/dealers`,
        { industry },
      ),
    enabled: Boolean(selectedRegion),
  });

  const models = useQuery({
    queryKey: ["executive-dealer-models", industry, selectedDealer?.dealer_id],
    queryFn: () =>
      apiClient.get<ModelRow[]>(
        `/api/v1/executive/dealers/${selectedDealer!.dealer_id}/models`,
        { industry },
      ),
    enabled: Boolean(selectedDealer),
  });

  const maxMetric = useMemo(() => {
    const list = regions.data ?? [];
    return Math.max(
      ...list.map((r) => (metric === "units" ? r.units_sold : r.revenue)),
      1,
    );
  }, [regions.data, metric]);

  function selectRegion(point: RegionPoint) {
    setSelectedRegion(point);
    setSelectedDealer(null);
  }

  const detail = (
    <DrillDetail
      industry={industry}
      selectedRegion={selectedRegion}
      selectedDealer={selectedDealer}
      dealers={dealers.data}
      dealersLoading={dealers.isLoading}
      models={models.data}
      modelsLoading={models.isLoading}
      onBackToRegions={() => {
        setSelectedRegion(null);
        setSelectedDealer(null);
      }}
      onBackToDealers={() => setSelectedDealer(null)}
      onSelectDealer={setSelectedDealer}
    />
  );

  const showDetailBeside = displayMode === "panel" && selectedRegion;
  const showDetailModal = displayMode === "modal" && selectedRegion;

  return (
    <div className="card-secondary p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3
            className={cn(
              presenterMode ? "text-base font-semibold" : "text-sm font-semibold",
            )}
          >
            Regional performance map
          </h3>
          <p className="text-xs text-muted-foreground">
            Click a hub to drill into dealers, then models. Markers show top make by units.
          </p>
        </div>
        <div className="flex gap-1 rounded-md border border-border p-0.5">
          {(["units", "revenue"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setMetric(mode)}
              className={cn(
                "rounded px-2.5 py-1 text-xs capitalize",
                metric === mode
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted",
              )}
            >
              {mode === "units" ? "Units" : "Revenue"}
            </button>
          ))}
        </div>
      </div>

      <div
        className={cn(
          "grid gap-4",
          showDetailBeside ? "lg:grid-cols-2" : "grid-cols-1",
        )}
      >
        <div className="relative overflow-hidden rounded-lg border border-border/70 bg-muted/20">
          {regions.isLoading ? (
            <p className="py-20 text-center text-sm text-muted-foreground">Loading map…</p>
          ) : !(regions.data ?? []).length ? (
            <p className="py-20 text-center text-sm text-muted-foreground">
              No regional sales data for this domain yet.
            </p>
          ) : (
            <IndiaSvg
              points={regions.data ?? []}
              metric={metric}
              maxMetric={maxMetric}
              selectedId={selectedRegion?.region_id ?? null}
              onSelect={selectRegion}
            />
          )}
        </div>

        {showDetailBeside ? detail : null}
        {displayMode === "panel" && !selectedRegion ? (
          <div className="flex min-h-[220px] items-center justify-center rounded-lg border border-dashed border-border/80 px-4 text-center text-sm text-muted-foreground lg:min-h-0">
            Select a region marker to load dealers progressively.
          </div>
        ) : null}
      </div>

      {showDetailModal ? (
        <div className="mt-4 rounded-lg border border-border bg-background p-4 shadow-[var(--shadow-raised)]">
          {detail}
        </div>
      ) : null}
    </div>
  );
}

function IndiaSvg({
  points,
  metric,
  maxMetric,
  selectedId,
  onSelect,
}: {
  points: RegionPoint[];
  metric: MetricMode;
  maxMetric: number;
  selectedId: number | null;
  onSelect: (point: RegionPoint) => void;
}) {
  return (
    <svg viewBox="0 0 80 90" className="mx-auto h-[320px] w-full max-w-md" role="img">
      <title>India regional performance</title>
      <path
        d="M28 8 L36 6 L42 10 L48 8 L54 14 L58 22 L62 28 L60 36 L64 44 L58 52 L54 62 L48 72 L42 80 L36 82 L30 76 L26 68 L22 58 L18 48 L16 38 L18 28 L22 18 Z"
        fill="hsl(var(--muted))"
        stroke="hsl(var(--border))"
        strokeWidth="0.6"
        opacity="0.85"
      />
      {points.map((point) => {
        const value = metric === "units" ? point.units_sold : point.revenue;
        const intensity = Math.max(0.25, value / maxMetric);
        const r = 1.6 + intensity * 2.2;
        const selected = point.region_id === selectedId;
        return (
          <g
            key={point.region_id}
            className="cursor-pointer"
            onClick={() => onSelect(point)}
          >
            <circle
              cx={point.x_pct}
              cy={point.y_pct}
              r={r}
              fill={CHART_SERIES.primary}
              fillOpacity={0.25 + intensity * 0.55}
              stroke={selected ? CHART_SERIES.secondary : CHART_SERIES.primary}
              strokeWidth={selected ? 0.7 : 0.35}
            />
            {point.top_make ? (
              <text
                x={point.x_pct}
                y={point.y_pct - r - 0.8}
                textAnchor="middle"
                fontSize="2.2"
                fill="hsl(var(--foreground))"
                className="pointer-events-none"
              >
                {point.top_make.slice(0, 8)}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

function DrillDetail({
  industry,
  selectedRegion,
  selectedDealer,
  dealers,
  dealersLoading,
  models,
  modelsLoading,
  onBackToRegions,
  onBackToDealers,
  onSelectDealer,
}: {
  industry: string;
  selectedRegion: RegionPoint | null;
  selectedDealer: DealerRow | null;
  dealers?: DealerRow[];
  dealersLoading: boolean;
  models?: ModelRow[];
  modelsLoading: boolean;
  onBackToRegions: () => void;
  onBackToDealers: () => void;
  onSelectDealer: (row: DealerRow) => void;
}) {
  if (!selectedRegion) return null;

  if (selectedDealer) {
    return (
      <div className="space-y-3">
        <Button type="button" variant="ghost" size="sm" onClick={onBackToDealers}>
          <ArrowLeft className="mr-1 h-3.5 w-3.5" />
          Dealers in {selectedRegion.region_name}
        </Button>
        <div>
          <h4 className="text-sm font-semibold">{selectedDealer.dealer_name}</h4>
          <p className="text-xs text-muted-foreground">
            {selectedDealer.units_formatted} units · {selectedDealer.revenue_formatted}
          </p>
        </div>
        {modelsLoading ? (
          <p className="text-sm text-muted-foreground">Loading models…</p>
        ) : !(models ?? []).length ? (
          <EmptyState message="No model sales recorded for this dealer." />
        ) : (
          <ul className="max-h-72 space-y-2 overflow-auto">
            {(models ?? []).map((row) => (
              <li
                key={`${row.make}-${row.model}`}
                className="rounded-md border border-border/60 px-3 py-2 text-sm"
              >
                <div className="flex justify-between gap-2">
                  <span className="font-medium">
                    {row.make} {row.model}
                  </span>
                  <span className="tabular-nums text-muted-foreground">
                    {row.units_formatted}
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {row.revenue_formatted}
                  {row.car_type ? ` · ${row.car_type}` : ""}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Button type="button" variant="ghost" size="sm" onClick={onBackToRegions}>
        <ArrowLeft className="mr-1 h-3.5 w-3.5" />
        All regions
      </Button>
      <div className="flex items-start gap-2">
        <MapPin className="mt-0.5 h-4 w-4 text-primary" />
        <div>
          <h4 className="text-sm font-semibold">{selectedRegion.region_name}</h4>
          <p className="text-xs text-muted-foreground">
            {selectedRegion.units_formatted} units · {selectedRegion.revenue_formatted}
            {selectedRegion.top_make
              ? ` · Top make ${selectedRegion.top_make}${
                  selectedRegion.top_model ? ` ${selectedRegion.top_model}` : ""
                }`
              : ""}
          </p>
        </div>
      </div>
      {industry !== "automotive" ? (
        <EmptyState message="Dealer drill-down is available for Automotive. Insurance shows regional claim intensity on the map." />
      ) : dealersLoading ? (
        <p className="text-sm text-muted-foreground">Loading dealers…</p>
      ) : !(dealers ?? []).length ? (
        <EmptyState message="No dealer data available for this region." />
      ) : (
        <ul className="max-h-72 space-y-2 overflow-auto">
          {(dealers ?? []).map((row) => (
            <li key={row.dealer_id}>
              <button
                type="button"
                className="w-full rounded-md border border-border/60 px-3 py-2 text-left text-sm transition-colors hover:bg-muted/50"
                onClick={() => onSelectDealer(row)}
              >
                <div className="flex justify-between gap-2">
                  <span className="font-medium">{row.dealer_name}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {row.units_formatted}
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {row.revenue_formatted}
                  {row.top_make
                    ? ` · Top ${row.top_make}${row.top_model ? ` ${row.top_model}` : ""}`
                    : ""}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border/80 px-4 py-8 text-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}
