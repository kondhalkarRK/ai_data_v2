"use client";

import { ArrowRight, Search, X } from "lucide-react";
import * as React from "react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { searchSemanticLayer, type BusinessSemanticLayer, type SearchHit, type SearchKind } from "./semantic-layer";
import { Chip, panelClass, type Tone } from "./ui";

const KIND_TONE: Record<SearchKind, Tone> = {
  Measure: "info",
  Metric: "primary",
  Dimension: "success",
  Attribute: "success",
  Value: "neutral",
  "Business term": "warning",
};

const COMMON_TERMS = ["sales", "brand", "territory", "growth", "premium", "claims", "channel", "price", "customer"];

function suggestionsFor(layer: BusinessSemanticLayer): string[] {
  const picks = COMMON_TERMS.filter((term) =>
    searchSemanticLayer(layer, term, 1).some((hit) => hit.score >= 80),
  );
  for (const row of layer.understanding) {
    if (picks.length >= 5) break;
    const term = row.terms.find((t) => t.length >= 4 && t.length <= 14 && !picks.includes(t.toLowerCase()));
    if (term && row.targets[0]?.kind !== "Value") picks.push(term.toLowerCase());
  }
  return picks.slice(0, 5);
}

export function SemanticSearch({
  layer,
  query,
  onQueryChange,
  onPick,
}: {
  layer: BusinessSemanticLayer;
  query: string;
  onQueryChange: (value: string) => void;
  onPick: (hit: SearchHit) => void;
}) {
  const hits = React.useMemo(() => searchSemanticLayer(layer, query), [layer, query]);
  const suggestions = React.useMemo(() => suggestionsFor(layer), [layer]);
  const active = query.trim().length >= 2;

  return (
    <div className={cn(panelClass, "p-5")}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            className="h-11 pl-9 pr-9 text-sm"
            placeholder="Search a metric, dimension or business term"
            aria-label="Semantic search"
          />
          {query ? (
            <button
              type="button"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
              onClick={() => onQueryChange("")}
              aria-label="Clear search"
            >
              <X className="size-4" />
            </button>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <span>Try</span>
          {suggestions.map((item) => (
            <button
              key={item}
              type="button"
              className="rounded-full border border-border/70 px-2.5 py-1 hover:border-primary/40 hover:text-foreground"
              onClick={() => onQueryChange(item)}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      {active ? (
        <div className="mt-3" aria-live="polite">
          {hits.length ? (
            <>
              <p className="mb-2 text-[11px] text-muted-foreground">
                {hits.length} match{hits.length === 1 ? "" : "es"} for “{query.trim()}”
              </p>
              <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {hits.map((hit) => (
                  <li key={hit.key}>
                    <button
                      type="button"
                      className="group flex w-full items-start gap-2.5 rounded-xl border border-border/60 bg-background/50 px-3 py-2 text-left transition-colors hover:border-primary/40 hover:bg-primary/5"
                      onClick={() => onPick(hit)}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span className="truncate text-sm font-medium text-foreground">{hit.label}</span>
                          <Chip tone={KIND_TONE[hit.kind]}>{hit.kind}</Chip>
                        </span>
                        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{hit.context}</span>
                      </span>
                      <ArrowRight className="mt-1 size-3.5 shrink-0 text-muted-foreground group-hover:text-primary" />
                    </button>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="py-3 text-sm text-muted-foreground">
              Nothing in the semantic layer matches “{query.trim()}”. The AI would ask a clarifying question for this
              term.
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}
