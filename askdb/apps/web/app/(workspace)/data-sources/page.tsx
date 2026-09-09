"use client";

import type { IndustryListResponse, ReadinessResponse } from "@nql/shared-types";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CircleSlash, MinusCircle } from "lucide-react";

import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";

type Status = ReadinessResponse["dependencies"][number]["status"];

const STATUS_PRESENTATION: Record<
  Status,
  { label: string; icon: typeof CheckCircle2; className: string }
> = {
  ok: { label: "Connected", icon: CheckCircle2, className: "text-success" },
  degraded: { label: "Degraded", icon: AlertTriangle, className: "text-warning" },
  unavailable: { label: "Unavailable", icon: CircleSlash, className: "text-danger" },
  not_configured: {
    label: "Not configured",
    icon: MinusCircle,
    className: "text-muted-foreground",
  },
};

export default function DataSourcesPage() {
  const readiness = useQuery({
    queryKey: ["readiness"],
    queryFn: () => apiClient.get<ReadinessResponse>("/ready"),
    // Connectivity is the whole point of this page, so it is polled rather than cached.
    refetchInterval: 30_000,
    staleTime: 0,
  });

  const industries = useQuery({
    queryKey: ["industries"],
    queryFn: () => apiClient.get<IndustryListResponse>("/api/v1/industries"),
  });

  return (
    <>
      <PageHeader
        title="Data Sources"
        description="Live status of every store this workspace depends on. Read directly from the API readiness probe."
      />

      {readiness.isPending ? (
        <LoadingState size="sm" title="Checking dependencies" />
      ) : readiness.isError ? (
        <Card>
          <CardContent className="pt-5 text-sm text-danger">
            The readiness probe could not be reached. The API is likely down.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {readiness.data.dependencies.map((dependency) => {
            const presentation = STATUS_PRESENTATION[dependency.status];
            const Icon = presentation.icon;
            return (
              <Card key={dependency.name}>
                <CardContent className="flex items-start gap-3 pt-5">
                  <Icon
                    className={cn("mt-0.5 size-5 shrink-0", presentation.className)}
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <CardTitle className="font-mono text-sm">{dependency.name}</CardTitle>
                    <p className={cn("text-xs font-medium", presentation.className)}>
                      {presentation.label}
                      {dependency.latencyMs !== null && dependency.latencyMs !== undefined
                        ? ` · ${dependency.latencyMs} ms`
                        : ""}
                    </p>
                    <CardDescription className="mt-1 break-words">
                      {dependency.detail}
                    </CardDescription>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <h2 className="mb-3 mt-8 text-base font-semibold tracking-tight">Industry packs</h2>
      {industries.isPending ? (
        <LoadingState size="sm" />
      ) : industries.isError ? (
        <p className="text-sm text-muted-foreground">Industry list unavailable.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {industries.data.industries.map((industry) => (
            <Card key={industry.id}>
              <CardContent className="pt-5">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base">{industry.label}</CardTitle>
                  {industry.isDefault ? (
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-2xs font-medium text-primary">
                      Default
                    </span>
                  ) : null}
                </div>
                <CardDescription className="mt-1">{industry.description}</CardDescription>
                <dl className="mt-3 flex gap-5 text-xs">
                  <div>
                    <dt className="text-muted-foreground">Database</dt>
                    <dd
                      className={cn(
                        "font-medium",
                        industry.databaseAvailable ? "text-success" : "text-danger",
                      )}
                    >
                      {industry.databaseAvailable ? "Reachable" : "Unreachable"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Semantic pack</dt>
                    <dd
                      className={cn(
                        "font-medium",
                        industry.semanticPackLoaded
                          ? "text-success"
                          : "text-muted-foreground",
                      )}
                    >
                      {industry.semanticPackLoaded ? "Loaded" : "Phase 2"}
                    </dd>
                  </div>
                </dl>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
