"use client";

import { ArrowDownRight, ArrowUpRight, Lightbulb, MousePointerClick } from "lucide-react";

import { COCKPIT, tint, toneColour } from "@/components/executive/cockpit/palette";
import type { CockpitInsight, SelectHandler } from "@/components/executive/cockpit/types";
import { cn } from "@/lib/utils";

export function InsightRail({
  insights,
  onSelect,
  className,
}: {
  insights: CockpitInsight[];
  onSelect: SelectHandler;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "flex min-w-0 flex-col rounded-2xl border border-slate-200/70 bg-gradient-to-b from-[#f4f8ff] to-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-12px_rgba(15,23,42,0.08)] dark:border-border dark:from-surface-raised dark:to-surface-raised",
        className,
      )}
    >
      <header className="mb-2 flex items-center gap-2">
        <span className="grid size-6 place-items-center rounded-lg bg-[#e3ecfd] text-[#2f6fed]">
          <Lightbulb className="size-3.5" />
        </span>
        <div>
          <h3 className="text-sm font-semibold tracking-tight text-slate-800 dark:text-foreground">Key insights</h3>
          <p className="text-2xs text-slate-500">Generated from the current selection</p>
        </div>
      </header>
      {insights.length === 0 ? (
        <p className="py-6 text-center text-xs text-slate-400">No notable movements in this selection.</p>
      ) : (
        <ul className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-0.5">
          {insights.map((insight) => (
            <li key={insight.id}>
              <InsightCard insight={insight} onSelect={onSelect} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function InsightCard({ insight, onSelect }: { insight: CockpitInsight; onSelect: SelectHandler }) {
  const colour = toneColour(insight.tone);
  const actionable = insight.filterDimension != null && insight.filterValue != null;
  const Icon = insight.tone === "negative" ? ArrowDownRight : ArrowUpRight;
  const body = (
    <>
      <span
        className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-md"
        style={{ backgroundColor: tint(colour, 0.85), color: colour }}
      >
        {insight.tone === "neutral" ? <span className="size-1.5 rounded-full" style={{ backgroundColor: colour }} /> : <Icon className="size-3" />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-start justify-between gap-2">
          <span className="text-xs font-semibold leading-snug text-slate-800 dark:text-foreground">{insight.headline}</span>
          {insight.metric ? (
            <span className="shrink-0 text-xs font-bold tabular-nums" style={{ color: insight.tone === "neutral" ? COCKPIT.blue : colour }}>
              {insight.metric}
            </span>
          ) : null}
        </span>
        <span className="mt-0.5 block text-2xs leading-relaxed text-slate-500 dark:text-muted-foreground">{insight.detail}</span>
        {actionable ? (
          <span className="mt-1 inline-flex items-center gap-1 text-[10px] font-medium text-[#2f6fed] opacity-0 transition group-hover:opacity-100">
            <MousePointerClick className="size-3" /> Focus dashboard on {insight.filterValue}
          </span>
        ) : null}
      </span>
    </>
  );
  const classes =
    "group flex w-full items-start gap-2.5 rounded-xl border border-slate-200/60 bg-white/80 p-2.5 text-left dark:border-border dark:bg-surface-raised";
  if (!actionable) return <div className={classes}>{body}</div>;
  return (
    <button
      type="button"
      className={cn(classes, "transition hover:border-[#8fb3f5] hover:shadow-sm")}
      onClick={() => onSelect(insight.filterDimension!, insight.filterValue!)}
    >
      {body}
    </button>
  );
}
