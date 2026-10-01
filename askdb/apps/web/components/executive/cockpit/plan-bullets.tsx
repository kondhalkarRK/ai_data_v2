"use client";

import { Info } from "lucide-react";

import { ChartFrame } from "@/components/executive/cockpit/chart-frame";
import { useElementSize } from "@/components/executive/cockpit/chart-utils";
import { formatCount, formatInr, formatPct } from "@/components/executive/cockpit/format";
import { COCKPIT } from "@/components/executive/cockpit/palette";
import type { BulletMetric, CockpitData, SelectHandler } from "@/components/executive/cockpit/types";
import { cn } from "@/lib/utils";

export function PlanBullets({
  data,
  onSelect,
  className,
}: {
  data: CockpitData;
  onSelect: SelectHandler;
  className?: string;
}) {
  const plan = data.plan;
  const metrics: Array<{ metric: BulletMetric; reference: string }> = [
    { metric: plan.revenue, reference: "Target" },
    { metric: plan.units, reference: "Target" },
    { metric: plan.forecastRevenue, reference: "Forecast" },
    { metric: plan.forecastUnits, reference: "Forecast" },
  ];
  return (
    <ChartFrame
      title="Forecast & target"
      subtitle={plan.monthsLabel ? `Completed months: ${plan.monthsLabel}` : "No completed month in this period yet"}
      exportName="forecast-target"
      className={className}
      csv={() => [
        ...metrics.map(({ metric, reference }) => ({
          measure: metric.label,
          actual: metric.actual,
          [reference.toLowerCase()]: metric.target,
          achievement_pct: metric.achievement == null ? null : +(metric.achievement * 100).toFixed(2),
        })),
        ...plan.byMake.map((m) => ({
          measure: `Units vs target · ${m.make}`,
          actual: m.actualUnits,
          target: m.targetUnits,
          achievement_pct: +(m.achievement * 100).toFixed(2),
        })),
      ]}
    >
      {() => (
        <div className="space-y-4">
          <div className="space-y-3">
            <div className="grid gap-x-6 gap-y-3 md:grid-cols-2">
              {metrics.map(({ metric, reference }) => (
                <Bullet key={metric.label} metric={metric} reference={reference} />
              ))}
            </div>
            {[plan.targetNote, plan.forecastNote].filter(Boolean).map((note) => (
              <p key={note} className="flex items-start gap-1.5 text-2xs text-slate-500">
                <Info className="mt-px size-3 shrink-0" />
                {note}
              </p>
            ))}
          </div>
          {plan.byMake.length ? (
            <div>
              <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                Target achievement by brand · units
              </p>
              <ul className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
                {plan.byMake.slice(0, 12).map((m) => (
                  <li key={m.make}>
                    <button
                      type="button"
                      className="grid w-full grid-cols-[5.5rem_minmax(3rem,1fr)_2.5rem] items-center gap-2 rounded px-1 py-0.5 text-left text-2xs hover:bg-slate-50 dark:hover:bg-muted"
                      onClick={() => onSelect("make", m.make)}
                      title={`${m.make}: ${formatCount(m.actualUnits)} of ${formatCount(m.targetUnits)} units`}
                    >
                      <span className="truncate font-medium text-slate-700 dark:text-foreground">{m.make}</span>
                      <MiniBullet achievement={m.achievement} />
                      <span
                        className={cn(
                          "text-right font-semibold tabular-nums",
                          m.achievement >= 1 ? "text-[#0f8f7e]" : m.achievement < 0.9 ? "text-[#c8574d]" : "text-slate-600",
                        )}
                      >
                        {formatPct(m.achievement, false, 0)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}
    </ChartFrame>
  );
}

function Bullet({ metric, reference }: { metric: BulletMetric; reference: string }) {
  const [ref, size] = useElementSize<HTMLDivElement>();
  const fmt = (v: number | null) => (metric.format === "currency" ? formatInr(v) : formatCount(v));
  const target = metric.target;
  const scale = Math.max((target ?? 0) * 1.25, metric.actual * 1.05, 1);
  const w = size.width;
  const px = (v: number) => (v / scale) * w;
  const variance = target ? metric.actual - target : null;
  const ach = metric.achievement;
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-xs font-semibold text-slate-700 dark:text-foreground">{metric.label}</span>
        <span className="flex items-baseline gap-2">
          {variance != null ? (
            <span className={cn("text-2xs font-semibold tabular-nums", variance >= 0 ? "text-[#0f8f7e]" : "text-[#c8574d]")}>
              {variance >= 0 ? "▲" : "▼"} {fmt(Math.abs(variance))}
            </span>
          ) : null}
          <span
            className={cn(
              "text-sm font-bold tabular-nums",
              ach == null ? "text-slate-400" : ach >= 1 ? "text-[#0f8f7e]" : ach < 0.9 ? "text-[#c8574d]" : "text-slate-700",
            )}
          >
            {ach == null ? "n/a" : formatPct(ach, false, 0)}
          </span>
        </span>
      </div>
      <div ref={ref} className="h-6 w-full">
        {w > 0 ? (
          <svg data-chart width={w} height={24} role="img" aria-label={metric.label}>
            {target ? (
              <>
                <rect x={0} y={2} width={px(target * 0.8)} height={20} rx={4} fill="#e2e8f0" />
                <rect x={px(target * 0.8)} y={2} width={px(target * 0.2)} height={20} fill="#edf1f6" />
                <rect x={px(target)} y={2} width={Math.max(w - px(target), 0)} height={20} fill="#f6f8fb" />
              </>
            ) : (
              <rect x={0} y={2} width={w} height={20} rx={4} fill="#f1f5f9" />
            )}
            <rect x={0} y={8} width={px(metric.actual)} height={8} rx={4} fill={ach != null && ach < 0.9 ? "#7c9cc9" : COCKPIT.blue} />
            {target ? <rect x={px(target) - 1.5} y={0} width={3} height={24} rx={1} fill={COCKPIT.ink} /> : null}
          </svg>
        ) : null}
      </div>
      <div className="mt-1 flex justify-between gap-2 text-2xs text-slate-500">
        <span>
          Actual <span className="font-semibold text-slate-700 dark:text-foreground">{fmt(metric.actual)}</span>
        </span>
        <span>
          {reference} <span className="font-semibold text-slate-700 dark:text-foreground">{fmt(target)}</span>
        </span>
      </div>
    </div>
  );
}

function MiniBullet({ achievement }: { achievement: number }) {
  const pct = Math.min(achievement / 1.25, 1) * 100;
  return (
    <span className="relative block h-2 rounded-full bg-slate-100 dark:bg-muted">
      <span
        className="absolute inset-y-0 left-0 rounded-full"
        style={{ width: `${pct}%`, backgroundColor: achievement >= 1 ? COCKPIT.teal : achievement < 0.9 ? "#e3a19a" : COCKPIT.blueSoft }}
      />
      <span className="absolute -inset-y-0.5 w-0.5 rounded bg-slate-700" style={{ left: `${100 / 1.25}%` }} />
    </span>
  );
}
