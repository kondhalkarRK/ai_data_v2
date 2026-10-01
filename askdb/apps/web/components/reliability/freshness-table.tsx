"use client";

import { ChartFrame } from "@/components/executive/cockpit/chart-frame";
import type { DataReliability, FreshnessRow, TrustFilters } from "@/components/reliability/types";
import { EmptyNote, formatHours, formatWhen, TRUST } from "@/components/reliability/ui";
import { cn } from "@/lib/utils";

const STATUS: Record<FreshnessRow["status"], { label: string; colour: string; bg: string }> = {
  on_time: { label: "On time", colour: "#0f7a6c", bg: "#dcf3ee" },
  delayed: { label: "Delayed", colour: "#94660f", bg: "#fdf3dc" },
  stale: { label: "Stale", colour: "#a8463d", bg: "#fbecea" },
  unknown: { label: "Not tracked", colour: "#64748b", bg: "#f1f5f9" },
};

export function FreshnessTable({
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
  const rows = data.freshness;
  const late = rows.filter((r) => r.status === "delayed" || r.status === "stale").length;
  return (
    <ChartFrame
      title="Data freshness"
      subtitle={late ? `${late} dataset${late === 1 ? "" : "s"} behind schedule` : "All tracked datasets on schedule"}
      exportName="data-freshness"
      png={false}
      className={className}
      csv={() =>
        rows.map((r) => ({
          dataset: r.label,
          cadence: r.cadence,
          last_refresh: r.lastRefresh ?? "",
          expected_by: r.expectedBy ?? "",
          sla_hours: r.slaHours ?? "",
          lag_hours: r.lagHours ?? "",
          delay_hours: r.delayHours ?? "",
          status: r.status,
        }))
      }
    >
      {() =>
        rows.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-xs">
              <thead className="text-[10px] uppercase tracking-wide text-slate-500">
                <tr className="border-b border-slate-100 dark:border-border">
                  <th className="py-2 pr-3 font-medium">Dataset</th>
                  <th className="py-2 pr-3 font-medium">Last refresh</th>
                  <th className="py-2 pr-3 font-medium">Expected by</th>
                  <th className="py-2 pr-3 font-medium">Delay</th>
                  <th className="py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-border">
                {rows.map((r) => {
                  const s = STATUS[r.status];
                  return (
                    <tr
                      key={r.dataset}
                      className={cn(
                        "cursor-pointer transition hover:bg-slate-50 dark:hover:bg-muted",
                        filters.dataset === r.dataset && "bg-[#f1f6ff]",
                      )}
                      onClick={() => (r.ruleId ? onOpenRule(r.ruleId) : onFilter({ dataset: r.dataset }))}
                    >
                      <td className="py-2 pr-3">
                        <p className="font-medium text-slate-800 dark:text-foreground">{r.label}</p>
                        <p className="text-[10px] capitalize text-slate-400">
                          {r.cadence}
                          {r.slaHours ? ` · SLA ${formatHours(r.slaHours)}` : ""}
                        </p>
                      </td>
                      <td className="whitespace-nowrap py-2 pr-3 text-slate-600">{formatWhen(r.lastRefresh)}</td>
                      <td className="whitespace-nowrap py-2 pr-3 text-slate-600">{formatWhen(r.expectedBy)}</td>
                      <td className="whitespace-nowrap py-2 pr-3 tabular-nums">
                        {r.delayHours && r.delayHours > 0 ? (
                          <span style={{ color: r.status === "stale" ? TRUST.coral : TRUST.amberInk }}>
                            {formatHours(r.delayHours)} late
                          </span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="py-2">
                        <span className="rounded-full px-2 py-0.5 text-2xs font-medium" style={{ color: s.colour, backgroundColor: s.bg }}>
                          {s.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyNote>No freshness expectations configured.</EmptyNote>
        )
      }
    </ChartFrame>
  );
}
