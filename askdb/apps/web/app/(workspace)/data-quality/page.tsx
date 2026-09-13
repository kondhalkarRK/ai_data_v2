"use client";

import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useState } from "react";

import { AiDataSteward } from "@/components/trust/ai-data-steward";
import { DatasetHealthGrid } from "@/components/trust/dataset-health-grid";
import { IncidentFeed } from "@/components/trust/incident-feed";
import {
  GovernanceCenter,
  LineageImpactExplorer,
  ProfilingWorkspace,
  QualityTrends,
  RuleManagement,
  SchemaDriftMonitor,
} from "@/components/trust/technical-panels";
import { TrustScoreHero } from "@/components/trust/trust-score-hero";
import type { DataTrustCenter } from "@/components/trust/types";
import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
    <>
      <PageHeader
        title="Data Trust Center"
        description="Observability, quality, and governance — the source of truth for trust signals across NQL Insight."
        actions={
          <div className="flex items-center gap-2">
            <div className="inline-flex rounded-full border border-border/70 bg-muted/30 p-0.5 text-[11px]">
              {(["overview", "technical"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  className={cn(
                    "rounded-full px-3 py-1 capitalize",
                    view === option ? "bg-background font-medium shadow-sm" : "text-muted-foreground",
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
        <div className="space-y-6">
          <p className="text-xs text-muted-foreground">
            Computed {new Date(center.data.computedAt).toLocaleString()}
            {center.data.dataAsOf
              ? ` · Data as of ${new Date(center.data.dataAsOf).toLocaleString()}`
              : ""}
          </p>

          <TrustScoreHero hero={center.data.hero} />

          {view === "overview" ? (
            <>
              <section className="space-y-3">
                <h2 className="text-sm font-semibold">Active Incidents</h2>
                <IncidentFeed
                  incidents={center.data.incidents}
                  history={center.data.incidentHistory}
                />
              </section>
              <section className="space-y-3">
                <h2 className="text-sm font-semibold">AI Data Steward</h2>
                <AiDataSteward steward={center.data.steward} />
              </section>
              <section className="space-y-3">
                <h2 className="text-sm font-semibold">Dataset Health</h2>
                <DatasetHealthGrid datasets={center.data.datasets} />
              </section>
            </>
          ) : (
            <>
              <section className="space-y-3">
                <h2 className="text-sm font-semibold">Trends</h2>
                <QualityTrends trends={center.data.trends} />
              </section>
              <section className="space-y-3">
                <h2 className="text-sm font-semibold">Schema Drift</h2>
                <SchemaDriftMonitor changes={center.data.schemaChanges} />
              </section>
              <section className="space-y-3">
                <h2 className="text-sm font-semibold">Data Profiling</h2>
                <ProfilingWorkspace profiles={center.data.profiles} />
              </section>
              <section className="space-y-3">
                <h2 className="text-sm font-semibold">Governance</h2>
                <GovernanceCenter records={center.data.governance} />
              </section>
              <section className="space-y-3">
                <h2 className="text-sm font-semibold">Lineage Impact</h2>
                <LineageImpactExplorer lineage={center.data.lineage} />
              </section>
              <section className="space-y-3">
                <h2 className="text-sm font-semibold">Rule Management</h2>
                <RuleManagement
                  rules={center.data.rules}
                  notifications={center.data.notificationRules}
                />
              </section>
              <section className="space-y-3">
                <h2 className="text-sm font-semibold">Dataset Health</h2>
                <DatasetHealthGrid datasets={center.data.datasets} />
              </section>
            </>
          )}
        </div>
      ) : null}
    </>
  );
}
