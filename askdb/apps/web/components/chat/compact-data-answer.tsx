"use client";

import * as React from "react";
import { BarChart3, ChevronUp } from "lucide-react";

import type { ActionKey } from "@/components/chat/action-toolbar";
import { ResponseCard } from "@/components/chat/response-card";
import { SuggestedQuestions } from "@/components/chat/suggested-questions";
import type { ChatMessage, ResponseTab, ResultProfile } from "@/components/chat/types";
import { Button } from "@/components/ui/button";
import { analysisTab } from "@/lib/chat-new-ui";
import { cn } from "@/lib/utils";

const PREVIEW_HEADING: Partial<Record<ResultProfile["shape"], string>> = {
  time_series: "Latest periods",
  ranking: "Top results",
};

/**
 * Compact answer for a successful data question: a sentence, the key values from the executed
 * result, and a centered View Analysis button. The analysis is the existing ResponseCard (table,
 * chart, narration, SQL) over the same message, so it shows the same authorized rows.
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
  const profile = message.meta?.resultProfile ?? null;
  const lead = message.meta?.insights?.narration?.summary || message.narrative || "";
  const followups = message.followups ?? [];

  return (
    <div className="space-y-3" data-testid="compact-data-answer">
      <div className="space-y-3 rounded-[var(--radius-card)] border border-border/70 bg-background px-4 py-4">
        {lead ? <p className="text-sm leading-relaxed text-foreground">{lead}</p> : null}
        {profile ? <ResultPreview profile={profile} /> : null}
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

function ResultPreview({ profile }: { profile: ResultProfile }) {
  const names = new Map(profile.measures.map((m) => [m.column, m.label]));

  if (profile.shape === "single_value") {
    const values = profile.preview[0]?.values.filter((v) => v.text) ?? [];
    if (!values.length) return null;
    return (
      <dl className="flex flex-wrap gap-x-8 gap-y-2" data-testid="result-preview">
        {values.map((value) => (
          <div key={value.column}>
            <dt className="text-xs text-muted-foreground">{names.get(value.column) ?? value.column}</dt>
            <dd className="text-2xl font-semibold tracking-tight tabular-nums">{value.text}</dd>
          </div>
        ))}
      </dl>
    );
  }

  const rows = profile.preview.filter((row) => row.values.some((v) => v.text));
  if (!rows.length) return null;
  const heading = PREVIEW_HEADING[profile.shape];
  const plus = profile.mayBeTruncated ? "+" : "";

  return (
    <div className="space-y-1.5" data-testid="result-preview">
      {heading ? (
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          {heading}
        </p>
      ) : null}
      <ul className="divide-y divide-border/50 text-sm">
        {rows.map((row, index) => (
          <li key={`${row.label ?? "row"}-${index}`} className="flex items-baseline justify-between gap-4 py-1.5">
            <span className={cn("truncate", !row.label && "text-muted-foreground")}>
              {row.label ?? `Row ${index + 1}`}
            </span>
            <span className="flex shrink-0 flex-wrap justify-end gap-x-4 tabular-nums">
              {row.values
                .filter((v) => v.text)
                .map((value, position) => (
                  <span
                    key={value.column}
                    className={position === 0 ? "font-semibold" : "text-muted-foreground"}
                    title={names.get(value.column) ?? value.column}
                  >
                    {position > 0 ? `${names.get(value.column) ?? value.column} ` : ""}
                    {value.text}
                  </span>
                ))}
            </span>
          </li>
        ))}
      </ul>
      {profile.previewTruncated ? (
        <p className="text-[11px] text-muted-foreground">
          Showing {rows.length} of {profile.rowCount.toLocaleString()}
          {plus} rows. Open the analysis for the full result.
        </p>
      ) : null}
    </div>
  );
}
