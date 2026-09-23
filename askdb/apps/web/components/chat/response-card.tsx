"use client";

import * as React from "react";

import { ActionToolbar, type ActionKey } from "@/components/chat/action-toolbar";
import { ExecutionTimeline } from "@/components/chat/execution-timeline";
import {
  failureKindFromCategory,
  ResponseErrorState,
} from "@/components/chat/response-error-state";
import { InsightSummary } from "@/components/chat/insight-summary";
import { ResponseTabs } from "@/components/chat/response-tabs";
import { ResultChart } from "@/components/chat/result-chart";
import { SQLViewer } from "@/components/chat/sql-viewer";
import { SuggestedQuestions } from "@/components/chat/suggested-questions";
import { TrustIndicators } from "@/components/chat/trust-indicators";
import type { ChatMessage, InsightDepth, QueryPlanTrace, ResponseTab } from "@/components/chat/types";
import { cn } from "@/lib/utils";

const ROUTE_LABEL: Record<string, string> = {
  sql: "Answered from data",
  knowledge: "Documents",
  hybrid: "Data + reports",
};

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
  const [tab, setTab] = React.useState<ResponseTab>("table");
  const [insightDepth, setInsightDepth] = React.useState<InsightDepth>("executive");
  const meta = message.meta;
  const route = message.route || meta?.route;

  React.useEffect(() => {
    if (route === "knowledge") {
      setTab("narration");
    }
  }, [route]);

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
      <div
        className={cn(
          "space-y-3 rounded-2xl border border-border/70 bg-background p-4 shadow-sm",
          className,
        )}
      >
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
          <p className="mt-2 text-sm text-muted-foreground">
            Working on your question… this can take up to a minute on the hosted API.
          </p>
        ) : null}
      </div>
    );
  }

  const zeroRows = Boolean(meta && meta.rowCount === 0 && message.sql && !meta.executionError);
  const execFailed = Boolean(meta?.executionError || meta?.validationStatus === "failed");
  const dqFailed = Boolean(meta?.dqFailed);
  const totalMs = message.latencyMs ?? meta?.executionTimeMs ?? 0;
  const answered = `${(totalMs / 1000).toFixed(1)}s`;

  return (
    <article
      className={cn(
        "overflow-hidden rounded-[var(--radius-card)] border border-border/70 bg-background",
        className,
      )}
    >
      {!meta && message.progress ? (
        <div className="border-b border-border/60 px-4 py-3">
          <ExecutionTimeline progress={message.progress} />
        </div>
      ) : null}

      <div className="space-y-3 px-4 py-4">
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
            title="SQL Execution Error"
            detail={
              meta?.executionError
                ? `Reason: ${meta.executionError}`
                : message.error || "The query did not finish. Try a more specific business question."
            }
            sql={message.sql}
            onRetry={onRetry}
          />
        ) : null}

        {zeroRows ? (
          <ResponseErrorState
            kind="zero_rows"
            title="No matching records"
            detail="The governed query ran successfully but returned zero rows. Try loosening a filter or widening the date range."
            sql={message.sql}
            suggestions={message.followups?.slice(0, 2)}
            onAsk={onAsk}
          />
        ) : null}

        {route && ROUTE_LABEL[route] ? (
          <p className="text-[11px] font-medium text-muted-foreground">{ROUTE_LABEL[route]}</p>
        ) : null}

        {meta ? (
          <TrustIndicators
            groundedOn={meta.groundedOn ?? []}
            ambiguityFlag={Boolean(meta.ambiguityFlag)}
            alternates={meta.alternateInterpretations}
            onClarify={onAsk}
          />
        ) : null}

        {meta?.queryPlan ? <QueryPlanNote plan={meta.queryPlan} /> : null}

        {!execFailed && (message.sql || message.rows?.length || meta) ? (
          <>
            <ResponseTabs value={tab} onChange={setTab} />
            <div className="min-h-[160px]">
              {tab === "table" ? (
                message.columns && message.rows ? (
                  <div className="overflow-auto rounded-xl border border-border/60">
                    <table className="min-w-full text-left text-xs">
                      <thead className="bg-muted/40">
                        <tr>
                          {message.columns.map((column) => (
                            <th
                              key={column}
                              className="px-3 py-2 font-medium text-muted-foreground"
                            >
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {message.rows.slice(0, 100).map((row, index) => (
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

              {tab === "chart" ? (
                message.columns && message.rows && message.columns.length >= 2 ? (
                  <ResultChart
                    xKey={message.chart?.x ?? message.columns[0]!}
                    yKey={message.chart?.y ?? message.columns[1]!}
                    rows={message.chart?.points ?? message.rows}
                    columns={message.columns}
                    anomalies={message.chart?.anomalies ?? meta?.anomalies ?? []}
                  />
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">
                    Chart needs at least two columns in the result.
                  </p>
                )
              ) : null}

              {tab === "narration" ? (
                meta?.insights?.executive || message.narrative ? (
                  <div className="space-y-3">
                    <InsightSummary
                      executive={
                        meta?.insights?.executive ||
                        message.narrative ||
                        "Business summary will appear when the answer is ready."
                      }
                      analyst={
                        meta?.insights?.analyst ||
                        message.narrative ||
                        "Detailed analyst notes will appear when the answer is ready."
                      }
                      depth={insightDepth}
                      onDepthChange={setInsightDepth}
                    />
                    <p className="text-[11px] text-muted-foreground">
                      AI Business Analyst — plain-language findings
                      {route === "knowledge"
                        ? " from documents."
                        : route === "hybrid"
                          ? " from governed data plus report evidence."
                          : " from the governed result, not SQL commentary."}
                    </p>
                    {route && route !== "sql" && message.citations?.length ? (
                      <ul className="space-y-1 text-[11px] text-muted-foreground">
                        {message.citations.map((citation, index) => (
                          <li key={`${citation.locator}-${index}`}>
                            [{citation.locator}] {citation.title}
                            {citation.confidence != null
                              ? ` · ${Math.round(citation.confidence * 100)}%`
                              : ""}
                            {citation.untrusted ? " (untrusted web)" : ""}: {citation.snippet}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">
                    Narration is generating… switch back in a moment, or keep the Table view open.
                  </p>
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

        {/* Compact meta + actions row below the result */}
        {meta ? (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-border/60 pt-3 text-[11px] text-muted-foreground">
            <span className="font-medium text-foreground">Answered in {answered}</span>
            <span>Rows: {meta.rowCount.toLocaleString()}</span>
            {meta.sourceDatabase ? <span>{meta.sourceDatabase}</span> : null}
            {meta.validationStatus === "auto_repaired" ? (
              <span className="text-amber-800 dark:text-amber-200">Auto-repaired SQL</span>
            ) : null}
            <details className="group">
              <summary className="cursor-pointer list-none font-medium text-foreground underline-offset-2 hover:underline [&::-webkit-details-marker]:hidden">
                Timing
              </summary>
              <div className="mt-2 w-full min-w-[240px]">
                <ExecutionTimeline
                  timings={meta.timings}
                  totalMs={totalMs || sumTimings(meta.timings)}
                />
              </div>
            </details>
            <div className="ml-auto">
              <ActionToolbar onAction={(key) => onAction(key, message)} />
            </div>
          </div>
        ) : (
          <div className="flex justify-end border-t border-border/60 pt-3">
            <ActionToolbar onAction={(key) => onAction(key, message)} />
          </div>
        )}

        {message.citations?.length && route === "sql" ? (
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

function QueryPlanNote({ plan }: { plan: QueryPlanTrace }) {
  if (!plan.formula && !plan.joins?.length && !plan.filters?.length) return null;
  return (
    <div className="rounded-xl border border-border/60 bg-muted/15 px-3 py-2 text-xs text-muted-foreground">
      {plan.formula ? (
        <p>
          <span className="font-medium text-foreground">
            {(plan.metric || "Metric").replaceAll("_", " ")}
          </span>{" "}
          interpreted as {plan.formula}
        </p>
      ) : null}
      {plan.joins?.length ? <p>Joins: {plan.joins.join(" · ")}</p> : null}
      {plan.filters?.length ? <p>Filters: {plan.filters.join(", ")}</p> : null}
    </div>
  );
}

function sumTimings(timings: NonNullable<ChatMessage["meta"]>["timings"]): number {
  return (
    (timings.llmGenerationMs ?? 0) +
    (timings.semanticLookupMs ?? 0) +
    (timings.sqlValidationMs ?? 0) +
    (timings.sqlAutoRepairMs ?? 0) +
    (timings.executionMs ?? 0) +
    (timings.renderMs ?? 0)
  );
}
