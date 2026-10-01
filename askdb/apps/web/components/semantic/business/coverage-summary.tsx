"use client";

import { BookOpenText, Brain, Calculator, Layers3, Link2, Tags } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

import type { CoverageSummary as Coverage } from "./semantic-layer";
import { Chip, panelClass } from "./ui";

export function CoverageSummary({ coverage }: { coverage: Coverage }) {
  const [showGaps, setShowGaps] = React.useState(false);
  const [tone, bar] =
    coverage.aiCoverage >= 85
      ? ["text-success", "bg-success"]
      : coverage.aiCoverage >= 65
        ? ["text-warning", "bg-warning"]
        : ["text-danger", "bg-danger"];

  const tiles = [
    {
      icon: Calculator,
      label: "Measures",
      value: coverage.measures,
      note: coverage.derivedMetrics ? `+${coverage.derivedMetrics} derived metrics` : "Governed calculations",
    },
    { icon: Layers3, label: "Dimensions", value: coverage.dimensions, note: `${coverage.attributes} business attributes` },
    { icon: Link2, label: "Relationships", value: coverage.relationships, note: `Measure × dimension · ${coverage.joins} joins` },
    { icon: BookOpenText, label: "Business Terms", value: coverage.businessTerms, note: "Governed glossary entries" },
    {
      icon: Tags,
      label: "Aliases",
      value: coverage.aliases,
      note: coverage.valueSynonyms ? `+${coverage.valueSynonyms} value synonyms` : "Business synonyms",
    },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {tiles.map((tile) => (
        <div key={tile.label} className={cn(panelClass, "px-4 py-3.5")}>
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <tile.icon className="size-3.5 text-primary" />
            {tile.label}
          </div>
          <p className="mt-1.5 text-2xl font-semibold tabular-nums text-foreground">{tile.value}</p>
          <p className="mt-0.5 truncate text-[11px] text-muted-foreground" title={tile.note}>
            {tile.note}
          </p>
        </div>
      ))}
      <div className={cn(panelClass, "relative px-4 py-3.5")}>
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <Brain className="size-3.5 text-primary" />
          AI Coverage
        </div>
        <p className={cn("mt-1.5 text-2xl font-semibold tabular-nums", tone)}>{coverage.aiCoverage}%</p>
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted/60">
          <div
            className={cn("h-full rounded-full", bar)}
            style={{ width: `${coverage.aiCoverage}%` }}
          />
        </div>
        <button
          type="button"
          className="mt-1.5 text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          onClick={() => setShowGaps((value) => !value)}
          aria-expanded={showGaps}
        >
          {coverage.coveredConcepts} of {coverage.totalConcepts} concepts AI-ready
        </button>
        {showGaps ? (
          <div className="absolute right-0 top-full z-20 mt-2 w-80 rounded-xl border border-border bg-surface-raised p-3 text-xs shadow-lg">
            <p className="font-medium text-foreground">How coverage is measured</p>
            <p className="mt-1 text-muted-foreground">
              A measure, dimension or AI-resolvable attribute counts as AI-ready when it has a governed business
              definition and at least one business alias.
            </p>
            {coverage.gaps.length ? (
              <>
                <p className="mt-3 font-medium text-foreground">Needs attention ({coverage.gaps.length})</p>
                <ul className="mt-1 max-h-48 space-y-1 overflow-y-auto">
                  {coverage.gaps.map((gap) => (
                    <li key={`${gap.kind}:${gap.label}`} className="flex items-start justify-between gap-2">
                      <span>
                        <span className="text-foreground">{gap.label}</span>{" "}
                        <span className="text-muted-foreground">({gap.kind.toLowerCase()})</span>
                      </span>
                      <Chip tone="warning" className="shrink-0">
                        No {gap.missing.join(" or ")}
                      </Chip>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="mt-3 text-success">Every concept is AI-ready.</p>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
