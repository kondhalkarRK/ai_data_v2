"use client";

import { useQuery } from "@tanstack/react-query";

import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";

interface CostSummary {
  calls: number;
  totalTokens: number;
  estimatedCostUsd: number;
  recent: Array<{
    id: string;
    model: string;
    purpose: string;
    totalTokens: number;
    estimatedCostUsd: number;
    createdAt: string;
  }>;
}

export default function CostAnalyticsPage() {
  const industry = useActiveIndustry();
  const cost = useQuery({
    queryKey: ["cost", industry],
    queryFn: () => apiClient.get<CostSummary>("/api/v1/cost", { industry }),
  });

  return (
    <>
      <PageHeader
        title="Cost Analytics"
        description="Token usage and estimated spend from chat LLM calls."
      />
      {cost.isPending ? (
        <LoadingState title="Loading usage" />
      ) : cost.isError ? (
        <Card>
          <CardContent className="pt-5 text-sm text-danger">
            Cost analytics require the analyst role and a migrated app database.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Metric label="Calls" value={String(cost.data?.calls ?? 0)} />
            <Metric label="Tokens" value={(cost.data?.totalTokens ?? 0).toLocaleString()} />
            <Metric
              label="Est. USD"
              value={`$${(cost.data?.estimatedCostUsd ?? 0).toFixed(4)}`}
            />
          </div>
          <Card>
            <CardContent className="space-y-2 pt-4">
              <CardTitle className="text-sm">Recent calls</CardTitle>
              {(cost.data?.recent ?? []).map((row) => (
                <div key={row.id} className="border-t border-border/60 py-2 text-sm">
                  <p className="font-medium">
                    {row.model} · {row.purpose}
                  </p>
                  <CardDescription>
                    {row.totalTokens} tokens · ${row.estimatedCostUsd.toFixed(4)} ·{" "}
                    {new Date(row.createdAt).toLocaleString()}
                  </CardDescription>
                </div>
              ))}
              {(cost.data?.recent.length ?? 0) === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No LLM usage yet. Template answers do not bill tokens.
                </p>
              ) : null}
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="pt-4">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="mt-1 text-2xl tabular-nums">{value}</CardTitle>
      </CardContent>
    </Card>
  );
}
