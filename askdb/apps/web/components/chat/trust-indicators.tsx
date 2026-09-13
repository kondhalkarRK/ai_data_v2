"use client";

import { AlertTriangle, Check } from "lucide-react";
import * as React from "react";

import type { GroundedSource } from "@/components/chat/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const ALL_SOURCES: GroundedSource[] = [
  "Semantic Layer",
  "Business Glossary",
  "KPI Definition",
  "Data Quality Check",
];

export function TrustIndicators({
  groundedOn,
  ambiguityFlag,
  alternates,
  onClarify,
  className,
}: {
  groundedOn: GroundedSource[];
  ambiguityFlag: boolean;
  alternates?: string[];
  onClarify?: (text: string) => void;
  className?: string;
}) {
  if (ambiguityFlag) {
    return (
      <div
        className={cn(
          "rounded-xl border border-amber-500/30 bg-amber-500/8 px-3 py-2.5 text-sm",
          className,
        )}
      >
        <p className="flex items-start gap-2 font-medium text-amber-800 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          This question was ambiguous — showing the most likely interpretation.
        </p>
        {alternates?.length ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {alternates.map((item) => (
              <Button
                key={item}
                type="button"
                size="sm"
                variant="secondary"
                className="h-7 text-xs"
                onClick={() => onClarify?.(item)}
              >
                {item}
              </Button>
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  const active = new Set(groundedOn);
  return (
    <div className={cn("space-y-1.5", className)}>
      <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
        Grounded on
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {ALL_SOURCES.map((source) => {
          const used = active.has(source);
          return (
            <li
              key={source}
              className={cn(
                "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px]",
                used
                  ? "border-emerald-500/25 bg-emerald-500/8 text-foreground"
                  : "border-border/60 text-muted-foreground/55",
              )}
            >
              {used ? <Check className="size-3 text-emerald-600" aria-hidden="true" /> : null}
              {source}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
