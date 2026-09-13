"use client";

import type {
  DatasetProfile,
  DqRule,
  GovernanceRecord,
  LineageImpact,
  NotificationRule,
  SchemaChange,
  TrendPoint,
} from "@/components/trust/types";
import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";
import Link from "next/link";
import * as React from "react";

export function QualityTrends({ trends }: { trends: TrendPoint[] }) {
  if (!trends.length) {
    return <Empty label="No trend history yet. Scores accumulate as Trust Center refreshes." />;
  }
  const max = Math.max(...trends.map((t) => t.trustScore ?? 0), 1);
  return (
    <div className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold">Data Quality Trends</h3>
      <div className="flex h-36 items-end gap-1">
        {trends.map((point) => (
          <div
            key={point.period}
            className="flex-1 rounded-t bg-foreground/70"
            style={{ height: `${Math.max(((point.trustScore ?? 0) / max) * 100, 4)}%` }}
            title={`${point.period}: ${point.trustScore ?? "—"}`}
          />
        ))}
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">
        Latest failed checks: {trends.at(-1)?.failedChecks ?? 0}
      </p>
    </div>
  );
}

export function SchemaDriftMonitor({ changes }: { changes: SchemaChange[] }) {
  if (!changes.length) {
    return <Empty label="No schema changes detected." />;
  }
  return (
    <div className="space-y-3">
      {changes.map((change) => (
        <article key={change.dataset} className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
          <h3 className="text-sm font-semibold">{change.displayName}</h3>
          <p className="text-xs text-muted-foreground">
            Version {change.fromVersion ?? "—"} → {change.toVersion ?? "—"}
          </p>
          <div className="mt-2 grid gap-2 text-xs sm:grid-cols-2">
            <div>
              <p className="font-medium text-emerald-700 dark:text-emerald-300">Added</p>
              <ul>{change.added.map((c) => <li key={c}>+ {c}</li>)}</ul>
              {!change.added.length ? <p className="text-muted-foreground">None</p> : null}
            </div>
            <div>
              <p className="font-medium text-rose-700 dark:text-rose-300">Removed</p>
              <ul>{change.removed.map((c) => <li key={c}>- {c}</li>)}</ul>
              {!change.removed.length ? <p className="text-muted-foreground">None</p> : null}
            </div>
          </div>
          <ol className="mt-3 space-y-1 text-[11px] text-muted-foreground">
            {change.timeline.map((step) => (
              <li key={`${step.at}-${step.event}`}>
                {step.at} · {step.event}
              </li>
            ))}
          </ol>
        </article>
      ))}
    </div>
  );
}

export function ProfilingWorkspace({ profiles }: { profiles: DatasetProfile[] }) {
  const [selected, setSelected] = React.useState(profiles[0]?.name ?? "");
  const active = profiles.find((p) => p.name === selected) ?? profiles[0];
  if (!profiles.length || !active) {
    return <Empty label="Profiling information not available." />;
  }
  return (
    <div className="grid gap-3 lg:grid-cols-[200px_minmax(0,1fr)]">
      <div className="space-y-1 rounded-2xl border border-border/70 bg-background p-2">
        {profiles.map((p) => (
          <button
            key={p.name}
            type="button"
            className={`w-full rounded-lg px-2 py-1.5 text-left text-xs ${
              active.name === p.name ? "bg-muted font-medium" : "text-muted-foreground hover:bg-muted/50"
            }`}
            onClick={() => setSelected(p.name)}
          >
            {p.displayName}
          </button>
        ))}
      </div>
      <div className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
        <h3 className="text-sm font-semibold">{active.displayName}</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Rows: {active.rows.toLocaleString()} · Columns: {active.columns} · Null %: {active.nullPct}% ·
          Duplicates: {active.duplicates}%
          {active.lastRefresh ? ` · Last refresh: ${new Date(active.lastRefresh).toLocaleString()}` : ""}
        </p>
        <ul className="mt-3 max-h-72 space-y-2 overflow-auto text-xs">
          {active.columnProfiles.map((col) => (
            <li key={`${col.name}-${col.issue ?? "ok"}`} className="rounded-lg border border-border/50 px-2 py-1.5">
              <p className="font-medium">{col.name}</p>
              <p className="text-muted-foreground">
                Null {col.nullPct}%
                {col.distinctCount != null ? ` · Distinct ${col.distinctCount}` : ""}
                {col.pattern ? ` · ${col.pattern}` : ""}
              </p>
              {col.issue ? <p className="text-amber-700 dark:text-amber-300">{col.issue}</p> : null}
            </li>
          ))}
          {!active.columnProfiles.length ? (
            <li className="text-muted-foreground">No column findings in this sample.</li>
          ) : null}
        </ul>
      </div>
    </div>
  );
}

