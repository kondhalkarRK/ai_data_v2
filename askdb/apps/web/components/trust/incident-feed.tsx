"use client";

import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  Info,
} from "lucide-react";

import type { TrustIncident } from "@/components/trust/types";
import { EmptyState } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

const SEVERITY: Record<
  string,
  { className: string; Icon: typeof CircleAlert; label: string }
> = {
  critical: { className: "bg-danger/10 text-danger", Icon: CircleAlert, label: "Critical" },
  high: { className: "bg-danger/10 text-danger", Icon: CircleAlert, label: "High" },
  medium: {
    className: "bg-warning/15 text-warning-foreground dark:text-warning",
    Icon: AlertTriangle,
    label: "Medium",
  },
  low: { className: "bg-primary/10 text-primary", Icon: Info, label: "Low" },
  info: { className: "bg-success/10 text-success", Icon: CheckCircle2, label: "Info" },
};

export function IncidentFeed({
  incidents,
  history,
}: {
  incidents: TrustIncident[];
  history: TrustIncident[];
}) {
  if (!incidents.length && !history.length) {
    return (
      <EmptyState
        title="No active incidents"
        detail="All monitored datasets are healthy for the current industry."
      />
    );
  }

  return (
    <div className="space-y-3">
      {incidents.map((incident) => {
        const sev = SEVERITY[incident.severity] ?? SEVERITY.info!;
        const Icon = sev.Icon;
        return (
          <article
            key={incident.id}
            className="card-secondary p-4"
            title={`Blast radius: ${incident.blastRadius.kpis} KPIs, ${incident.blastRadius.dashboards} dashboards, ${incident.blastRadius.insights} AI insights`}
          >
            <div className="flex items-start gap-3">
              <span className={cn("icon-well", sev.className)} aria-hidden="true">
                <Icon className="size-3.5" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold">{incident.title}</h3>
                  <span className="rounded-md border border-border/60 px-2 py-0.5 text-[10px] text-muted-foreground">
                    {sev.label}
                  </span>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{incident.summary}</p>
                {incident.rootCauseHint ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Likely cause: {incident.rootCauseHint}
                  </p>
                ) : null}
                <p className="mt-2 text-[11px] text-muted-foreground">
                  Impact: {incident.impactedAssets.slice(0, 3).join(", ") || "—"}
                  {" · "}
                  {formatRelative(incident.detectedAt)}
                </p>
                <Link
                  href={`/semantic/ontology?focus=${encodeURIComponent(incident.dataset)}`}
                  className="mt-2 inline-block text-[11px] font-medium text-teal underline-offset-2 hover:underline"
                >
                  View details / lineage
                </Link>
              </div>
            </div>
          </article>
        );
      })}
      {history.length ? (
        <div className="card-supporting p-3 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">Resolved history</p>
          <ul className="mt-2 space-y-1">
            {history.map((item) => (
              <li key={item.id}>
                {item.title} — TTD {item.timeToDetectHours ?? "—"}h · TTR{" "}
                {item.timeToResolveHours ?? "—"}h
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">No resolved-incident history recorded yet.</p>
      )}
    </div>
  );
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const hours = Math.max(0, (Date.now() - then) / 3_600_000);
  if (hours < 1) return `${Math.round(hours * 60)} minutes ago`;
  if (hours < 48) return `${hours.toFixed(0)} hours ago`;
  return `${(hours / 24).toFixed(0)} days ago`;
}
