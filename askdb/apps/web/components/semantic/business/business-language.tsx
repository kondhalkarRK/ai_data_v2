"use client";

import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";

import type { UnderstandingRow, UnderstandingTarget } from "./semantic-layer";
import { Chip, panelClass } from "./ui";

export const languageRowId = (key: string) => `language-${key.replace(/[^a-z0-9]+/gi, "-")}`;

function targetText(target: UnderstandingTarget): string {
  if (target.kind === "Value" && target.detail) return `${target.detail} = ${target.label}`;
  if (target.kind === "Not available") return `${target.label} (not available in this data)`;
  return target.label;
}

export function BusinessLanguage({
  rows,
  showAll,
  onShowAll,
  focusKey,
  limit = 10,
}: {
  rows: UnderstandingRow[];
  showAll: boolean;
  onShowAll: () => void;
  focusKey: string | null;
  limit?: number;
}) {
  if (!rows.length) {
    return <p className="text-sm text-muted-foreground">No business vocabulary is declared in this pack yet.</p>;
  }
  const visible = showAll ? rows : rows.slice(0, limit);

  return (
    <div className={cn(panelClass, "overflow-hidden")}>
      <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] gap-4 border-b border-border/60 bg-muted/30 px-5 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <span>When someone says</span>
        <span aria-hidden="true" className="w-4" />
        <span>The AI reads it as</span>
      </div>
      <ul className="divide-y divide-border/50">
        {visible.map((row) => (
          <li
            key={row.key}
            id={languageRowId(row.key)}
            className={cn(
              "grid scroll-mt-28 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-start gap-4 px-5 py-3",
              row.key === focusKey && "bg-primary/8",
            )}
          >
            <span className="text-sm text-foreground">{row.terms.map((term) => `“${term}”`).join(", ")}</span>
            <ArrowRight className="mt-0.5 size-4 text-muted-foreground" aria-hidden="true" />
            <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
              {row.targets.map(targetText).join(" or ")}
              {row.ambiguous ? <Chip tone="warning">AI asks which one</Chip> : null}
            </span>
          </li>
        ))}
      </ul>
      {!showAll && rows.length > limit ? (
        <button
          type="button"
          className="w-full border-t border-border/60 px-5 py-3 text-center text-xs font-medium text-primary hover:bg-primary/5"
          onClick={onShowAll}
        >
          Show all {rows.length} terms
        </button>
      ) : null}
    </div>
  );
}
