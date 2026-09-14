"use client";

import type { IndustryListResponse, ReadinessResponse } from "@nql/shared-types";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  Database,
  MinusCircle,
} from "lucide-react";
import Link from "next/link";

import { LoadingState } from "@/components/loading/loading-state";
import type { DataTrustCenter } from "@/components/trust/types";
import { useActiveIndustry } from "@/hooks/use-session";
import { useTrustSnapshot } from "@/hooks/use-trust-snapshot";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";

type Status = ReadinessResponse["dependencies"][number]["status"];

const STATUS_PRESENTATION: Record<
  Status,
  { label: string; icon: typeof CheckCircle2; className: string; dot: string }
> = {
  ok: {
    label: "Connected",
    icon: CheckCircle2,
    className: "text-success",
    dot: "bg-success",
  },
  degraded: {
    label: "Degraded",
    icon: AlertTriangle,
    className: "text-warning",
    dot: "bg-warning",
  },
  unavailable: {
    label: "Unavailable",
    icon: CircleSlash,
    className: "text-danger",
    dot: "bg-danger",
  },
  not_configured: {
    label: "Not connected",
    icon: MinusCircle,
    className: "text-muted-foreground",
    dot: "bg-muted-foreground/50",
  },
};

export function ConnectedDataSources() {
  const industry = useActiveIndustry();
  const readiness = useQuery({
    queryKey: ["readiness"],
    queryFn: () => apiClient.get<ReadinessResponse>("/ready"),
    refetchInterval: 30_000,
    staleTime: 0,
  });
  const industries = useQuery({
    queryKey: ["industries"],
    queryFn: () => apiClient.get<IndustryListResponse>("/api/v1/industries"),
  });
  const trust = useTrustSnapshot();
  const center = useQuery({
    queryKey: ["data-trust-center-summary", industry],
    queryFn: () => apiClient.get<DataTrustCenter>("/api/v1/trust/center", { industry }),
    staleTime: 60_000,
  });

  const dataAsOf = center.data?.dataAsOf
    ? new Date(center.data.dataAsOf).toLocaleString(undefined, {
        hour: "numeric",
        minute: "2-digit",
      })
    : null;
  const openIncidents =
    trust.data?.activeIncidents ?? center.data?.hero.activeIncidents ?? 0;

  return (
    <section id="data-sources" className="scroll-mt-24">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-foreground">
            Connected Data Sources
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Live readiness from the API probe — not placeholder status.
          </p>
        </div>
        <Link
          href="/data-quality"
          className="text-xs font-medium text-primary underline-offset-2 hover:underline"
        >
          Open Data Trust Center
        </Link>
      </div>

      {openIncidents > 0 ? (
        <p className="mb-3 rounded-lg border border-warning/30 bg-warning/8 px-3 py-2 text-xs text-amber-900 dark:text-amber-100">
          {openIncidents} active incident{openIncidents === 1 ? "" : "s"} in Data Trust Center —
          connection dots below reflect readiness, not a clean bill of health.
        </p>
      ) : null}

      {readiness.isPending ? (
        <LoadingState size="sm" title="Checking dependencies" />
      ) : readiness.isError ? (
        <p className="text-sm text-danger">The readiness probe could not be reached.</p>
      ) : (
        <ul className="space-y-2">
          {readiness.data.dependencies.map((dependency) => {
            const presentation = STATUS_PRESENTATION[dependency.status];
            const Icon = presentation.icon;
            const showFreshness =
              dependency.status === "ok" &&
              Boolean(dataAsOf) &&
              /postgres|analytics|automotive|insurance/i.test(dependency.name);
            return (
              <li
                key={dependency.name}
                className="flex items-start gap-3 rounded-lg border border-border/60 bg-background/60 px-3 py-2.5"
              >
                <span className="mt-1.5 flex items-center gap-1.5" aria-hidden="true">
                  <span className={cn("size-2 rounded-full", presentation.dot)} />
                  <Icon className={cn("size-3.5", presentation.className)} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-sm text-foreground">{dependency.name}</p>
                  <p className={cn("text-xs font-medium", presentation.className)}>
                    {presentation.label}
                    {dependency.latencyMs != null ? ` · ${dependency.latencyMs} ms` : ""}
                    {showFreshness ? ` · Data as of ${dataAsOf}` : ""}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{dependency.detail}</p>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <h3 className="mb-2 mt-6 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        Industry packs
      </h3>
      {industries.isPending ? (
        <LoadingState size="sm" />
      ) : industries.isError ? (
        <p className="text-sm text-muted-foreground">Industry list unavailable.</p>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {industries.data.industries.map((pack) => (
            <li
              key={pack.id}
              className={cn(
                "rounded-lg border border-border/60 bg-background/60 px-3 py-2.5",
                pack.id === industry && "border-primary/30",
              )}
            >
              <div className="flex items-center gap-2">
                <Database className="size-3.5 text-muted-foreground" aria-hidden="true" />
                <p className="text-sm font-medium">{pack.label}</p>
                {pack.isDefault ? (
                  <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                    Default
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Database {pack.databaseAvailable ? "reachable" : "unreachable"}
                {" · "}
                Semantic pack {pack.semanticPackLoaded ? "loaded" : "not loaded"}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
