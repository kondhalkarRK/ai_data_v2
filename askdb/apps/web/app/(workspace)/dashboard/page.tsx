"use client";

import type { Industry } from "@nql/shared-types";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui-store";

interface KpiCard {
  id: string;
  label: string;
  value: number | null;
  formatted: string;
  format: string;
  formula?: string;
  delta?: number | null;
}

interface KpiSummary {
  industry: Industry;
  window: string;
  windowLabel: string;
  startDate: string | null;
  endDate: string | null;
  cards: KpiCard[];
  series: Array<{ period: string; values: Record<string, number | null> }>;
  breakdowns: Record<string, Array<{ name: string; value: number; formatted: string }>>;
  scenarioAvailable: boolean;
  compareEnabled?: boolean;
}

interface KpiFilters {
  windows: Array<{ id: string; label: string }>;
  lobs: string[];
  regions: string[];
  makes: string[];
  scenarioAvailable: boolean;
}

interface ScenarioResponse {
  available: boolean;
  message: string;
  actual?: number | null;
  scenario?: number | null;
  delta?: number | null;
  narrative?: string | null;
}

export default function DashboardPage() {
  const industry = useActiveIndustry();
  const presenterMode = useUiStore((state) => state.presenterMode);
  const [windowId, setWindowId] = useState("ytd");
  const [lob, setLob] = useState("");
  const [region, setRegion] = useState("");
  const [make, setMake] = useState("");
  const [compare, setCompare] = useState(true);
  const [scenarioChange, setScenarioChange] = useState(10);
  const [scenarioResult, setScenarioResult] = useState<ScenarioResponse | null>(null);
  const [scenarioBusy, setScenarioBusy] = useState(false);

  const filters = useQuery({
    queryKey: ["kpi-filters", industry],
    queryFn: () => apiClient.get<KpiFilters>("/api/v1/kpis/filters", { industry }),
  });

  const qs = useMemo(() => {
    const params = new URLSearchParams({ window: windowId, compare: String(compare) });
    if (lob) params.set("lob", lob);
    if (region) params.set("region", region);
    if (make) params.set("make", make);
    return params.toString();
  }, [windowId, lob, region, make, compare]);

  const summary = useQuery({
    queryKey: ["kpi-summary", industry, qs],
    queryFn: () => apiClient.get<KpiSummary>(`/api/v1/kpis/summary?${qs}`, { industry }),
  });

  function applyCrossFilter(dimension: string, name: string) {
    if (dimension === "lob") setLob(name);
    else if (dimension === "region") setRegion(name);
    else if (dimension === "make") setMake(name);
  }

  async function runScenario() {
    setScenarioBusy(true);
    try {
      const metric = industry === "insurance" ? "written_premium" : "revenue";
      const result = await apiClient.post<ScenarioResponse>(
        "/api/v1/kpis/scenario",
        {
          metric,
          changeType: "percent",
          changeValue: scenarioChange,
          direction: "up",
        },
        { industry },
      );
      setScenarioResult(result);
    } catch {
      setScenarioResult({
        available: false,
        message: "Scenario request failed. Ensure forecast migration/seed is applied.",
      });
    } finally {
      setScenarioBusy(false);
    }
  }

  function exportCsv() {
    const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
    const url = `${base}/api/v1/kpis/export?${qs}`;
    window.open(url, "_blank", "noopener,noreferrer");
  }

  return (
    <>
      <PageHeader
        title="Executive Dashboard"
        description="KPIs computed in SQL against the active industry warehouse."
        className={presenterMode ? "scale-110 origin-left" : undefined}
      />

      <Card className="mb-4">
        <CardContent className="flex flex-wrap items-end gap-3 pt-4">
          <FilterSelect
            label="Window"
            value={windowId}
            options={(filters.data?.windows ?? []).map((w) => ({ value: w.id, label: w.label }))}
            onChange={setWindowId}
          />
          {industry === "insurance" ? (
            <FilterSelect
              label="Line of business"
              value={lob}
              options={[
                { value: "", label: "All" },
                ...(filters.data?.lobs ?? []).map((item) => ({ value: item, label: item })),
              ]}
              onChange={setLob}
            />
          ) : (
            <FilterSelect
              label="Make"
              value={make}
              options={[
                { value: "", label: "All" },
                ...(filters.data?.makes ?? []).map((item) => ({ value: item, label: item })),
              ]}
              onChange={setMake}
            />
          )}
          <FilterSelect
            label="Region"
            value={region}
            options={[
              { value: "", label: "All" },
              ...(filters.data?.regions ?? []).map((item) => ({ value: item, label: item })),
            ]}
            onChange={setRegion}
          />
          <label className="flex items-center gap-2 pb-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={compare}
              onChange={(event) => setCompare(event.target.checked)}
            />
            Period comparison
          </label>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => {
              setLob("");
              setRegion("");
              setMake("");
              setWindowId("ytd");
              setCompare(true);
              setScenarioResult(null);
            }}
          >
            Reset
          </Button>
          <Button type="button" variant="secondary" size="sm" onClick={exportCsv}>
            Export CSV
          </Button>
        </CardContent>
      </Card>

      {summary.isPending ? (
        <LoadingState title="Computing KPIs" />
      ) : summary.isError ? (
        <Card>
          <CardContent className="pt-5 text-sm text-danger">
            Could not load KPIs. Migrate and seed the analytics database, then retry.
          </CardContent>
        </Card>
      ) : summary.data ? (
        <div className={cn("space-y-4", presenterMode && "text-base")}>
          <p className="text-xs text-muted-foreground">
            {summary.data.windowLabel}
            {summary.data.startDate ? ` · ${summary.data.startDate}` : ""}
            {summary.data.endDate ? ` → ${summary.data.endDate}` : ""}
            {compare ? " · vs prior period" : ""}
          </p>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {summary.data.cards.map((card) => (
              <Card key={card.id}>
                <CardContent className={cn("pt-4", presenterMode && "pt-6")}>
                  <CardDescription>{card.label}</CardDescription>
                  <CardTitle
                    className={cn(
                      "mt-1 tabular-nums",
                      presenterMode ? "text-4xl" : "text-2xl",
                    )}
                  >
                    {card.formatted}
                  </CardTitle>
                  {card.delta != null ? (
                    <p
                      className={cn(
                        "mt-1 text-xs tabular-nums",
                        card.delta >= 0 ? "text-emerald-600" : "text-danger",
                      )}
                    >
                      {card.delta >= 0 ? "+" : ""}
                      {(card.delta * 100).toFixed(1)}% vs prior
                    </p>
                  ) : null}
                  {card.formula && !presenterMode ? (
                    <p className="mt-2 font-mono text-2xs text-muted-foreground">{card.formula}</p>
                  ) : null}
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <SeriesCard
              title="Trend"
              series={summary.data.series}
              metric={industry === "insurance" ? "claims_incurred" : "revenue"}
              presenterMode={presenterMode}
            />
            {Object.entries(summary.data.breakdowns).map(([key, items]) => (
              <BreakdownCard
                key={key}
                title={key}
                items={items}
                onSelect={(name) => applyCrossFilter(key, name)}
                presenterMode={presenterMode}
              />
            ))}
          </div>

          {summary.data.scenarioAvailable || filters.data?.scenarioAvailable ? (
            <Card>
              <CardContent className="space-y-3 pt-4">
                <CardTitle className="text-sm">Scenario Mode</CardTitle>
                <CardDescription>
                  Applies a governed delta to the headline metric. Actual KPI cards stay unchanged.
                </CardDescription>
                <div className="flex flex-wrap items-end gap-3">
                  <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                    Change %
                    <input
                      type="number"
                      min={0}
                      className="h-9 w-24 rounded-md border border-border bg-background px-2 text-sm text-foreground"
                      value={scenarioChange}
                      onChange={(event) => setScenarioChange(Number(event.target.value))}
                    />
                  </label>
                  <Button type="button" size="sm" disabled={scenarioBusy} onClick={runScenario}>
                    Run scenario
                  </Button>
                </div>
                {scenarioResult ? (
                  <p className="text-sm text-muted-foreground">
                    {scenarioResult.narrative || scenarioResult.message}
                  </p>
                ) : null}
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="pt-4 text-sm text-muted-foreground">
                Scenario Mode unlocks after forecast tables are migrated and seeded (
                <code className="text-xs">0002_*_forecast_mvs</code>). Actual KPIs are never
                overwritten.
              </CardContent>
            </Card>
          )}
        </div>
      ) : null}
    </>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex min-w-[160px] flex-col gap-1 text-xs text-muted-foreground">
      {label}
      <select
        className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option.value || "all"} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function SeriesCard({
  title,
  series,
  metric,
  presenterMode,
}: {
  title: string;
  series: KpiSummary["series"];
  metric: string;
  presenterMode: boolean;
}) {
  const max = Math.max(...series.map((point) => Number(point.values[metric] || 0)), 1);
  return (
    <Card>
      <CardContent className="pt-4">
        <CardTitle className={cn("mb-3", presenterMode ? "text-base" : "text-sm")}>{title}</CardTitle>
        <div className={cn("flex items-end gap-1", presenterMode ? "h-56" : "h-40")}>
          {series.slice(-18).map((point) => {
            const value = Number(point.values[metric] || 0);
            const height = `${Math.max((value / max) * 100, 2)}%`;
            return (
              <div
                key={point.period}
                className="flex-1 rounded-t bg-primary/70"
                style={{ height }}
                title={`${point.period}: ${value.toLocaleString()}`}
              />
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function BreakdownCard({
  title,
  items,
  onSelect,
  presenterMode,
}: {
  title: string;
  items: Array<{ name: string; value: number; formatted: string }>;
  onSelect: (name: string) => void;
  presenterMode: boolean;
}) {
  const max = Math.max(...items.map((item) => item.value), 1);
  return (
    <Card>
      <CardContent className="pt-4">
        <CardTitle className={cn("mb-3 capitalize", presenterMode ? "text-base" : "text-sm")}>
          {title}
          <span className="ml-2 font-normal text-muted-foreground">(click to filter)</span>
        </CardTitle>
        <ul className="space-y-2">
          {items.slice(0, 8).map((item) => (
            <li key={item.name}>
              <button
                type="button"
                className="w-full text-left"
                onClick={() => onSelect(item.name)}
              >
                <div className="mb-1 flex justify-between gap-2 text-xs">
                  <span className="truncate text-foreground underline-offset-2 hover:underline">
                    {item.name}
                  </span>
                  <span className="tabular-nums text-muted-foreground">{item.formatted}</span>
                </div>
                <div className="h-1.5 rounded-full bg-muted">
                  <div
                    className="h-1.5 rounded-full bg-primary/70"
                    style={{ width: `${(item.value / max) * 100}%` }}
                  />
                </div>
              </button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
