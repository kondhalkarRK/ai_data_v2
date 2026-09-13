"use client";

import {
  Lightbulb,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  TriangleAlert,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { AiInsight } from "@/components/executive/types";
import { EmptyState } from "@/components/ui/status-pill";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { useActiveIndustry } from "@/hooks/use-session";

const CATEGORY: Record<
  AiInsight["category"],
  { label: string; bar: string; well: string; Icon: typeof TriangleAlert }
> = {
  risk: {
    label: "Risk",
    bar: "bg-danger",
    well: "bg-danger/10 text-danger",
    Icon: TriangleAlert,
  },
  opportunity: {
    label: "Opportunity",
    bar: "bg-success",
    well: "bg-success/10 text-success",
    Icon: TrendingUp,
  },
  insight: {
    label: "Insight",
    bar: "bg-primary",
    well: "bg-primary/10 text-primary",
    Icon: Lightbulb,
  },
  recommendation: {
    label: "Recommendation",
    bar: "bg-orange",
    well: "bg-orange/10 text-orange",
    Icon: Sparkles,
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
      <EmptyState
        title="No grounded AI insights yet"
        detail="Insights appear only when they can be tied to live KPIs and definitions for this window."
      />
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
        const meta = CATEGORY[insight.category];
        const Icon = meta.Icon;
        return (
          <article key={insight.id} className="card-secondary relative flex flex-col overflow-hidden p-4">
            <span className={cn("absolute inset-y-0 left-0 w-0.5", meta.bar)} aria-hidden="true" />
            <div className="mb-2 flex items-start justify-between gap-2 pl-2">
              <div className="flex items-center gap-2">
                <span className={cn("icon-well", meta.well)} aria-hidden="true">
                  <Icon className="size-3.5" />
                </span>
                <span className="text-xs font-medium text-foreground">{meta.label}</span>
              </div>
              <div className="flex gap-1">
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  aria-label="Insight helpful"
                  className={cn(votes[insight.id] === "up" && "text-success")}
                  onClick={() => void vote(insight, "up")}
                >
                  <ThumbsUp className="size-3.5" />
                </Button>
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  aria-label="Insight not helpful"
                  className={cn(votes[insight.id] === "down" && "text-danger")}
                  onClick={() => void vote(insight, "down")}
                >
                  <ThumbsDown className="size-3.5" />
                </Button>
              </div>
            </div>
            <h3 className="pl-2 text-sm font-semibold tracking-tight">{insight.title}</h3>
            <p className="mt-1 flex-1 pl-2 text-sm leading-relaxed text-muted-foreground">
              {insight.body}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-1.5 pl-2">
              {insight.groundedOn.map((item) => (
                <span
                  key={item}
                  className="rounded-md border border-border/60 px-2 py-0.5 text-[10px] text-muted-foreground"
                >
                  {item}
                </span>
              ))}
              <Link
                href={`${exploreBasePath}?focus=${encodeURIComponent(insight.exploreFocus[0] ?? "")}`}
                className="ml-auto text-[11px] font-medium text-primary underline-offset-2 hover:underline"
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
