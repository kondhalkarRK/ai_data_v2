"use client";

import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useState } from "react";

import { AiDataSteward } from "@/components/trust/ai-data-steward";
import { DatasetHealthGrid } from "@/components/trust/dataset-health-grid";
import { IncidentFeed } from "@/components/trust/incident-feed";
import {
  LineageImpactExplorer,
  ProfilingWorkspace,
  QualityTrends,
  SchemaDriftMonitor,
} from "@/components/trust/technical-panels";
import { TrustScoreHero } from "@/components/trust/trust-score-hero";
import type { DataTrustCenter } from "@/components/trust/types";
import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageShell, Section } from "@/components/ui/page-shell";
import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";

export default function DataTrustCenterPage() {
  const industry = useActiveIndustry();
  const [view, setView] = useState<"overview" | "technical">("overview");
  const [forceRefresh, setForceRefresh] = useState(false);

  const center = useQuery({
    queryKey: ["data-trust-center", industry],
    queryFn: async () => {
      const refresh = forceRefresh ? "?refresh=true" : "";
      const data = await apiClient.get<DataTrustCenter>(`/api/v1/trust/center${refresh}`, {
        industry,
      });
      setForceRefresh(false);
      return data;
    },
  });

  return (
    <PageShell>
      <PageHeader
        title="Data Trust Center"
        description="Modern data observability — health score, incidents, trends, profiling, and lineage."
        actions={
          <div className="flex items-center gap-2">
            <div className="inline-flex rounded-[var(--radius-control)] border border-border bg-muted/30 p-0.5 text-[11px]">
              {(["overview", "technical"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  className={cn(
                    "rounded-[var(--radius-control)] px-3 py-1 capitalize",
                    view === option
                      ? "bg-background font-medium text-foreground shadow-sm"
                      : "text-muted-foreground",
                  )}
                  onClick={() => setView(option)}
                >
                  {option}
                </button>
              ))}
            </div>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="gap-1.5"
              onClick={() => {
                setForceRefresh(true);
                void center.refetch();
              }}
            >
              <RefreshCw className="size-3.5" />
              Refresh
            </Button>
          </div>
        }
      />

      {center.isPending ? (
        <LoadingState title="Evaluating data trust" />
      ) : center.isError ? (
        <Card>
          <CardContent className="pt-5 text-sm text-danger">
            Could not load Data Trust Center. {(center.error as Error)?.message}
          </CardContent>
        </Card>
      ) : center.data ? (
        <div className="space-y-8">
          <p className="text-xs text-muted-foreground">
            Computed {new Date(center.data.computedAt).toLocaleString()}
            {center.data.dataAsOf
              ? ` · Data as of ${new Date(center.data.dataAsOf).toLocaleString()}`
              : ""}
          </p>

          <Section title="Data Health Score">
            <TrustScoreHero hero={center.data.hero} />
          </Section>

          {view === "overview" ? (
            <>
              <Section title="Active Incidents">
                <IncidentFeed
                  incidents={center.data.incidents}
                  history={center.data.incidentHistory}
                />
              </Section>
              <Section
                title="Data Quality Trends"
                description="Org-wide trust score movement as Trust Center refreshes."
              >
                <QualityTrends trends={center.data.trends} />
              </Section>
              <Section title="Dataset Health Grid">
                <DatasetHealthGrid datasets={center.data.datasets} />
              </Section>
              <Section title="AI Data Steward" description="AI-assisted stewardship recommendations.">
                <AiDataSteward steward={center.data.steward} />
              </Section>
            </>
          ) : (
            <>
              <Section title="Schema Drift Monitor">
                <SchemaDriftMonitor changes={center.data.schemaChanges} />
              </Section>
              <Section title="Data Profiling">
                <ProfilingWorkspace profiles={center.data.profiles} />
              </Section>
              <Section title="Lineage Impact Analysis">
                <LineageImpactExplorer lineage={center.data.lineage} />
              </Section>
            </>
          )}
        </div>
      ) : null}
    </PageShell>
  );
}
