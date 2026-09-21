"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useMemo, useState } from "react";

import { AiIntelligenceSection } from "@/components/executive/ai-intelligence";
import { BusinessHealthPanel } from "@/components/executive/business-health";
import { KpiCardsGrid } from "@/components/executive/kpi-cards";
import { ProgressiveExplorer } from "@/components/executive/progressive-explorer";
import type { ExecutiveIntelligence } from "@/components/executive/types";
import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageShell } from "@/components/ui/page-shell";
import { useActiveIndustry } from "@/hooks/use-session";
import { useTrustSnapshot } from "@/hooks/use-trust-snapshot";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui-store";

interface KpiFilters {
  windows: Array<{ id: string; label: string }>;
  lobs: string[];
  regions: string[];
  makes: string[];
}

export default function DashboardPage() {
  const industry = useActiveIndustry();
  const router = useRouter();
  const presenterMode = useUiStore((state) => state.presenterMode);
  const trustSnapshot = useTrustSnapshot();
  const [trustOpen, setTrustOpen] = React.useState(false);
  const [windowId, setWindowId] = useState("ytd");
  const [lob, setLob] = useState("");
  const [region, setRegion] = useState("");
  const [make, setMake] = useState("");
  const [forceRefresh, setForceRefresh] = useState(false);

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

  const bundle = useQuery({
    queryKey: ["executive-intelligence", industry, qs],
    queryFn: async () => {
      const refresh = forceRefresh ? "&refresh=true" : "";
      const data = await apiClient.get<ExecutiveIntelligence>(
        `/api/v1/executive/intelligence?${qs}${refresh}`,
        { industry },
      );
      setForceRefresh(false);
      return data;
    },
  });

  function explore(kpiId: string) {
    router.push(`/semantic?tab=graph&focus=${encodeURIComponent(kpiId)}`);
  }

  const data = bundle.data;
  const highlightCards = useMemo(() => {
    if (!data) return [];
    const cards = [...data.cards];
    const hasTopRegion = cards.some((c) => /top.?region/i.test(c.label) || c.id.includes("region"));
    const hasTopBrand = cards.some(
      (c) => /top.?(brand|make)/i.test(c.label) || c.id.includes("make"),
    );
    const topRegion = data.breakdowns.region?.[0];
    const topMake = data.breakdowns.make?.[0];
    if (!hasTopRegion && topRegion) {
      cards.push({
        id: "derived_top_region",
        label: "Top Region",
        value: topRegion.value,
        formatted: topRegion.name,
        format: "text",
        delta: null,
      });
    }
    if (!hasTopBrand && topMake) {
      cards.push({
        id: "derived_top_brand",
        label: industry === "automotive" ? "Top Brand" : "Top LOB",
        value: topMake.value,
        formatted: topMake.name,
        format: "text",
        delta: null,
      });
    }
    const topModel = data.breakdowns.model?.[0];
    if (topModel && !cards.some((c) => /top.?model/i.test(c.label))) {
      cards.push({
        id: "derived_top_model",
        label: "Top Model",
        value: topModel.value,
        formatted: topModel.name,
        format: "text",
        delta: null,
      });
    }
    return cards.slice(0, 8);
  }, [data, industry]);

  return (
    <PageShell>
      <PageHeader
        title={data?.title ?? "Executive Intelligence"}
        description="Primary KPIs first. Drill the heatmap, then read grounded insights."
        className={presenterMode ? "origin-left scale-110" : undefined}
        actions={
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="gap-1.5"
            onClick={() => {
              setForceRefresh(true);
              void bundle.refetch();
            }}
          >
            <RefreshCw className="size-3.5" />
            Refresh
          </Button>
        }
      />

      {bundle.isPending ? (
        <LoadingState title="Building Executive Intelligence" />
      ) : bundle.isError ? (
        <Card>
          <CardContent className="space-y-2 pt-5 text-sm text-danger">
            <p>Could not load Executive Intelligence.</p>
            <p className="text-xs text-muted-foreground">
              {(bundle.error as Error)?.message ||
                "Migrate and seed the analytics database, then retry."}
            </p>
          </CardContent>
        </Card>
      ) : data ? (
        <div className={cn("space-y-5", presenterMode && "text-base")}>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <p>
              {data.windowLabel}
              {data.startDate ? ` · ${data.startDate}` : ""}
              {data.endDate ? ` → ${data.endDate}` : ""}
              {" · "}
              {data.compareLabel}
              {region ? ` · Focus: ${region}` : ""}
              {make ? ` · ${make}` : ""}
            </p>
            <p>
              Data as of {formatStamp(data.dataAsOf)}
              {" · "}
              Bundle computed {formatStamp(data.computedAt)}
            </p>
          </div>

          <KpiCardsGrid
            cards={highlightCards}
            compareLabel={data.compareLabel}
            onExplore={explore}
            presenterMode={presenterMode}
          />

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
            <div className="min-w-0 space-y-5">
              <section className="rounded-2xl border border-border/60 bg-surface-raised/80 p-4 shadow-sm">
                <div className="mb-3">
                  <h2 className="text-base font-semibold tracking-tight">Progressive explorer</h2>
                  <p className="text-xs text-muted-foreground">
                    Region → State → City. Click a cell to drill. Use Home, Back, or Reset if you go too deep.
                  </p>
                </div>
                <ProgressiveExplorer
                  data={data}
                  industry={industry}
                  presenterMode={presenterMode}
                  regionFilter={region}
                  makeFilter={make}
                  onRegionChange={setRegion}
                  onMakeChange={setMake}
                />
              </section>

              <section className="rounded-2xl border border-border/60 bg-surface-raised/80 p-4 shadow-sm">
                <h2 className="mb-3 text-base font-semibold tracking-tight">AI Intelligence</h2>
                <AiIntelligenceSection
                  insights={data.insights}
                  exploreBasePath={data.exploreBasePath}
                />
              </section>
            </div>

            <aside className="space-y-4 xl:sticky xl:top-4 xl:self-start">
              <div className="rounded-2xl border border-border/60 bg-surface-raised/90 p-4 shadow-sm">
                <h2 className="text-sm font-semibold tracking-tight">Period & filters</h2>
                <p className="mt-1 mb-3 text-[11px] text-muted-foreground">
                  Year window and line of business. Region focus follows the heatmap.
                </p>
                <div className="space-y-3">
                  <FilterSelect
                    label="Period"
                    value={windowId}
                    options={(filters.data?.windows ?? []).map((w) => ({
                      value: w.id,
                      label: w.label,
                    }))}
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
                  ) : null}
                  {region || make || lob ? (
                    <button
                      type="button"
                      className="text-xs font-medium text-primary hover:underline"
                      onClick={() => {
                        setRegion("");
                        setMake("");
                        setLob("");
                      }}
                    >
                      Clear focus
                    </button>
                  ) : null}
                </div>
              </div>

              <div className="rounded-2xl border border-border/60 bg-surface-raised/90 p-4 shadow-sm">
                <h2 className="mb-3 text-sm font-semibold tracking-tight">Business Health</h2>
                <BusinessHealthPanel health={data.health} />
                <div className="mt-3">
                  {trustSnapshot.data?.available && trustSnapshot.data.score != null ? (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                      aria-expanded={trustOpen}
                      onClick={() => setTrustOpen((v) => !v)}
                    >
                      Data Trust: {trustSnapshot.data.label} — {trustSnapshot.data.score.toFixed(0)}
                      /100
                      <ChevronDown className={cn("size-3.5", trustOpen && "rotate-180")} />
                    </button>
                  ) : data.dataQuality.healthyPct != null ? (
                    <p className="text-xs text-muted-foreground">
                      Data Quality {data.dataQuality.healthyPct.toFixed(1)}% · {data.dataQuality.label}
                    </p>
                  ) : null}
                </div>
                {trustOpen && trustSnapshot.data?.components?.length ? (
                  <div className="mt-3 card-supporting px-3 py-2 text-xs">
                    <p className="mb-2 text-muted-foreground">
                      {trustSnapshot.data.formulaNote ||
                        "Sourced from Data Trust Center — same breakdown as the Trust Score hero."}
                    </p>
                    <ul className="space-y-1">
                      {trustSnapshot.data.components.map((c) => (
                        <li key={c.id} className="flex justify-between gap-2">
                          <span>{c.label}</span>
                          <span className="tabular-nums text-muted-foreground">
                            {c.score.toFixed(0)} · w {(c.weight * 100).toFixed(0)}%
                          </span>
                        </li>
                      ))}
                    </ul>
                    <Link
                      href="/data-quality"
                      className="mt-2 inline-block font-medium text-teal underline-offset-2 hover:underline"
                    >
                      Open Data Trust Center
                    </Link>
                  </div>
                ) : null}
                {data.dataQuality.notices.length ? (
                  <div className="mt-3 rounded-[var(--radius-card)] border border-warning/30 bg-warning/8 px-3 py-2 text-sm">
                    <p className="font-medium">Data quality notice</p>
                    <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-muted-foreground">
                      {data.dataQuality.notices.map((notice) => (
                        <li key={notice}>{notice}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            </aside>
          </div>
        </div>
      ) : null}
    </PageShell>
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
    <label className="flex w-full flex-col gap-1 text-xs text-muted-foreground">
      {label}
      <select
        className="h-9 rounded-lg border border-border bg-background px-2 text-sm text-foreground"
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

function formatStamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
