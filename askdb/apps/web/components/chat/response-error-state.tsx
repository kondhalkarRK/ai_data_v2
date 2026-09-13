"use client";

import { AlertCircle, Ban, Bot, DatabaseZap, HelpCircle, Layers } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type ResponseErrorKind =
  | "zero_rows"
  | "execution"
  | "dq"
  | "ambiguous"
  | "llm"
  | "sql_generation"
  | "semantic"
  | "generic";

const KIND_ICON: Record<ResponseErrorKind, typeof AlertCircle> = {
  zero_rows: Ban,
  execution: DatabaseZap,
  dq: DatabaseZap,
  ambiguous: HelpCircle,
  llm: Bot,
  sql_generation: AlertCircle,
  semantic: Layers,
  generic: HelpCircle,
};

export function ResponseErrorState({
  kind,
  title,
  detail,
  sql,
  suggestions,
  onAsk,
  onRetry,
  className,
}: {
  kind: ResponseErrorKind;
  title: string;
  detail: string;
  sql?: string;
  suggestions?: string[];
  onAsk?: (text: string) => void;
  onRetry?: () => void;
  className?: string;
}) {
  const Icon = KIND_ICON[kind] ?? HelpCircle;

  return (
    <div
      className={cn(
        "rounded-2xl border border-border/70 bg-muted/20 px-4 py-5 text-sm",
        className,
      )}
    >
      <div className="flex gap-3">
        <Icon className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div className="min-w-0 space-y-2">
          <h3 className="font-semibold tracking-tight">{title}</h3>
          <p className="text-muted-foreground">{detail}</p>
          {sql ? (
            <details className="rounded-lg border border-border/60 bg-background/80">
              <summary className="cursor-pointer px-3 py-2 text-xs font-medium">
                View attempted SQL
              </summary>
              <pre className="overflow-auto border-t border-border/60 p-3 font-mono text-[11px]">
                {sql}
              </pre>
            </details>
          ) : null}
          <div className="flex flex-wrap gap-2 pt-1">
            {onRetry ? (
              <Button type="button" size="sm" variant="secondary" onClick={onRetry}>
                Try Again
              </Button>
            ) : null}
            {suggestions?.map((item) => (
              <Button
                key={item}
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => onAsk?.(item)}
              >
                {item}
              </Button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function failureKindFromCategory(category?: string): ResponseErrorKind {
  switch (category) {
    case "llm":
    case "circuit_open":
    case "timeout":
      return "llm";
    case "sql_generation":
      return "sql_generation";
    case "database":
      return "execution";
    case "semantic":
      return "semantic";
    case "ambiguous":
      return "ambiguous";
    default:
      return "generic";
  }
}
