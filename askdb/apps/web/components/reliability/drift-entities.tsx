"use client";

import { GitCompareArrows, Sparkle } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { DataReliability } from "@/components/reliability/types";
import { Card, EmptyNote, formatWhen, PanelTitle, TRUST } from "@/components/reliability/ui";
import { cn } from "@/lib/utils";

const DRIFT_STATUS: Record<DataReliability["schemaDrift"]["status"], { colour: string; bg: string }> = {
  stable: { colour: "#0f7a6c", bg: "#dcf3ee" },
  drift: { colour: "#94660f", bg: "#fdf3dc" },
  not_checked: { colour: "#64748b", bg: "#f1f5f9" },
  unavailable: { colour: "#64748b", bg: "#f1f5f9" },
};

export function SchemaDriftPanel({ data, className }: { data: DataReliability; className?: string }) {
  const { schemaDrift: drift } = data;
  const style = DRIFT_STATUS[drift.status];
  return (
    <Card className={className}>
      <PanelTitle
        title="Schema drift monitoring"
        subtitle="Structural changes to monitored tables and their downstream impact"
        right={
          <span className="rounded-full px-2 py-0.5 text-2xs font-medium" style={{ color: style.colour, backgroundColor: style.bg }}>
            {drift.label}
          </span>
        }
      />
      {drift.events.length ? (
        <ol className="relative ml-1.5 space-y-3 border-l border-slate-200 pl-4 dark:border-border">
          {drift.events.slice(0, 8).map((e) => (
            <li key={e.id} className="relative">
              <span
                className="absolute -left-[21px] top-1 grid size-2.5 place-items-center rounded-full ring-2 ring-white dark:ring-surface-raised"
                style={{ backgroundColor: e.severity === "high" || e.severity === "critical" ? TRUST.amber : TRUST.teal }}
              />
              <p className="text-xs font-medium text-slate-800 dark:text-foreground">{e.summary}</p>
              <p className="text-[10px] text-slate-400">
                <span className="capitalize">{e.kind.replace(/_/g, " ")}</span>
                {e.table ? ` · ${e.table}${e.column ? `.${e.column}` : ""}` : ""} · {formatWhen(e.detectedAt)}
              </p>
              {Object.keys(e.impact).length ? (
                <p className="mt-0.5 text-[11px] text-slate-500">{Object.values(e.impact).slice(0, 2).join(" · ")}</p>
              ) : null}
            </li>
          ))}
        </ol>
      ) : (
        <div className="flex items-center gap-3 rounded-xl bg-slate-50 px-3 py-3 dark:bg-muted">
          <GitCompareArrows className="size-5 shrink-0 text-[#14a3a1]" />
          <p className="text-[11px] leading-relaxed text-slate-600 dark:text-muted-foreground">
            {drift.status === "stable"
              ? "No column additions, removals or type changes detected in the last 30 days."
              : drift.status === "not_checked"
                ? "Schema has not been snapshotted yet. Run a catalog refresh from the Entity Catalog to start tracking drift."
                : "Schema history is unavailable for this source."}
          </p>
        </div>
      )}
    </Card>
  );
}

export function EntityChangesPanel({ data, className }: { data: DataReliability; className?: string }) {
  const { entities } = data;
  const [open, setOpen] = React.useState<string | null>(null);
  return (
    <Card className={className}>
      <PanelTitle
        title="New business entities"
        subtitle={
          entities.available
            ? `From the Entity Catalog · last 30 days${entities.lastRefreshAt ? ` · refreshed ${formatWhen(entities.lastRefreshAt)}` : ""}`
            : "Entity Catalog integration"
        }
        right={
          <Link href="/semantic/catalog" className="text-2xs font-medium text-[#2f6fed] hover:underline">
            Open catalog
          </Link>
        }
      />
      {!entities.available ? (
        <EmptyNote>The Entity Catalog has not been refreshed for this industry yet.</EmptyNote>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {entities.groups.map((g) => (
              <button
                key={g.key}
                type="button"
                disabled={!g.count}
                onClick={() => setOpen(open === g.key ? null : g.key)}
                className={cn(
                  "rounded-xl border px-3 py-2 text-left transition enabled:hover:border-[#8fb3f5]",
                  open === g.key ? "border-[#8fb3f5] bg-[#f1f6ff]" : "border-slate-100 dark:border-border",
                )}
              >
                <p className="text-[10px] uppercase tracking-wide text-slate-400">{g.label}</p>
                <p className={cn("text-lg font-semibold tabular-nums", g.count ? "text-slate-800 dark:text-foreground" : "text-slate-300")}>
                  {g.count ? `+${g.count}` : "0"}
                </p>
              </button>
            ))}
          </div>
          {open ? (
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {entities.groups
                .find((g) => g.key === open)
                ?.values.map((v) => (
                  <li
                    key={`${v.domain}:${v.value}`}
                    className="inline-flex items-center gap-1 rounded-full bg-[#dff4f2] px-2 py-0.5 text-2xs text-[#0e6f6d]"
                    title={v.firstSeenAt ? `First seen ${formatWhen(v.firstSeenAt)}` : undefined}
                  >
                    <Sparkle className="size-3" />
                    {v.value}
                  </li>
                ))}
            </ul>
          ) : entities.total ? (
            <p className="mt-3 text-[11px] text-slate-500">
              {entities.total} new value{entities.total === 1 ? "" : "s"} appeared. Confirm they are expected before they reach executive reports.
            </p>
          ) : (
            <p className="mt-3 text-[11px] text-slate-500">No new brands, models, dealers or locations in the last 30 days.</p>
          )}
        </>
      )}
    </Card>
  );
}
