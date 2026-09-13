"use client";

import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { AiIntelligenceSection } from "@/components/executive/ai-intelligence";
import { AskDashboardAi } from "@/components/executive/ask-dashboard-ai";
import { BusinessHealthPanel } from "@/components/executive/business-health";
import { KpiCardsGrid } from "@/components/executive/kpi-cards";
import { PerformanceAnalytics } from "@/components/executive/performance-analytics";
import type { ExecutiveIntelligence } from "@/components/executive/types";
import { WhatIfPanel } from "@/components/executive/what-if-panel";
import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useActiveIndustry } from "@/hooks/use-session";
import { useTrustSnapshot } from "@/hooks/use-trust-snapshot";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui-store";
import Link from "next/link";
import { ChevronDown } from "lucide-react";
import * as React from "react";

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

  function applyCrossFilter(dimension: string, name: string) {
    if (dimension === "lob") setLob(name);
    else if (dimension === "region") setRegion(name);
    else if (dimension === "make") setMake(name);
  }

  function explore(kpiId: string) {
    router.push(`/semantic/ontology?focus=${encodeURIComponent(kpiId)}`);
  }

  const data = bundle.data;

  return (
    <>
      <PageHeader
        title={data?.title ?? "Executive Intelligence"}
        description={data?.tagline ?? "Domain-aware KPIs, grounded AI insights, and What-If analysis."}
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

      <Card className="mb-4 border-border/70 shadow-sm">
        <CardContent className="flex flex-wrap items-end gap-3 pt-4">
          <FilterSelect
            label="Period"
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
            variant="ghost"
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
        <div className={cn("space-y-6", presenterMode && "text-base")}>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <p>
              {data.windowLabel}
              {data.startDate ? ` · ${data.startDate}` : ""}
              {data.endDate ? ` → ${data.endDate}` : ""}
              {" · "}
              {data.compareLabel}
            </p>
            <p>
              Data as of {formatStamp(data.dataAsOf)} · Bundle computed{" "}
              {formatStamp(data.computedAt)}
            </p>
          </div>

          <section className="space-y-3">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <h2 className="text-sm font-semibold tracking-tight">Business Health</h2>
              {trustSnapshot.data?.available && trustSnapshot.data.score != null ? (
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                  aria-expanded={trustOpen}
                  onClick={() => setTrustOpen((v) => !v)}
                >
                  Data Trust: {trustSnapshot.data.label} — {trustSnapshot.data.score.toFixed(0)}/100
                  <ChevronDown className={cn("size-3.5", trustOpen && "rotate-180")} />
                </button>
              ) : data.dataQuality.healthyPct != null ? (
                <p className="text-xs text-muted-foreground">
                  Data Quality {data.dataQuality.healthyPct.toFixed(1)}% · {data.dataQuality.label}
                </p>
              ) : null}
            </div>
            {trustOpen && trustSnapshot.data?.components?.length ? (
              <div className="rounded-xl border border-border/60 bg-muted/20 px-3 py-2 text-xs">
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
                  className="mt-2 inline-block font-medium underline-offset-2 hover:underline"
                >
                  Open Data Trust Center
                </Link>
              </div>
            ) : null}
            <BusinessHealthPanel health={data.health} />
            {data.dataQuality.notices.length ? (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/8 px-3 py-2 text-sm text-amber-900 dark:text-amber-100">
                <p className="font-medium">Data Quality Notice</p>
                <ul className="mt-1 list-disc space-y-1 pl-4 text-xs">
                  {data.dataQuality.notices.map((notice) => (
                    <li key={notice}>{notice}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <KpiCardsGrid
              cards={data.cards}
              compareLabel={data.compareLabel}
              onExplore={explore}
              presenterMode={presenterMode}
            />
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold tracking-tight">AI Intelligence</h2>
            <AiIntelligenceSection
              insights={data.insights}
              exploreBasePath={data.exploreBasePath}
            />
          </section>

          <section>
            <WhatIfPanel presets={data.whatIfPresets} />
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold tracking-tight">Performance Analytics</h2>
            <PerformanceAnalytics
              data={data}
              presenterMode={presenterMode}
              onFilter={applyCrossFilter}
            />
          </section>

          <section>
            <AskDashboardAi suggestions={data.suggestedQuestions} />
          </section>
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
