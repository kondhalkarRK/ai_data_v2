"use client";

import Link from "next/link";

import type { TrustIncident } from "@/components/trust/types";
import { cn } from "@/lib/utils";

const SEVERITY: Record<string, string> = {
  critical: "bg-rose-500",
  high: "bg-rose-400",
  medium: "bg-amber-400",
  low: "bg-sky-400",
  info: "bg-emerald-400",
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
      <Empty title="No active incidents" detail="No open data-quality incidents for the current industry." />
    );
  }

  return (
    <div className="space-y-3">
      {incidents.map((incident) => (
        <article
          key={incident.id}
          className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm"
          title={`Blast radius: ${incident.blastRadius.kpis} KPIs, ${incident.blastRadius.dashboards} dashboards, ${incident.blastRadius.insights} AI insights`}
        >
          <div className="flex items-start gap-3">
            <span className={cn("mt-1.5 size-2.5 shrink-0 rounded-full", SEVERITY[incident.severity])} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold">{incident.title}</h3>
                <span className="rounded-full border border-border/60 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                  {incident.severity}
                </span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">{incident.summary}</p>
              {incident.rootCauseHint ? (
                <p className="mt-1 text-xs text-muted-foreground">Likely cause: {incident.rootCauseHint}</p>
              ) : null}
              <p className="mt-2 text-[11px] text-muted-foreground">
                Impact: {incident.impactedAssets.slice(0, 3).join(" · ") || "—"} ·{" "}
                {formatRelative(incident.detectedAt)}
              </p>
              <Link
                href={`/semantic/ontology?focus=${encodeURIComponent(incident.dataset)}`}
                className="mt-2 inline-block text-[11px] font-medium underline-offset-2 hover:underline"
              >
                View details / lineage
              </Link>
            </div>
          </div>
        </article>
      ))}
      {history.length ? (
        <div className="rounded-xl border border-border/60 bg-muted/20 p-3 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">Resolved history</p>
          <ul className="mt-2 space-y-1">
            {history.map((item) => (
              <li key={item.id}>
                {item.title} · TTD {item.timeToDetectHours ?? "—"}h · TTR{" "}
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

function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-border/70 px-4 py-6 text-center">
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
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
