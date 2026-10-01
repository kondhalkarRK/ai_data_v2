"use client";

import { ArrowDownRight, ArrowUpRight, Car, Crown, IndianRupee, Package, ShoppingCart } from "lucide-react";
import type * as React from "react";

import { monotonePath } from "@/components/executive/cockpit/chart-utils";
import { formatCount, formatInr, formatPct, formatPts } from "@/components/executive/cockpit/format";
import { COCKPIT } from "@/components/executive/cockpit/palette";
import type { CockpitData, SelectHandler } from "@/components/executive/cockpit/types";
import { cn } from "@/lib/utils";

export function KpiStrip({ data, onSelect }: { data: CockpitData; onSelect: SelectHandler }) {
  const { kpis, period } = data;
  const history = data.trend.filter((p) => p.revenue != null).slice(-12);
  const compare = `vs ${period.priorLabel}`;
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:gap-5 xl:grid-cols-5">
      <KpiCard
        icon={<IndianRupee className="size-4" />}
        label="Total Revenue"
        value={formatInr(kpis.revenue.value)}
        growth={kpis.revenue.growth}
        foot={compare}
        spark={history.map((p) => p.revenue ?? 0)}
        accent={COCKPIT.blue}
        featured
      />
      <KpiCard
        icon={<Package className="size-4" />}
        label="Units Sold"
        value={formatCount(kpis.units.value)}
        growth={kpis.units.growth}
        foot={compare}
        spark={history.map((p) => p.units ?? 0)}
        accent={COCKPIT.teal}
      />
      <KpiCard
        icon={<ShoppingCart className="size-4" />}
        label="Total Orders"
        value={formatCount(kpis.orders.value)}
        growth={kpis.orders.growth}
        foot={`Avg price ${formatInr(kpis.avgPrice.value)} (${formatPct(kpis.avgPrice.growth, true)})`}
        accent={COCKPIT.grey}
      />
      <LeaderCard
        icon={<Car className="size-4" />}
        label="Top Model"
        name={kpis.topModel?.name}
        sub={kpis.topModel?.make ?? undefined}
        metric={kpis.topModel ? `${formatPct(kpis.topModel.share)} of revenue` : undefined}
        detail={kpis.topModel ? `${formatInr(kpis.topModel.revenue)} · ${formatPct(kpis.topModel.growth, true)} YoY` : undefined}
        onClick={kpis.topModel ? () => onSelect("model", kpis.topModel!.name) : undefined}
      />
      <LeaderCard
        icon={<Crown className="size-4" />}
        label="Top Make"
        name={kpis.topMake?.name}
        metric={kpis.topMake ? `${formatPct(kpis.topMake.share)} market share` : undefined}
        detail={
          kpis.topMake?.shareChange != null
            ? `${formatPts(kpis.topMake.shareChange)} ${compare}`
            : kpis.topMake
              ? formatInr(kpis.topMake.revenue)
              : undefined
        }
        onClick={kpis.topMake ? () => onSelect("make", kpis.topMake!.name) : undefined}
      />
    </div>
  );
}

function GrowthChip({ growth }: { growth: number | null }) {
  if (growth == null) return <span className="text-2xs text-slate-400">no prior data</span>;
  const up = growth >= 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-2xs font-semibold tabular-nums",
        up ? "bg-[#dff4f2] text-[#0f8f7e]" : "bg-[#fbe9e7] text-[#c8574d]",
      )}
    >
      <Icon className="size-3" />
      {formatPct(Math.abs(growth))}
    </span>
  );
}

function Sparkline({ values, colour }: { values: number[]; colour: string }) {
  if (values.length < 2) return null;
  const width = 96;
  const height = 30;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const points = values.map((v, i) => [
    (i / (values.length - 1)) * width,
    height - 3 - ((v - min) / span) * (height - 6),
  ]) as Array<[number, number]>;
  const line = monotonePath(points);
  const id = `spark-${colour.slice(1)}`;
  return (
    <svg width={width} height={height} className="shrink-0" aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={colour} stopOpacity={0.25} />
          <stop offset="100%" stopColor={colour} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={`${line} L${width},${height} L0,${height} Z`} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={colour} strokeWidth={1.6} />
    </svg>
  );
}

const cardBase =
  "relative overflow-hidden rounded-2xl border border-slate-200/70 bg-white/90 p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-14px_rgba(15,23,42,0.1)] dark:border-border dark:bg-surface-raised";

function KpiCard({
  icon,
  label,
  value,
  growth,
  foot,
  spark,
  accent,
  featured,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  growth: number | null;
  foot: string;
  spark?: number[];
  accent: string;
  featured?: boolean;
}) {
  return (
    <div
      className={cn(cardBase, featured && "bg-gradient-to-br from-[#eef4ff] via-white to-[#effaf9] dark:from-surface-raised dark:to-surface-raised")}
    >
      <div className="flex items-center gap-2 text-2xs font-medium uppercase tracking-wide text-slate-500">
        <span className="icon-well size-6 rounded-md" style={{ backgroundColor: `${accent}14`, color: accent }}>
          {icon}
        </span>
        {label}
      </div>
      <div className="mt-2 flex items-end justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-2xl font-semibold tracking-tight text-slate-900 tabular-nums dark:text-foreground">
            {value}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <GrowthChip growth={growth} />
            <span className="truncate text-2xs text-slate-400">{foot}</span>
          </div>
        </div>
        {spark ? <Sparkline values={spark} colour={accent} /> : null}
      </div>
    </div>
  );
}

function LeaderCard({
  icon,
  label,
  name,
  sub,
  metric,
  detail,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  name?: string;
  sub?: string;
  metric?: string;
  detail?: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      disabled={!onClick}
      onClick={onClick}
      className={cn(cardBase, "text-left transition enabled:hover:border-[#8fb3f5] enabled:hover:shadow-md")}
      title={onClick ? `Filter the dashboard to ${name}` : undefined}
    >
      <div className="flex items-center gap-2 text-2xs font-medium uppercase tracking-wide text-slate-500">
        <span className="icon-well size-6 rounded-md bg-[#e3ecfd] text-[#2f6fed]">{icon}</span>
        {label}
      </div>
      <p className="mt-2 truncate text-2xl font-semibold tracking-tight text-slate-900 dark:text-foreground">
        {name ?? "—"}
        {sub ? <span className="ml-1.5 text-xs font-medium text-slate-400">{sub}</span> : null}
      </p>
      <p className="mt-1 truncate text-xs font-medium text-[#2f6fed]">{metric ?? ""}</p>
      <p className="truncate text-2xs text-slate-400">{detail ?? ""}</p>
    </button>
  );
}