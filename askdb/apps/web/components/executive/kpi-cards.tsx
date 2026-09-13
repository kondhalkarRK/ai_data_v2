"use client";

import * as React from "react";

import type { ExecKpiCard } from "@/components/executive/types";
import { cn } from "@/lib/utils";

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
      <p className="rounded-2xl border border-dashed border-border/70 px-4 py-8 text-center text-sm text-muted-foreground">
        No KPIs available for this domain and window. Connect data or widen filters.
      </p>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <button
          key={card.id}
          type="button"
          className="rounded-2xl border border-border/70 bg-background p-4 text-left shadow-sm transition-colors hover:border-border"
          onClick={() => onExplore?.(card.id)}
        >
          <p className="text-xs text-muted-foreground">{card.label}</p>
          <p
            className={cn(
              "mt-1 font-semibold tracking-tight tabular-nums",
              presenterMode ? "text-3xl" : "text-2xl",
            )}
          >
            {card.formatted}
          </p>
          {card.delta != null ? (
            <p
              className={cn(
                "mt-1 text-xs tabular-nums",
                card.delta >= 0 ? "text-emerald-600" : "text-danger",
              )}
            >
              {card.delta >= 0 ? "↑" : "↓"} {(Math.abs(card.delta) * 100).toFixed(1)}% {compareLabel}
            </p>
          ) : null}
        </button>
      ))}
    </div>
  );
}
