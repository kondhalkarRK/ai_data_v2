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
  RuleManagement,
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
        description="Observability, quality, and governance — the source of truth for trust signals across NQL Insight."
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

          <TrustScoreHero hero={center.data.hero} />

          {view === "overview" ? (
            <>
              <Section title="Active Incidents">
                <IncidentFeed
                  incidents={center.data.incidents}
                  history={center.data.incidentHistory}
                />
              </Section>
              <Section title="AI Data Steward" description="Purple marks AI-assisted stewardship.">
                <AiDataSteward steward={center.data.steward} />
              </Section>
              <Section title="Dataset Health">
                <DatasetHealthGrid datasets={center.data.datasets} />
              </Section>
            </>
          ) : (
            <>
              {/* Data Quality Trends removed (Round 2). Aggregate series was
                  redundant with Dataset Health per-dataset sparklines below;
                  unique lost: org-wide trust score over time as a single chart. */}
              <Section title="Schema Drift">
                <SchemaDriftMonitor changes={center.data.schemaChanges} />
              </Section>
              <Section title="Data Profiling">
                <ProfilingWorkspace profiles={center.data.profiles} />
              </Section>
              <Section title="Governance">
                <GovernanceCenter records={center.data.governance} />
              </Section>
              <Section title="Lineage Impact">
                <LineageImpactExplorer lineage={center.data.lineage} />
              </Section>
              <Section title="Rule Management">
                <RuleManagement
                  rules={center.data.rules}
                  notifications={center.data.notificationRules}
                />
              </Section>
              <Section title="Dataset Health">
                <DatasetHealthGrid datasets={center.data.datasets} />
              </Section>
            </>
          )}
        </div>
      ) : null}
    </PageShell>
  );
}
