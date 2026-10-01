"use client";

import { BellRing, Clock3, Database, ShieldCheck } from "lucide-react";

import { ChartFrame } from "@/components/executive/cockpit/chart-frame";
import { formatCount, formatInr } from "@/components/executive/cockpit/format";
import type { AlertItem, DataReliability, Severity, TrustFilters } from "@/components/reliability/types";
import { DIMENSION_LABEL, EmptyNote, formatWhen, SEVERITIES, SEVERITY_DOT, SeverityChip } from "@/components/reliability/ui";
import { cn } from "@/lib/utils";

export function AlertCenter({
  data,
  filters,
  onFilter,
  onOpenRule,
  className,
}: {
  data: DataReliability;
  filters: TrustFilters;
  onFilter: (patch: TrustFilters) => void;
  onOpenRule: (id: string) => void;
  className?: string;
}) {
  const scoped = data.alerts.filter(
    (a) => (!filters.dimension || a.dimension === filters.dimension) && (!filters.dataset || a.dataset === filters.dataset),
  );
  const counts = Object.fromEntries(SEVERITIES.map((s) => [s, scoped.filter((a) => a.severity === s).length])) as Record<
    Severity,
    number
  >;
  const shown = filters.severity ? scoped.filter((a) => a.severity === filters.severity) : scoped;

  return (
    <ChartFrame
      title="Alert center"
      subtitle={scoped.length ? `${scoped.length} open alert${scoped.length === 1 ? "" : "s"} · newest first within severity` : "No open alerts"}
      exportName="dq-alerts"
      png={false}
      className={className}
      csv={() =>
        shown.map((a) => ({
          severity: a.severity,
          rule: a.title,
          dataset: a.datasetLabel,
          dimension: DIMENSION_LABEL[a.dimension],
          failed_records: a.failedRecords,
          unit: a.unit,
          business_impact: a.impact,
          value_at_risk: a.valueAtRisk ?? "",
          detected_at: a.detectedAt ?? "",
        }))
      }
    >
      {(expanded) => (
        <div className="flex h-full flex-col">
          <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Alert severity">
            <SeverityTab label="All" count={scoped.length} active={!filters.severity} onClick={() => onFilter({ severity: undefined })} />
            {SEVERITIES.map((s) => (
              <SeverityTab
                key={s}
                label={s[0]!.toUpperCase() + s.slice(1)}
                count={counts[s]}
                dot={SEVERITY_DOT[s]}
                active={filters.severity === s}
                onClick={() => onFilter({ severity: filters.severity === s ? undefined : s })}
              />
            ))}
          </div>
          <div className={cn("mt-3 space-y-2 overflow-y-auto pr-1", expanded ? "flex-1" : "max-h-[26rem]")}>
            {shown.length ? (
              shown.map((a) => <AlertCard key={a.id} alert={a} onOpen={() => onOpenRule(a.ruleId)} />)
            ) : (
              <div className="flex flex-col items-center gap-2 py-8 text-center">
                <span className="grid size-10 place-items-center rounded-full bg-[#dcf3ee] text-[#0f8f7e]">
                  <ShieldCheck className="size-5" />
                </span>
                <p className="text-xs font-medium text-slate-700">Nothing needs attention here.</p>
                <p className="text-2xs text-slate-400">Every monitored check in this view is within its target.</p>
              </div>
            )}
            {!shown.length && scoped.length ? <EmptyNote>Try another severity tab.</EmptyNote> : null}
          </div>
        </div>
      )}
    </ChartFrame>
  );
}

function SeverityTab({
  label,
  count,
  dot,
  active,
  onClick,
}: {
  label: string;
  count: number;
  dot?: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-2xs font-medium transition",
        active
          ? "border-[#8fb3f5] bg-[#eef4ff] text-[#2f5fc4]"
          : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 dark:border-border dark:bg-surface-raised",
      )}
    >
      {dot ? <span className="size-1.5 rounded-full" style={{ backgroundColor: dot }} /> : null}
      {label}
      <span className="tabular-nums text-slate-400">{count}</span>
    </button>
  );
}

function AlertCard({ alert, onOpen }: { alert: AlertItem; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group relative w-full overflow-hidden rounded-xl border border-slate-100 bg-white py-2.5 pl-4 pr-3 text-left transition hover:border-[#c9dafb] hover:shadow-sm dark:border-border dark:bg-surface-raised"
    >
      <span className="absolute inset-y-0 left-0 w-1" style={{ backgroundColor: SEVERITY_DOT[alert.severity] }} />
      <div className="flex items-start justify-between gap-2">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-slate-800 dark:text-foreground">
          {alert.kind === "error" ? <BellRing className="size-3.5 text-[#d69e2e]" /> : null}
          {alert.title}
        </p>
        <SeverityChip severity={alert.severity} />
      </div>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-600 dark:text-muted-foreground">{alert.impact}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-slate-400">
        <span className="inline-flex items-center gap-1">
          <Database className="size-3" />
          {alert.datasetLabel}
        </span>
        {alert.kind === "rule" ? (
          <span className="tabular-nums">
            {formatCount(alert.failedRecords)} failed {alert.unit}
          </span>
        ) : null}
        {alert.valueAtRisk ? <span>{formatInr(alert.valueAtRisk)} at risk</span> : null}
        <span className="inline-flex items-center gap-1">
          <Clock3 className="size-3" />
          {alert.detectedAt ? `detected ${formatWhen(alert.detectedAt)}` : "detected this run"}
        </span>
      </div>
    </button>
  );
}
