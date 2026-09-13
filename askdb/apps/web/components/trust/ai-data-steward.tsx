"use client";

import { Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";
import * as React from "react";

import type { AiSteward } from "@/components/trust/types";
import { Button } from "@/components/ui/button";
import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";

export function AiDataSteward({ steward }: { steward: AiSteward }) {
  const industry = useActiveIndustry();
  const [vote, setVote] = React.useState<"up" | "down" | null>(null);

  async function send(choice: "up" | "down") {
    setVote(choice);
    try {
      await apiClient.post(
        "/api/v1/trust/steward/feedback",
        {
          vote: choice,
          groundedOn: steward.groundedOn,
          bodyPreview: steward.summary.slice(0, 240),
        },
        { industry },
      );
    } catch {
      // best-effort
    }
  }

  return (
    <div className="card-secondary relative overflow-hidden p-4">
      <span className="absolute inset-y-0 left-0 w-0.5 bg-accent" aria-hidden="true" />
      <div className="mb-2 flex items-start justify-between gap-2 pl-2">
        <div className="flex items-center gap-2">
          <span className="icon-well bg-accent/12 text-accent" aria-hidden="true">
            <Sparkles className="size-3.5" />
          </span>
          <h3 className="text-sm font-semibold">AI Data Steward</h3>
        </div>
        <div className="flex gap-1">
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            aria-label="Helpful"
            className={cn(vote === "up" && "text-success")}
            onClick={() => void send("up")}
          >
            <ThumbsUp className="size-3.5" />
          </Button>
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            aria-label="Not helpful"
            className={cn(vote === "down" && "text-danger")}
            onClick={() => void send("down")}
          >
            <ThumbsDown className="size-3.5" />
          </Button>
        </div>
      </div>
      <p className="pl-2 text-sm leading-relaxed text-muted-foreground">{steward.summary}</p>
      {steward.risks.length ? (
        <div className="mt-3 pl-2">
          <p className="text-xs font-medium text-foreground">Risks</p>
          <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
            {steward.risks.map((item) => (
              <li key={item}>• {item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="mt-3 pl-2">
        <p className="text-xs font-medium text-foreground">Recommendations</p>
        <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
          {steward.recommendations.map((item) => (
            <li key={item}>• {item}</li>
          ))}
        </ul>
      </div>
      <p className="mt-3 pl-2 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Impact: </span>
        {steward.impactAssessment}
      </p>
      <div className="mt-3 flex flex-wrap gap-1.5 pl-2">
        {steward.groundedOn.map((g) => (
          <span
            key={g}
            className="rounded-md border border-border/60 px-2 py-0.5 text-[10px] text-muted-foreground"
          >
            {g}
          </span>
        ))}
      </div>
    </div>
  );
}
