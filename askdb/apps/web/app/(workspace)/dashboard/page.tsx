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

interface KpiCard {
  id: string;
  label: string;
  value: number | null;
  formatted: string;
  format: string;
  formula?: string;
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
}

interface KpiFilters {
  windows: Array<{ id: string; label: string }>;
  lobs: string[];
  regions: string[];
  makes: string[];
  scenarioAvailable: boolean;
}

export default function DashboardPage() {
  const industry = useActiveIndustry();
  const [windowId, setWindowId] = useState("ytd");
  const [lob, setLob] = useState("");
  const [region, setRegion] = useState("");
  const [make, setMake] = useState("");

  const filters = useQuery({
    queryKey: ["kpi-filters", industry],
    queryFn: () => apiClient.get<KpiFilters>("/api/v1/kpis/filters", { industry }),
  });

  const qs = useMemo(() => {
    const params = new URLSearchParams({ window: windowId });
    if (lob) params.set("lob", lob);
    if (region) params.set("region", region);
    if (make) params.set("make", make);
    return params.toString();
  }, [windowId, lob, region, make]);

  const summary = useQuery({
    queryKey: ["kpi-summary", industry, qs],
    queryFn: () => apiClient.get<KpiSummary>(`/api/v1/kpis/summary?${qs}`, { industry }),
  });

  return (
    <>
      <PageHeader
        title="Executive Dashboard"
        description="KPIs computed in SQL against the active industry warehouse."
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
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => {
              setLob("");
              setRegion("");
              setMake("");
              setWindowId("ytd");
            }}
          >
            Reset
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
        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">
            {summary.data.windowLabel}
            {summary.data.startDate ? ` · ${summary.data.startDate}` : ""}
            {summary.data.endDate ? ` → ${summary.data.endDate}` : ""}
          </p>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {summary.data.cards.map((card) => (
              <Card key={card.id}>
                <CardContent className="pt-4">
                  <CardDescription>{card.label}</CardDescription>
                  <CardTitle className="mt-1 text-2xl tabular-nums">{card.formatted}</CardTitle>
                  {card.formula ? (
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
            />
            {Object.entries(summary.data.breakdowns).map(([key, items]) => (
              <BreakdownCard key={key} title={key} items={items} />
            ))}
          </div>

          {!summary.data.scenarioAvailable ? (
            <Card>
              <CardContent className="pt-4 text-sm text-muted-foreground">
                Scenario Mode stays hidden until forecast data exists. Actual KPIs are never
                overwritten.
              </CardContent>
            </Card>
          ) : null}
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
}: {
  title: string;
  series: KpiSummary["series"];
  metric: string;
}) {
  const max = Math.max(...series.map((point) => Number(point.values[metric] || 0)), 1);
  return (
    <Card>
      <CardContent className="pt-4">
        <CardTitle className="mb-3 text-sm">{title}</CardTitle>
        <div className="flex h-40 items-end gap-1">
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
}: {
  title: string;
  items: Array<{ name: string; value: number; formatted: string }>;
}) {
  const max = Math.max(...items.map((item) => item.value), 1);
  return (
    <Card>
      <CardContent className="pt-4">
        <CardTitle className="mb-3 text-sm capitalize">{title}</CardTitle>
        <ul className="space-y-2">
          {items.slice(0, 8).map((item) => (
            <li key={item.name}>
              <div className="mb-1 flex justify-between gap-2 text-xs">
                <span className="truncate text-foreground">{item.name}</span>
                <span className="tabular-nums text-muted-foreground">{item.formatted}</span>
              </div>
              <div className="h-1.5 rounded-full bg-muted">
                <div
                  className={cn("h-1.5 rounded-full bg-primary/70")}
                  style={{ width: `${(item.value / max) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
