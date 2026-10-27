"use client";

import { ArrowDownRight, ArrowUpRight, Car, Crown, IndianRupee, Package, ShoppingCart } from "lucide-react";
import type * as React from "react";

import { monotonePath } from "@/components/executive/cockpit/chart-utils";
import { formatCount, formatInr, formatPct, formatPts } from "@/components/executive/cockpit/format";
import type { CockpitData, SelectHandler } from "@/components/executive/cockpit/types";
import { CHART_SERIES } from "@/lib/design";
import { cn } from "@/lib/utils";

export function KpiStrip({ data, onSelect }: { data: CockpitData; onSelect: SelectHandler }) {
  const { kpis, period } = data;
  const history = data.trend.filter((p) => p.revenue != null).slice(-12);
  const compare = `vs ${period.priorLabel}`;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:gap-4 xl:grid-cols-12">
      <KpiCard
        className="xl:col-span-4"
        icon={<IndianRupee className="size-4" />}
        label="Total revenue"
        value={formatInr(kpis.revenue.value)}
        growth={kpis.revenue.growth}
        foot={compare}
        spark={history.map((p) => p.revenue ?? 0)}
        accent={CHART_SERIES.primary}
        featured
      />
      <KpiCard
        className="xl:col-span-2"
        icon={<Package className="size-4" />}
        label="Units sold"
        value={formatCount(kpis.units.value)}
        growth={kpis.units.growth}
        foot={compare}
        spark={history.map((p) => p.units ?? 0)}
        accent={CHART_SERIES.secondary}
      />
      <KpiCard
        className="xl:col-span-2"
        icon={<ShoppingCart className="size-4" />}
        label="Total orders"
        value={formatCount(kpis.orders.value)}
        growth={kpis.orders.growth}
        foot={`ASP ${formatInr(kpis.avgPrice.value)} (${formatPct(kpis.avgPrice.growth, true)})`}
        accent={CHART_SERIES.axis}
        compact
      />
      <LeaderCard
        className="xl:col-span-2"
        icon={<Car className="size-4" />}
        label="Top model"
        name={kpis.topModel?.name}
        sub={kpis.topModel?.make ?? undefined}
        metric={kpis.topModel ? `${formatPct(kpis.topModel.share)} of revenue` : undefined}
        detail={kpis.topModel ? `${formatInr(kpis.topModel.revenue)} · ${formatPct(kpis.topModel.growth, true)} YoY` : undefined}
        onClick={kpis.topModel ? () => onSelect("model", kpis.topModel!.name) : undefined}
      />
      <LeaderCard
        className="xl:col-span-2"
        icon={<Crown className="size-4" />}
        label="Top make"
        name={kpis.topMake?.name}
        metric={kpis.topMake ? `${formatPct(kpis.topMake.share)} share` : undefined}
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
  if (growth == null) return <span className="text-2xs text-muted-foreground">no prior data</span>;
  const up = growth >= 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-2xs font-semibold tabular-nums",
        up ? "bg-success/12 text-success" : "bg-danger/12 text-danger",
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
  const id = `spark-${colour.replace(/\W/g, "")}`;
  return (
    <svg width={width} height={height} className="shrink-0" aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={colour} stopOpacity={0.22} />
          <stop offset="100%" stopColor={colour} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={`${line} L${width},${height} L0,${height} Z`} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={colour} strokeWidth={1.6} />
    </svg>
  );
}

function KpiCard({
  icon,
  label,
  value,
  growth,
  foot,
  spark,
  accent,
  featured,
  compact,
  className,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  growth: number | null;
  foot: string;
  spark?: number[];
  accent: string;
  featured?: boolean;
  compact?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "kpi-card relative p-4 sm:p-5",
        featured && "kpi-card--featured",
        className,
      )}
    >
      <div className="flex items-center gap-2 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
        <span className="icon-well size-6 rounded-md bg-muted/60" style={{ color: accent }}>
          {icon}
        </span>
        {label}
      </div>
      <div className={cn("mt-2 flex items-end justify-between gap-2", compact && "mt-3")}>
        <div className="min-w-0">
          <p className={cn("truncate font-semibold tracking-tight text-foreground tabular-nums", featured ? "text-2xl" : "text-xl")}>
            {value}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <GrowthChip growth={growth} />
            <span className="truncate text-2xs text-muted-foreground">{foot}</span>
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
  className,
}: {
  icon: React.ReactNode;
  label: string;
  name?: string;
  sub?: string;
  metric?: string;
  detail?: string;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      disabled={!onClick}
      onClick={onClick}
      className={cn(
        "kpi-card p-4 text-left transition enabled:hover:border-primary/35 enabled:hover:shadow-[var(--shadow-raised)] sm:p-5",
        className,
      )}
      title={onClick ? `Filter the dashboard to ${name}` : undefined}
    >
      <div className="flex items-center gap-2 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
        <span className="icon-well size-6 rounded-md bg-primary/10 text-primary">{icon}</span>
        {label}
      </div>
      <p className="mt-2 truncate text-xl font-semibold tracking-tight text-foreground">
        {name ?? "—"}
        {sub ? <span className="ml-1.5 text-xs font-medium text-muted-foreground">{sub}</span> : null}
      </p>
      <p className="mt-1 truncate text-xs font-medium text-primary">{metric ?? ""}</p>
      <p className="truncate text-2xs text-muted-foreground">{detail ?? ""}</p>
    </button>
  );
}
