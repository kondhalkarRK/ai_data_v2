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

import type { ExecKpiCard } from "@/components/executive/types";
import { EmptyState } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

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
        const up = card.delta != null && card.delta >= 0;
        return (
          <button
            key={card.id}
            type="button"
            className={cn(
              "group p-4 text-left transition-colors",
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
            <p
              className={cn(
                "mt-2 font-semibold tracking-tight tabular-nums text-foreground",
                presenterMode ? "text-3xl" : featured ? "text-3xl" : "text-2xl",
              )}
            >
              {card.formatted}
            </p>
            {card.delta != null ? (
              <p
                className={cn(
                  "mt-1.5 inline-flex items-center gap-1 text-xs tabular-nums",
                  up ? "text-success" : "text-danger",
                )}
              >
                {up ? (
                  <TrendingUp className="size-3.5" aria-hidden="true" />
                ) : (
                  <TrendingDown className="size-3.5" aria-hidden="true" />
                )}
                <span>
                  {(Math.abs(card.delta) * 100).toFixed(1)}% {compareLabel}
                </span>
              </p>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
