"use client";

import { Check, ChevronDown, Copy } from "lucide-react";
import * as React from "react";

import type { QueryMeta, SqlDiffLine } from "@/components/chat/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function highlightSql(sql: string): React.ReactNode[] {
  const pattern =
    /\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP|BY|ORDER|LIMIT|AS|AND|OR|SUM|AVG|COUNT|MIN|MAX|COALESCE|NULLIF|DATE|EXTRACT|FILTER|DISTINCT)\b|('[^']*')|(\d+(?:\.\d+)?)|(--[^\n]*)/gi;
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = pattern.exec(sql))) {
    if (match.index > last) {
      nodes.push(<span key={key++}>{sql.slice(last, match.index)}</span>);
    }
    const [token, keyword, stringLit, numberLit, comment] = match;
    if (keyword) {
      nodes.push(
        <span key={key++} className="text-sky-700 dark:text-sky-300">
          {token}
        </span>,
      );
    } else if (stringLit) {
      nodes.push(
        <span key={key++} className="text-emerald-700 dark:text-emerald-300">
          {token}
        </span>,
      );
    } else if (numberLit) {
      nodes.push(
        <span key={key++} className="text-amber-700 dark:text-amber-300">
          {token}
        </span>,
      );
    } else if (comment) {
      nodes.push(
        <span key={key++} className="text-muted-foreground">
          {token}
        </span>,
      );
    } else {
      nodes.push(<span key={key++}>{token}</span>);
    }
    last = match.index + token.length;
  }
  if (last < sql.length) nodes.push(<span key={key++}>{sql.slice(last)}</span>);
  return nodes;
}

function MetaPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1 rounded-full border border-border/60 bg-background px-2.5 py-1 text-[11px]">
      <span className="text-muted-foreground">{label}</span>
      <span className="truncate font-medium text-foreground">{value}</span>
    </span>
  );
}

export function SQLViewer({
  sql,
  queryMeta,
  executionTimeMs,
  rowCount,
  sourceDatabase,
  diff,
  compact = false,
  className,
}: {
  sql: string;
  queryMeta?: QueryMeta | null;
  executionTimeMs?: number;
  rowCount?: number;
  sourceDatabase?: string;
  diff?: SqlDiffLine[] | null;
  /** Demo / hero mode — SQL block only, no meta pills. */
  compact?: boolean;
  className?: string;
}) {
  const [expanded, setExpanded] = React.useState(false);
  const [copied, setCopied] = React.useState(false);
  const lines = sql.split("\n");
  const visible = expanded || lines.length <= 14 ? lines : lines.slice(0, 12);
  const meta = queryMeta;

  async function copy() {
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <div className={cn("space-y-3", className)}>
      {!compact && meta ? (
      <div className="flex flex-wrap gap-1.5">
        {meta.tablesUsed.length ? (
          <MetaPill label="Tables" value={meta.tablesUsed.join(", ")} />
        ) : null}
        {meta.metricsUsed.length ? (
          <MetaPill label="Metrics" value={meta.metricsUsed.join(", ")} />
        ) : null}
        {meta.dimensionsUsed.length ? (
          <MetaPill label="Dimensions" value={meta.dimensionsUsed.join(", ")} />
        ) : null}
        {meta.joinPath.length ? (
          <MetaPill label="Join path" value={meta.joinPath.join(" → ")} />
        ) : null}
        {meta.filtersApplied.length ? (
          <MetaPill label="Filters" value={meta.filtersApplied.join("; ")} />
        ) : null}
        {meta.dateRange ? <MetaPill label="Date range" value={meta.dateRange} /> : null}
        {executionTimeMs != null ? (
          <MetaPill label="Execution" value={`${(executionTimeMs / 1000).toFixed(2)}s`} />
        ) : null}
        {rowCount != null ? (
          <MetaPill label="Rows" value={rowCount.toLocaleString()} />
        ) : null}
        {sourceDatabase ? <MetaPill label="Source" value={sourceDatabase} /> : null}
      </div>
      ) : null}

      <div className="overflow-hidden rounded-xl border border-border/70 bg-[#0f1419] text-[#e7ecf3] shadow-sm dark:border-white/10">
        <div className="flex items-center justify-between border-b border-white/10 px-3 py-2">
          <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-white/55">SQL</p>
          <div className="flex gap-1">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 gap-1.5 px-2 text-xs text-white/70 hover:bg-white/10 hover:text-white"
              onClick={() => void copy()}
            >
              {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
              {copied ? "Copied" : "Copy"}
            </Button>
            {lines.length > 14 ? (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 gap-1.5 px-2 text-xs text-white/70 hover:bg-white/10 hover:text-white"
                onClick={() => setExpanded((value) => !value)}
              >
                <ChevronDown className={cn("size-3.5", expanded && "rotate-180")} />
                {expanded ? "Collapse" : "Expand"}
              </Button>
            ) : null}
          </div>
        </div>
        <pre className="overflow-auto p-3 font-mono text-[11px] leading-5">
          {visible.map((line, index) => (
            <div key={index} className="flex gap-3">
              <span className="w-6 shrink-0 select-none text-right text-white/30">{index + 1}</span>
              <code className="whitespace-pre-wrap">{highlightSql(line || " ")}</code>
            </div>
          ))}
          {!expanded && lines.length > 14 ? (
            <p className="mt-2 text-white/40">… {lines.length - 12} more lines</p>
          ) : null}
        </pre>
      </div>

      {diff?.length ? (
        <div className="overflow-hidden rounded-xl border border-border/70">
          <p className="border-b border-border/60 bg-muted/30 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            SQL diff vs previous turn
          </p>
          <pre className="max-h-56 overflow-auto p-3 font-mono text-[11px] leading-5">
            {diff.map((line, index) => (
              <div
                key={`${line.op}-${index}`}
                className={cn(
                  line.op === "add" && "bg-emerald-500/10 text-emerald-800 dark:text-emerald-200",
                  line.op === "del" && "bg-rose-500/10 text-rose-800 dark:text-rose-200",
                  line.op === "ctx" && "text-muted-foreground",
                )}
              >
                {line.op === "add" ? "+" : line.op === "del" ? "-" : " "}
                {line.text}
              </div>
            ))}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
