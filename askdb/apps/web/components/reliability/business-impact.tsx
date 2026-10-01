"use client";

import { BriefcaseBusiness } from "lucide-react";

import { formatCount, formatInr } from "@/components/executive/cockpit/format";
import type { DataReliability, TrustFilters } from "@/components/reliability/types";
import { Card, PanelTitle, SEVERITY_DOT } from "@/components/reliability/ui";

export function BusinessImpactPanel({
  data,
  filters,
  onOpenRule,
  className,
}: {
  data: DataReliability;
  filters: TrustFilters;
  onOpenRule: (id: string) => void;
  className?: string;
}) {
  const { impact } = data;
  const inScope = new Set(
    data.rules
      .filter(
        (r) =>
          (!filters.dimension || r.dimension === filters.dimension) &&
          (!filters.dataset || r.dataset === filters.dataset) &&
          (!filters.severity || r.severity === filters.severity),
      )
      .map((r) => r.id),
  );
  const items = impact.items.filter((i) => i.ruleIds.some((id) => inScope.has(id)));

  return (
    <Card className={className}>
      <PanelTitle title="Business impact" subtitle="What the open issues mean for decisions, in plain language" />
      <div className="rounded-xl bg-gradient-to-r from-[#eef4ff] to-[#eaf7f3] px-3.5 py-3 dark:from-muted dark:to-muted">
        <p className="flex items-start gap-2 text-xs font-medium leading-relaxed text-slate-800 dark:text-foreground">
          <BriefcaseBusiness className="mt-0.5 size-4 shrink-0 text-[#2f6fed]" />
          {impact.headline}
        </p>
        {impact.recordsAffected || impact.valueAtRisk ? (
          <div className="mt-2 flex gap-4 pl-6 text-[11px] text-slate-500">
            <span>
              <span className="font-semibold tabular-nums text-slate-700">{formatCount(impact.recordsAffected)}</span> records affected
            </span>
            {impact.valueAtRisk ? (
              <span>
                <span className="font-semibold tabular-nums text-slate-700">{formatInr(impact.valueAtRisk)}</span> value in question
              </span>
            ) : null}
          </div>
        ) : null}
      </div>
      <ul className="mt-3 space-y-2.5">
        {items.map((item) => (
          <li key={item.asset} className="rounded-xl border border-slate-100 px-3 py-2.5 dark:border-border">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-slate-800 dark:text-foreground">
              <span className="size-1.5 rounded-full" style={{ backgroundColor: SEVERITY_DOT[item.severity] }} />
              {item.asset}
            </p>
            <ul className="mt-1 space-y-1">
              {item.statements.map((s, i) => (
                <li key={i}>
                  <button
                    type="button"
                    onClick={() => item.ruleIds[i] && onOpenRule(item.ruleIds[i]!)}
                    className="text-left text-[11px] leading-relaxed text-slate-600 hover:text-[#2f6fed] dark:text-muted-foreground"
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          </li>
        ))}
        {!items.length ? (
          <li className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-center text-2xs text-slate-500">
            {impact.items.length
              ? "No business impact from the rules in the current filter."
              : "Dashboards, forecasts and reports built on this data can be used with confidence."}
          </li>
        ) : null}
      </ul>
    </Card>
  );
}
