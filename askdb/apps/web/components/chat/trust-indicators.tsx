"use client";

import { AlertTriangle, Check, ChevronDown } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { GroundedSource } from "@/components/chat/types";
import { Button } from "@/components/ui/button";
import { useTrustSnapshot } from "@/hooks/use-trust-snapshot";
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
  const trust = useTrustSnapshot(!ambiguityFlag);
  const [open, setOpen] = React.useState(false);

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

  const active = new Set(groundedOn ?? []);
  const snapshot = trust.data;

  return (
    <div className={cn("space-y-2", className)}>
      {snapshot?.available && snapshot.score != null ? (
        <div className="rounded-xl border border-border/60 bg-muted/20">
          <button
            type="button"
            className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            <span>
              Dataset Trust:{" "}
              <span className="font-semibold tabular-nums text-foreground">
                {snapshot.score.toFixed(0)}%
              </span>{" "}
              <span className="text-muted-foreground">({snapshot.label})</span>
            </span>
            <ChevronDown className={cn("size-3.5 text-muted-foreground", open && "rotate-180")} />
          </button>
          {open ? (
            <div className="space-y-2 border-t border-border/50 px-3 py-2">
              <p className="text-[11px] text-muted-foreground">
                {snapshot.formulaNote ||
                  "Sourced from Data Trust Center — not a local confidence estimate."}
              </p>
              <ul className="space-y-1">
                {(snapshot.components ?? []).map((c) => (
                  <li key={c.id} className="flex justify-between gap-2 text-[11px]">
                    <span>{c.label}</span>
                    <span className="tabular-nums text-muted-foreground">
                      {c.score.toFixed(0)} · w {(c.weight * 100).toFixed(0)}%
                    </span>
                  </li>
                ))}
              </ul>
              <Link
                href="/data-quality"
                className="inline-block text-[11px] font-medium underline-offset-2 hover:underline"
              >
                Open Data Trust Center
              </Link>
            </div>
          ) : null}
        </div>
      ) : null}

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
