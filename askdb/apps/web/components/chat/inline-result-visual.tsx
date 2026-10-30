"use client";

import * as React from "react";

import { ResultChart } from "@/components/chat/result-chart";
import type { ChatMessage, ResultProfile } from "@/components/chat/types";
import { formatChatCell } from "@/lib/format-chat-cell";
import {
  type InlinePresentation,
  inlinePresentation,
} from "@/lib/chat-new-ui";
import { cn } from "@/lib/utils";

/**
 * Shape-driven inline visuals for New Chat. Every figure comes from the executed message
 * payload (`resultProfile` / rows); nothing is invented.
 */
export function InlineResultVisual({ message }: { message: ChatMessage }) {
  const profile = message.meta?.resultProfile ?? null;
  if (!profile || profile.shape === "empty") return null;

  const presentation = inlinePresentation(profile);
  const chartBlock =
    presentation.showChart && message.rows?.length && message.columns && message.columns.length >= 2 ? (
      <InlineChart message={message} presentation={presentation} />
    ) : null;

  const detail = <DetailBlock profile={profile} presentation={presentation} message={message} />;

  if (presentation.sideBySide && chartBlock && detail) {
    return (
      <div
        className="grid gap-3 md:grid-cols-2"
        data-testid="inline-result-visual"
        data-layout={presentation.layout}
      >
        <div className="min-w-0">{detail}</div>
        <div className="min-w-0 rounded-xl border border-border/60 bg-muted/10 p-3">{chartBlock}</div>
      </div>
    );
  }

  const chartFirst =
    presentation.layout === "trend_chart" || presentation.layout === "comparison_chart";

  return (
    <div className="space-y-3" data-testid="inline-result-visual" data-layout={presentation.layout}>
      {chartFirst && chartBlock ? (
        <div className="rounded-xl border border-border/60 bg-muted/10 p-3">{chartBlock}</div>
      ) : null}
      {detail}
      {!chartFirst && chartBlock ? (
        <div className="rounded-xl border border-border/60 bg-muted/10 p-3">{chartBlock}</div>
      ) : null}
    </div>
  );
}

function DetailBlock({
  profile,
  presentation,
  message,
}: {
  profile: ResultProfile;
  presentation: InlinePresentation;
  message: ChatMessage;
}) {
  switch (presentation.layout) {
    case "kpi":
    case "kpi_group":
      return <KpiCards profile={profile} />;
    case "ranked_list":
      return <RankedList profile={profile} />;
    case "table_preview":
      return <TablePreview message={message} profile={profile} />;
    case "trend_chart":
    case "comparison_chart":
      // Chart is the primary visual; optional short list when not side-by-side and few rows.
      if (!presentation.sideBySide && profile.preview.length > 0 && profile.preview.length <= 5) {
        return <RankedList profile={profile} quiet />;
      }
      return null;
    case "summary_only":
    default:
      return null;
  }
}

function KpiCards({ profile }: { profile: ResultProfile }) {
  const values = profile.preview[0]?.values.filter((v) => v.text) ?? [];
  if (!values.length) return null;
  const names = new Map(profile.measures.map((m) => [m.column, m.label]));
  const label = profile.preview[0]?.label;

  return (
    <div
      className={cn(
        "grid gap-3",
        values.length === 1 ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2",
      )}
      data-testid="result-preview"
    >
      {values.map((value) => (
        <div
          key={value.column}
          className="rounded-xl border border-border/70 bg-background px-4 py-3 shadow-sm"
          data-testid="kpi-card"
        >
          <p className="text-xs font-medium text-muted-foreground">
            {names.get(value.column) ?? value.column}
            {label ? ` · ${label}` : ""}
          </p>
          <p className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-foreground">
            {value.text}
          </p>
        </div>
      ))}
    </div>
  );
}

function RankedList({ profile, quiet = false }: { profile: ResultProfile; quiet?: boolean }) {
  const rows = profile.preview.filter((row) => row.values.some((v) => v.text));
  if (!rows.length) return null;
  const names = new Map(profile.measures.map((m) => [m.column, m.label]));
  const ranked = profile.shape === "ranking";
  const plus = profile.mayBeTruncated ? "+" : "";

  return (
    <div className="space-y-1.5" data-testid="result-preview">
      {!quiet ? (
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          {profile.shape === "time_series"
            ? "Latest periods"
            : ranked
              ? "Top results"
              : "Breakdown"}
        </p>
      ) : null}
      <ol className="divide-y divide-border/50 text-sm">
        {rows.map((row, index) => (
          <li
            key={`${row.label ?? "row"}-${index}`}
            className="flex items-baseline justify-between gap-4 py-2"
          >
            <span className="flex min-w-0 items-baseline gap-2">
              {ranked ? (
                <span className="w-5 shrink-0 text-xs font-medium text-muted-foreground">
                  {index + 1}.
                </span>
              ) : null}
              <span className={cn("truncate", !row.label && "text-muted-foreground")}>
                {row.label ?? `Row ${index + 1}`}
              </span>
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
      </ol>
      {profile.previewTruncated ? (
        <p className="text-[11px] text-muted-foreground">
          Showing {rows.length} of {profile.rowCount.toLocaleString()}
          {plus} rows. Open the analysis for the full result.
        </p>
      ) : null}
    </div>
  );
}

function TablePreview({
  message,
  profile,
}: {
  message: ChatMessage;
  profile: ResultProfile;
}) {
  const columns = message.columns ?? [];
  const rows = (message.rows ?? []).slice(0, 5);
  if (!columns.length || !rows.length) {
    return <RankedList profile={profile} />;
  }
  const plus = profile.mayBeTruncated ? "+" : "";

  return (
    <div className="space-y-1.5" data-testid="result-preview">
      <div className="data-table-wrap overflow-x-auto rounded-xl border border-border/60">
        <table className="data-table text-xs">
          <thead className="bg-muted/40">
            <tr>
              {columns.map((column) => (
                <th key={column} className="px-3 py-2 font-medium text-muted-foreground">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-t border-border/50">
                {columns.map((column) => (
                  <td key={column} className="px-3 py-2 font-mono">
                    {formatChatCell(row[column], column)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {profile.rowCount > rows.length || profile.previewTruncated ? (
        <p className="text-[11px] text-muted-foreground">
          Showing {rows.length} of {profile.rowCount.toLocaleString()}
          {plus} rows. Open the analysis for the full result.
        </p>
      ) : null}
    </div>
  );
}

function InlineChart({
  message,
  presentation,
}: {
  message: ChatMessage;
  presentation: InlinePresentation;
}) {
  const columns = message.columns!;
  const rows = message.rows!;
  const profile = message.meta?.resultProfile;
  const xKey =
    message.chart?.x ??
    profile?.labelColumns[0] ??
    columns[0]!;
  const yKey =
    message.chart?.y ??
    profile?.measures[0]?.column ??
    columns.find((c) => c !== xKey) ??
    columns[1]!;

  return (
    <ResultChart
      xKey={xKey}
      yKey={yKey}
      rows={message.chart?.points ?? rows}
      columns={columns}
      series={message.chart?.series}
      initialType={presentation.chartKind}
      anomalies={message.chart?.anomalies ?? message.meta?.anomalies ?? []}
      hideTypeSelect
      compact
    />
  );
}
