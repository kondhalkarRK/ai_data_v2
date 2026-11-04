"use client";

import {
  Activity,
  Car,
  CircleDollarSign,
  Gauge,
  Percent,
  Shield,
  TrendingDown,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import * as React from "react";

import { formatCount, formatInr, formatPct } from "@/components/executive/cockpit/format";
import type { ExecKpiCard } from "@/components/executive/types";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { useDashboardActions } from "@/components/executive/dashboard-intelligence";
import { EmptyState } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

function formatKpiAnim(n: number, card: ExecKpiCard): string {
  const fmt = (card.format || "").toLowerCase();
  if (fmt.includes("percent") || card.formatted.includes("%")) {
    // Values may already be 0–1 ratios or 0–100; match final string shape.
    if (Math.abs(card.value ?? 0) <= 1.5 && card.formatted.includes("%")) {
      return formatPct(n);
    }
    return `${n.toFixed(1)}%`;
  }
  if (fmt.includes("currency") || fmt.includes("money") || card.formatted.includes("₹")) {
    return formatInr(n);
  }
  if (fmt === "text") return card.formatted;
  return formatCount(n);
}

const KPI_ICONS: LucideIcon[] = [CircleDollarSign, Gauge, Percent, Car, Shield, Activity];

export function KpiCardsGrid({
  cards,
  compareLabel,
  onExplore,
  presenterMode,
}: {
  cards: ExecKpiCard[];
  compareLabel: string;
  onExplore?: (kpiId: string) => void;
  presenterMode?: boolean;
}) {
  const dashboard = useDashboardActions();
  if (!cards.length) {
    return (
      <EmptyState
        title="No KPIs for this window"
        detail="Connect analytics data or widen filters to populate executive metrics."
      />
    );
  }

  const cols =
    cards.length === 1
      ? "sm:grid-cols-1 max-w-sm"
      : cards.length === 2
        ? "sm:grid-cols-2"
        : cards.length === 3
          ? "sm:grid-cols-2 xl:grid-cols-3"
          : "sm:grid-cols-2 xl:grid-cols-4";

  return (
    <div className={cn("grid gap-3", cols)}>
      {cards.map((card, index) => {
        const Icon = KPI_ICONS[index % KPI_ICONS.length]!;
        const featured = index === 0;
        const ratio = dashboard?.metrics.find((metric) => metric.id === card.id && metric.format === "percent");
        const points = ratio?.current != null && ratio.prior != null;
        const delta = points ? ratio.current! - ratio.prior! : card.delta;
        const up = delta != null && delta >= 0;
        const favorable = card.id === "loss_ratio" ? !up : up;
        return (
          <div key={card.id} className="relative">
          <button
            type="button"
            className={cn(
              "group h-full w-full p-4 text-left transition-colors",
              dashboard && ["written_premium", "earned_premium", "claim_count", "loss_ratio"].includes(card.id) && "pb-12",
              featured
                ? "card-primary hover:border-primary/35"
                : "card-secondary hover:border-border hover:bg-muted/20",
            )}
            onClick={() => onExplore?.(card.id)}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-xs text-muted-foreground">{card.label}</p>
              {featured ? (
                <span className="icon-well bg-primary/10 text-primary" aria-hidden="true">
                  <Icon className="size-3.5" />
                </span>
              ) : null}
            </div>
            {card.value != null && card.format !== "text" ? (
              <AnimatedNumber
                value={card.value}
                format={(n) =>
                  Math.abs(n - card.value!) < 1e-6 ? card.formatted : formatKpiAnim(n, card)
                }
                className={cn(
                  "kpi-metric mt-2 block font-semibold tracking-tight text-foreground",
                  presenterMode ? "text-3xl" : featured ? "text-3xl" : "text-2xl",
                )}
                as="p"
              />
            ) : (
              <p
                className={cn(
                  "kpi-metric mt-2 font-semibold tracking-tight tabular-nums text-foreground",
                  presenterMode ? "text-3xl" : featured ? "text-3xl" : "text-2xl",
                )}
              >
                {card.formatted}
              </p>
            )}
            {delta != null ? (
              <p
                className={cn(
                  "mt-1.5 inline-flex items-center gap-1 text-xs tabular-nums",
                  delta === 0 ? "text-muted-foreground" : favorable ? "text-success" : "text-danger",
                )}
              >
                {up ? (
                  <TrendingUp className="size-3.5" aria-hidden="true" />
                ) : (
                  <TrendingDown className="size-3.5" aria-hidden="true" />
                )}
                <span>
                  {(Math.abs(delta) * 100).toFixed(1)}{points ? " pp" : "%"} {compareLabel}
                </span>
              </p>
            ) : null}
          </button>
          {dashboard && ["written_premium", "earned_premium", "claim_count", "loss_ratio"].includes(card.id) ? <button type="button" disabled={dashboard.updating} onClick={() => dashboard.explain(card.id)} className="absolute bottom-4 left-4 text-xs font-medium text-primary hover:underline disabled:opacity-50" aria-label={`Explain ${card.label}`}>Explain this change</button> : null}
          </div>
        );
      })}
    </div>
  );
}
