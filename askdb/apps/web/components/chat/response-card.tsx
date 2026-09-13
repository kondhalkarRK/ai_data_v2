"use client";

import * as React from "react";

import { ActionToolbar, type ActionKey } from "@/components/chat/action-toolbar";
import { ExecutionTimeline } from "@/components/chat/execution-timeline";
import { InsightSummary } from "@/components/chat/insight-summary";
import {
  failureKindFromCategory,
  ResponseErrorState,
} from "@/components/chat/response-error-state";
import { ResponseHeader } from "@/components/chat/response-header";
import { ResponseTabs } from "@/components/chat/response-tabs";
import { ResultChart } from "@/components/chat/result-chart";
import { SQLViewer } from "@/components/chat/sql-viewer";
import { SuggestedQuestions } from "@/components/chat/suggested-questions";
import { TrustIndicators } from "@/components/chat/trust-indicators";
import type {
  ChatMessage,
  InsightDepth,
  ResponseTab,
} from "@/components/chat/types";
import { cn } from "@/lib/utils";

export function ResponseCard({
  message,
  busy,
  onAsk,
  onRetry,
  onAction,
  className,
}: {
  message: ChatMessage;
  busy?: boolean;
  onAsk: (question: string) => void;
  onRetry?: () => void;
  onAction: (key: ActionKey, message: ChatMessage) => void;
  className?: string;
}) {
  const [tab, setTab] = React.useState<ResponseTab>("chart");
  const [depth, setDepth] = React.useState<InsightDepth>("executive");
  const meta = message.meta;

  if (message.cancelled) {
    return (
      <ResponseErrorState
        kind="generic"
        title="Request cancelled"
        detail="The previous question was cancelled before a result was ready."
        onRetry={onRetry}
        className={className}
      />
    );
  }

  if (message.failure || (message.error && !meta)) {
    const failure = message.failure;
    const kind = failureKindFromCategory(failure?.category);
    return (
      <ResponseErrorState
        kind={kind}
        title={failure?.title || "Couldn't run this query"}
        detail={
          failure?.reason
            ? `Reason: ${failure.reason}`
            : failure?.message || message.error || "Something went wrong."
        }
        sql={failure?.sql || message.sql}
        onRetry={failure?.retryable !== false ? onRetry : undefined}
        className={className}
      />
    );
  }

  if (message.clarification && (!message.rows || message.rows.length === 0) && !message.sql) {
    return (
      <div className={cn("space-y-3 rounded-2xl border border-border/70 bg-background p-4 shadow-sm", className)}>
        <ResponseErrorState
          kind="ambiguous"
          title="Your question is ambiguous"
          detail={message.clarification}
          suggestions={message.options}
          onAsk={onAsk}
        />
        {message.followups?.length ? (
          <SuggestedQuestions items={message.followups} disabled={busy} onSelect={onAsk} />
        ) : null}
      </div>
    );
  }

  if (!meta && !message.narrative && !message.sql && !message.rows?.length) {
    return (
      <div
        className={cn(
          "rounded-2xl border border-border/70 bg-background p-4 shadow-sm",
          className,
        )}
      >
        <ExecutionTimeline progress={message.progress ?? undefined} />
        {!message.progress ? (
          <p className="mt-2 text-sm text-muted-foreground">Understanding your question…</p>
        ) : null}
      </div>
    );
  }

  const zeroRows = Boolean(meta && meta.rowCount === 0 && message.sql && !meta.executionError);
  const execFailed = Boolean(meta?.executionError || meta?.validationStatus === "failed");
  const dqFailed = Boolean(meta?.dqFailed);

  return (
    <article
      className={cn(
        "overflow-hidden rounded-[var(--radius-card)] border border-border/70 bg-background",
        className,
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-border/60 px-4 py-3">
        <div className="min-w-0 flex-1">
          {meta ? <ResponseHeader meta={meta} latencyMs={message.latencyMs} /> : null}
          {!meta && message.progress ? (
            <ExecutionTimeline progress={message.progress} />
          ) : null}
        </div>
        <ActionToolbar onAction={(key) => onAction(key, message)} />
      </div>

      <div className="space-y-4 px-4 py-4">
        {!meta && (message.rows?.length || message.sql) ? (
          <div className="min-h-[120px]">
            {message.columns && message.rows ? (
              <div className="overflow-auto rounded-xl border border-border/60">
                <table className="min-w-full text-left text-xs">
                  <thead className="bg-muted/40">
                    <tr>
                      {message.columns.map((column) => (
                        <th key={column} className="px-3 py-2 font-medium text-muted-foreground">
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {message.rows.slice(0, 50).map((row, index) => (
                      <tr key={index} className="border-t border-border/50">
                        {message.columns?.map((column) => (
                          <td key={column} className="px-3 py-2 font-mono">
                            {String(row[column] ?? "—")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {message.chart && message.columns && message.columns.length >= 2 ? (
              <div className="mt-3">
                <ResultChart
                  xKey={message.chart.x}
                  yKey={message.chart.y}
                  rows={message.chart.points}
                  anomalies={message.chart.anomalies ?? []}
                />
              </div>
            ) : null}
          </div>
        ) : null}

        {meta ? (
          <InsightSummary
            executive={meta.insights?.executive || message.narrative || ""}
            analyst={meta.insights?.analyst || message.narrative || ""}
            depth={depth}
            onDepthChange={setDepth}
          />
        ) : message.narrative ? (
          <p className="text-sm leading-relaxed">{message.narrative}</p>
        ) : null}

        {meta ? (
          <TrustIndicators
            groundedOn={meta.groundedOn ?? []}
            ambiguityFlag={Boolean(meta.ambiguityFlag)}
            alternates={meta.alternateInterpretations}
            onClarify={onAsk}
          />
        ) : null}

        {dqFailed ? (
          <ResponseErrorState
            kind="dq"
            title="Data quality note"
            detail="Underlying data failed a freshness/completeness check. Treat the numbers below with caution."
          />
        ) : null}

        {execFailed ? (
          <ResponseErrorState
            kind="execution"
            title="Database Execution Failed"
            detail={
              meta?.executionError
                ? `Reason: ${meta.executionError}`
                : message.error || "SQL execution failed after validation."
            }
            sql={message.sql}
            onRetry={onRetry}
          />
        ) : null}

        {zeroRows ? (
          <ResponseErrorState
            kind="zero_rows"
            title="No rows matched"
            detail="The governed query ran successfully but returned zero rows. Try loosening a filter or widening the date range."
            sql={message.sql}
            suggestions={message.followups?.slice(0, 2)}
            onAsk={onAsk}
          />
        ) : null}

        {!execFailed && meta && (message.sql || message.rows?.length) ? (
          <>
            <ResponseTabs value={tab} onChange={setTab} />
            <div className="min-h-[180px]">
              {tab === "chart" ? (
                message.columns && message.rows && message.columns.length >= 2 ? (
                  <ResultChart
                    xKey={message.chart?.x ?? message.columns[0]!}
                    yKey={message.chart?.y ?? message.columns[1]!}
                    rows={message.chart?.points ?? message.rows}
                    anomalies={message.chart?.anomalies ?? meta?.anomalies ?? []}
                  />
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">
                    Chart needs at least two columns in the result.
                  </p>
                )
              ) : null}
              {tab === "table" ? (
                message.columns && message.rows ? (
                  <div className="overflow-auto rounded-xl border border-border/60">
                    <table className="min-w-full text-left text-xs">
                      <thead className="bg-muted/40">
                        <tr>
                          {message.columns.map((column) => (
                            <th key={column} className="px-3 py-2 font-medium text-muted-foreground">
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {message.rows.slice(0, 50).map((row, index) => (
                          <tr key={index} className="border-t border-border/50">
                            {message.columns?.map((column) => (
                              <td key={column} className="px-3 py-2 font-mono">
                                {String(row[column] ?? "—")}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">No table rows.</p>
                )
              ) : null}
              {tab === "sql" && message.sql && meta ? (
                <SQLViewer
                  sql={message.sql}
                  queryMeta={meta.queryMeta}
                  executionTimeMs={meta.executionTimeMs}
                  rowCount={meta.rowCount}
                  sourceDatabase={meta.sourceDatabase}
                  diff={message.sqlDiff}
                />
              ) : null}
              {tab === "sql" && message.sql && !meta ? (
                <pre className="overflow-auto rounded-xl bg-muted/40 p-3 font-mono text-[11px]">
                  {message.sql}
                </pre>
              ) : null}
            </div>
          </>
        ) : null}

        {message.citations?.length ? (
          <ul className="space-y-1 text-[11px] text-muted-foreground">
            {message.citations.map((citation, index) => (
              <li key={`${citation.locator}-${index}`}>
                [{citation.locator}] {citation.title}
                {citation.untrusted ? " (untrusted web)" : ""}: {citation.snippet}
              </li>
            ))}
          </ul>
        ) : null}

        {message.followups?.length ? (
          <SuggestedQuestions items={message.followups} disabled={busy} onSelect={onAsk} />
        ) : null}
      </div>
    </article>
  );
}
