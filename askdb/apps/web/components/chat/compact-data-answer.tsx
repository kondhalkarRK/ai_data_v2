"use client";

import * as React from "react";
import { BarChart3, ChevronUp } from "lucide-react";

import type { ActionKey } from "@/components/chat/action-toolbar";
import { InlineResultVisual } from "@/components/chat/inline-result-visual";
import { ResponseCard } from "@/components/chat/response-card";
import { SuggestedQuestions } from "@/components/chat/suggested-questions";
import type { ChatMessage, ResponseTab } from "@/components/chat/types";
import { Button } from "@/components/ui/button";
import { analysisTab } from "@/lib/chat-new-ui";

/**
 * Conversational analytics answer for a successful data question: short narration, shape-driven
 * inline visuals (KPI / chart / ranked list / table) from the executed result, and View Analysis
 * that opens the existing ResponseCard over the same payload (no re-query).
 */
export function CompactDataAnswer({
  message,
  requestedTab,
  busy,
  onAsk,
  onAction,
}: {
  message: ChatMessage;
  /** Tab the user explicitly asked for ("show a chart"); opens the analysis immediately. */
  requestedTab: ResponseTab | null;
  busy?: boolean;
  onAsk: (question: string) => void;
  onAction: (key: ActionKey, message: ChatMessage) => void;
}) {
  const [open, setOpen] = React.useState(requestedTab !== null);
  const lead = message.meta?.insights?.narration?.summary || message.narrative || "";
  const highlights = message.meta?.insights?.narration?.highlights?.slice(0, 3) ?? [];
  const insight = message.meta?.insights?.narration?.insight;
  const followups = message.followups ?? [];

  return (
    <div className="space-y-3" data-testid="compact-data-answer">
      <div className="space-y-3 rounded-[var(--radius-card)] border border-border/70 bg-background px-4 py-4 shadow-sm">
        {lead ? <p className="text-sm leading-relaxed text-foreground">{lead}</p> : null}

        {highlights.length ? (
          <ul className="space-y-1 text-xs text-muted-foreground">
            {highlights.map((item) => (
              <li key={item} className="flex gap-2">
                <span className="mt-1.5 size-1 shrink-0 rounded-full bg-primary/70" aria-hidden />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ) : null}

        <InlineResultVisual message={message} />

        {insight ? (
          <p className="border-t border-border/50 pt-3 text-xs leading-relaxed text-muted-foreground">
            {insight}
          </p>
        ) : null}
      </div>

      <div className="flex justify-center">
        <Button
          type="button"
          variant={open ? "secondary" : "primary"}
          className="gap-2"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <ChevronUp className="size-4" /> : <BarChart3 className="size-4" />}
          {open ? "Hide Analysis" : "View Analysis"}
        </Button>
      </div>

      {open ? (
        <ResponseCard
          message={{ ...message, followups: undefined }}
          busy={busy}
          onAsk={onAsk}
          onAction={onAction}
          initialTab={analysisTab(message, requestedTab)}
        />
      ) : null}

      {followups.length ? (
        <SuggestedQuestions items={followups} disabled={busy} onSelect={onAsk} />
      ) : null}
    </div>
  );
}