export function GovernanceCenter({ records }: { records: GovernanceRecord[] }) {
  if (!records.length) return <Empty label="No governance metadata available." />;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {records.map((r) => (
        <article key={r.dataset} className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
          {r.restricted ? (
            <p className="mb-2 text-[11px] text-amber-700 dark:text-amber-300">
              Classification: {r.classification} — detailed ownership shown under existing access policy.
            </p>
          ) : null}
          <h3 className="text-sm font-semibold">{r.displayName}</h3>
          <dl className="mt-2 space-y-1 text-xs text-muted-foreground">
            <div>Technical Owner: {r.technicalOwner ?? "—"}</div>
            <div>Business Owner: {r.businessOwner ?? "—"}</div>
            <div>Classification: {r.classification}</div>
            <div>Certified: {r.certified ? "✓" : "—"}</div>
            <div>Glossary: {r.glossaryLinked ? "Linked" : "Not linked"}</div>
            <div>Semantic Layer: {r.semanticLinked ? "Linked" : "—"}</div>
            <div>Lineage: {r.lineageAvailable ? "Available" : "—"}</div>
            <div>DQ Rules: {r.activeRules} active</div>
          </dl>
        </article>
      ))}
    </div>
  );
}

export function LineageImpactExplorer({ lineage }: { lineage: LineageImpact[] }) {
  if (!lineage.length) return <Empty label="No lineage impact graphs available." />;
  return (
    <div className="space-y-3">
      {lineage.slice(0, 6).map((item) => (
        <div key={item.dataset} className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{item.dataset}</h3>
            <Link href={item.explorePath} className="text-[11px] font-medium underline-offset-2 hover:underline">
              Open Semantic Galaxy
            </Link>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            {item.nodes.map((n) => String(n.label ?? n.id)).join(" → ")}
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            Blast radius preview: {item.nodes.filter((n) => n.kind === "kpi").length} KPIs,{" "}
            {item.nodes.filter((n) => n.kind === "dashboard").length} dashboards,{" "}
            {item.nodes.filter((n) => n.kind === "insight").length} AI insights
          </p>
        </div>
      ))}
    </div>
  );
}

export function RuleManagement({
  rules,
  notifications,
}: {
  rules: DqRule[];
  notifications: NotificationRule[];
}) {
  const industry = useActiveIndustry();
  const [local, setLocal] = React.useState(rules);
  React.useEffect(() => setLocal(rules), [rules]);

  async function saveThreshold(rule: DqRule, threshold: number) {
    try {
      await apiClient.patch(`/api/v1/trust/rules/${encodeURIComponent(rule.id)}`, { threshold }, { industry });
      setLocal((prev) =>
        prev.map((r) => (r.id === rule.id ? { ...r, threshold, passing: r.observed < threshold } : r)),
      );
    } catch {
      // keep prior
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
        <h3 className="mb-3 text-sm font-semibold">DQ Rules</h3>
        {!local.length ? (
          <p className="text-xs text-muted-foreground">No rules derived from the DQ engine.</p>
        ) : (
          <ul className="space-y-2">
            {local.map((rule) => (
              <li key={rule.id} className="grid gap-2 rounded-xl border border-border/50 px-3 py-2 text-xs md:grid-cols-[1fr_auto]">
                <div>
                  <p className="font-medium">
                    {rule.name}{" "}
                    <span className={rule.passing ? "text-emerald-600" : "text-rose-600"}>
                      {rule.passing ? "Passing" : "Failing"}
                    </span>
                  </p>
                  <p className="text-muted-foreground">
                    {rule.dataset} · observed {rule.observed}
                    {rule.unit === "percent" ? "%" : ""} · owner {rule.owner}
                  </p>
                </div>
                {rule.editable ? (
                  <label className="flex items-center gap-2">
                    Threshold
                    <input
                      type="number"
                      className="h-8 w-20 rounded-md border border-border bg-background px-2"
                      defaultValue={rule.threshold}
                      onBlur={(e) => void saveThreshold(rule, Number(e.target.value))}
                    />
                  </label>
                ) : (
                  <p className="text-muted-foreground">Read-only check</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
        <h3 className="mb-2 text-sm font-semibold">Notification rules</h3>
        <p className="mb-3 text-xs text-muted-foreground">
          Architecture for Slack / email / Teams / webhook. Channels enable incrementally — disabled rules
          never pretend to send.
        </p>
        <ul className="space-y-2 text-xs">
          {notifications.map((rule) => (
            <li key={rule.id} className="rounded-xl border border-border/50 px-3 py-2">
              <p className="font-medium">
                {rule.name} · {rule.channel} · min {rule.minSeverity}
              </p>
              <p className="text-muted-foreground">
                {rule.enabled ? "Enabled" : "Disabled"}{rule.note ? ` — ${rule.note}` : ""}
              </p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return (
    <div className="rounded-[var(--radius-card)] border border-dashed border-border/80 bg-surface/60 px-4 py-8 text-center">
      <p className="text-sm font-medium text-foreground">{label}</p>
      <p className="mt-1 text-sm text-muted-foreground">
        Your datasets have remained stable — nothing needs attention here right now.
      </p>
    </div>
  );
}
