"use client";

import { ThumbsDown, ThumbsUp } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { AiInsight } from "@/components/executive/types";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { useActiveIndustry } from "@/hooks/use-session";

const CATEGORY_STYLES: Record<
  AiInsight["category"],
  { label: string; className: string }
> = {
  risk: { label: "Risk", className: "border-rose-500/25 bg-rose-500/8 text-rose-800 dark:text-rose-200" },
  opportunity: {
    label: "Opportunity",
    className: "border-emerald-500/25 bg-emerald-500/8 text-emerald-800 dark:text-emerald-200",
  },
  insight: {
    label: "Insight",
    className: "border-sky-500/25 bg-sky-500/8 text-sky-800 dark:text-sky-200",
  },
  recommendation: {
    label: "Recommendation",
    className: "border-amber-500/25 bg-amber-500/8 text-amber-800 dark:text-amber-200",
  },
};

export function AiIntelligenceSection({
  insights,
  exploreBasePath,
}: {
  insights: AiInsight[];
  exploreBasePath: string;
}) {
  const industry = useActiveIndustry();
  const [votes, setVotes] = React.useState<Record<string, "up" | "down">>({});

  if (!insights.length) {
    return (
      <div className="rounded-2xl border border-dashed border-border/70 bg-muted/15 px-4 py-6 text-sm text-muted-foreground">
        No grounded AI insights for the current metrics and window. Insights appear only when they
        can be tied to live KPIs and definitions.
      </div>
    );
  }

  async function vote(insight: AiInsight, choice: "up" | "down") {
    setVotes((prev) => ({ ...prev, [insight.id]: choice }));
    try {
      await apiClient.post(
        "/api/v1/executive/insights/feedback",
        {
          insightId: insight.id,
          vote: choice,
          groundedOn: insight.groundedOn,
          category: insight.category,
          bodyPreview: insight.body.slice(0, 240),
        },
        { industry },
      );
    } catch {
      // Feedback is best-effort; UI still reflects local vote.
    }
  }

  return (
    <div className="grid gap-3 md:grid-cols-2">
      {insights.map((insight) => {
        const style = CATEGORY_STYLES[insight.category];
        return (
          <article
            key={insight.id}
            className="flex flex-col rounded-2xl border border-border/70 bg-background p-4 shadow-sm"
          >
            <div className="mb-2 flex items-start justify-between gap-2">
              <span className={cn("rounded-full border px-2.5 py-0.5 text-[11px] font-medium", style.className)}>
                {style.label}
              </span>
              <div className="flex gap-1">
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  aria-label="Insight helpful"
                  className={cn(votes[insight.id] === "up" && "text-emerald-600")}
                  onClick={() => void vote(insight, "up")}
                >
                  <ThumbsUp className="size-3.5" />
                </Button>
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  aria-label="Insight not helpful"
                  className={cn(votes[insight.id] === "down" && "text-rose-600")}
                  onClick={() => void vote(insight, "down")}
                >
                  <ThumbsDown className="size-3.5" />
                </Button>
              </div>
            </div>
            <h3 className="text-sm font-semibold tracking-tight">{insight.title}</h3>
            <p className="mt-1 flex-1 text-sm leading-relaxed text-muted-foreground">{insight.body}</p>
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              {insight.groundedOn.map((item) => (
                <span
                  key={item}
                  className="rounded-full border border-border/60 px-2 py-0.5 text-[10px] text-muted-foreground"
                >
                  {item}
                </span>
              ))}
              <Link
                href={`${exploreBasePath}?focus=${encodeURIComponent(insight.exploreFocus[0] ?? "")}`}
                className="ml-auto text-[11px] font-medium text-foreground underline-offset-2 hover:underline"
              >
                Explore Data Context
              </Link>
            </div>
          </article>
        );
      })}
    </div>
  );
}
