"use client";

import type { DataQualityReport, PreviewTableSummary } from "@nql/shared-types";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";

export default function DataQualityPage() {
  const industry = useActiveIndustry();
  const [selected, setSelected] = useState<string | null>(null);

  const tables = useQuery({
    queryKey: ["data-tables", industry],
    queryFn: () => apiClient.get<PreviewTableSummary[]>("/api/v1/data/tables", { industry }),
  });

  const activeTable = selected ?? tables.data?.[0]?.name ?? null;

  const report = useQuery({
    queryKey: ["data-quality", industry, activeTable],
    enabled: Boolean(activeTable),
    queryFn: () =>
      apiClient.get<DataQualityReport>(`/api/v1/data/quality/${activeTable}`, { industry }),
  });

  return (
    <>
      <PageHeader
        title="Data Quality"
        description="Legacy scoring formula applied to a capped sample of the selected table."
      />

      {tables.isPending ? (
        <LoadingState size="sm" title="Loading tables" />
      ) : tables.isError ? (
        <Card>
          <CardContent className="pt-5 text-sm text-danger">
            Could not load tables for quality scoring.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
          <Card className="h-fit">
            <CardContent className="space-y-1 pt-4">
              <CardTitle className="mb-2 text-sm">Tables</CardTitle>
              {tables.data?.map((table) => (
                <button
                  key={table.name}
                  type="button"
                  onClick={() => setSelected(table.name)}
                  className={cn(
                    "w-full rounded-md px-2.5 py-2 text-left text-sm",
                    activeTable === table.name
                      ? "bg-primary/10 text-foreground"
                      : "text-muted-foreground hover:bg-muted/60",
                  )}
                >
                  {table.displayName}
                </button>
              ))}
            </CardContent>
          </Card>

          <div className="space-y-3">
            {report.isPending ? (
              <LoadingState size="sm" title="Scoring sample" />
            ) : report.isError ? (
              <Card>
                <CardContent className="pt-5 text-sm text-danger">
                  Quality scoring failed for {activeTable}.
                </CardContent>
              </Card>
            ) : report.data ? (
              <>
                <Card>
                  <CardContent className="flex flex-wrap items-end gap-6 pt-5">
                    <div>
                      <p className="text-2xs uppercase tracking-wide text-muted-foreground">
                        Health score
                      </p>
                      <p
                        className={cn(
                          "text-3xl font-semibold tabular-nums",
                          scoreClass(report.data.healthScore),
                        )}
                      >
                        {report.data.healthScore.toFixed(1)}
                      </p>
                    </div>
                    <Metric label="Sample rows" value={report.data.sampleRows.toLocaleString()} />
                    <Metric label="Null %" value={`${report.data.totalNullPct}%`} />
                    <Metric label="Duplicates" value={String(report.data.duplicateCount)} />
                    <Metric label="Outlier cols" value={String(Object.keys(report.data.outliers).length)} />
                    <Metric label="Date gaps" value={String(report.data.dateGaps.length)} />
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="space-y-2 pt-5">
                    <CardTitle className="text-sm">Findings</CardTitle>
                    <CardDescription>
                      Computed in {report.data.computedIn} on {report.data.physicalName}.
                    </CardDescription>
                    <IssueList
                      title="Null columns"
                      items={Object.entries(report.data.nullSummary).map(
                        ([column, detail]) => `${column}: ${detail.pct}% null`,
                      )}
                    />
                    <IssueList
                      title="Type issues"
                      items={report.data.typeIssues.map((item) => String(item.issue ?? item.column))}
                    />
                    <IssueList
                      title="Cardinality"
                      items={report.data.cardinalityFlags.map((item) =>
                        String(item.issue ?? item.column),
                      )}
                    />
                    <IssueList title="Missing months" items={report.data.dateGaps} />
                  </CardContent>
                </Card>
              </>
            ) : null}
          </div>
        </div>
      )}
    </>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-2xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-sm font-medium tabular-nums text-foreground">{value}</p>
    </div>
  );
}

function IssueList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <p className="text-xs font-medium text-foreground">{title}</p>
      <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
        {items.slice(0, 8).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function scoreClass(score: number): string {
  if (score >= 90) return "text-success";
  if (score >= 70) return "text-warning";
  return "text-danger";
}
