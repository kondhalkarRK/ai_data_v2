"use client";

import { ArrowRight } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

import type { BusinessSemanticLayer, UnderstandingKind, UnderstandingRow } from "./semantic-layer";
import { Chip, SegmentedTabs, type Tone } from "./ui";

export type AiTab = "concepts" | "values" | "ambiguous" | "unavailable";

const KIND_TONE: Record<UnderstandingKind, Tone> = {
  Measure: "info",
  Metric: "primary",
  Dimension: "success",
  Attribute: "success",
  "Value filter": "neutral",
  Value: "neutral",
  "Not available": "danger",
};

const PAGE = 40;

export function aiRowId(key: string): string {
  return `ai-${key.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`;
}

export function aiTabFor(row: UnderstandingRow): AiTab {
  if (row.targets.some((t) => t.kind === "Not available")) return "unavailable";
  if (row.ambiguous) return "ambiguous";
  if (row.targets.every((t) => t.kind === "Value")) return "values";
  return "concepts";
}

export function AiUnderstanding({
  layer,
  tab,
  onTabChange,
  focusKey,
}: {
  layer: BusinessSemanticLayer;
  tab: AiTab;
  onTabChange: (tab: AiTab) => void;
  focusKey: string | null;
}) {
  const [limit, setLimit] = React.useState(PAGE);
  const groups = React.useMemo(() => {
    const out: Record<AiTab, UnderstandingRow[]> = { concepts: [], values: [], ambiguous: [], unavailable: [] };
    for (const row of layer.understanding) out[aiTabFor(row)].push(row);
    return out;
  }, [layer.understanding]);

  const rows = groups[tab];
  const focusIndex = focusKey ? rows.findIndex((row) => row.key === focusKey) : -1;
  const visible = rows.slice(0, Math.max(limit, focusIndex + 1));

  const options: Array<{ value: AiTab; label: string }> = [
    { value: "concepts", label: `Business concepts (${groups.concepts.length})` },
    { value: "values", label: `Value synonyms (${groups.values.length})` },
    { value: "ambiguous", label: `Needs context (${groups.ambiguous.length})` },
    { value: "unavailable", label: `Not answerable (${groups.unavailable.length})` },
  ];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SegmentedTabs
          value={tab}
          options={options}
          onChange={(value) => {
            onTabChange(value);
            setLimit(PAGE);
          }}
          ariaLabel="AI understanding category"
        />
        <p className="text-xs text-muted-foreground">{hint(tab)}</p>
      </div>
      <div className="overflow-x-auto rounded-xl border border-border/60">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-muted/30 text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="w-[40%] px-3 py-2.5 font-semibold">When a user says</th>
              <th className="w-[6%] px-1 py-2.5" aria-hidden="true" />
              <th className="px-3 py-2.5 font-semibold">AI understands as</th>
              <th className="w-[16%] px-3 py-2.5 font-semibold">Learned from</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {visible.map((row) => (
              <tr
                key={row.key}
                id={aiRowId(row.key)}
                className={cn("scroll-mt-28 align-top", row.key === focusKey && "bg-primary/8")}
              >
                <td className="px-3 py-2.5">
                  <span className="flex flex-wrap gap-1">
                    {row.terms.map((term) => (
                      <span
                        key={term}
                        className="rounded-md border border-border/60 bg-background/60 px-1.5 py-0.5 text-xs text-foreground"
                      >
                        {term}
                      </span>
                    ))}
                  </span>
                </td>
                <td className="px-1 py-2.5 text-center">
                  <ArrowRight className="mx-auto mt-0.5 size-4 text-primary/70" />
                </td>
                <td className="px-3 py-2.5">
                  <ul className="space-y-1">
                    {row.targets.map((target) => (
                      <li key={`${target.kind}:${target.label}`} className="flex flex-wrap items-center gap-1.5">
                        <span className="font-semibold text-foreground">{target.label}</span>
                        <Chip tone={KIND_TONE[target.kind]}>{target.kind}</Chip>
                        {target.kind === "Value" && target.detail ? (
                          <span className="text-[11px] text-muted-foreground">in {target.detail}</span>
                        ) : null}
                        {target.kind === "Not available" && target.detail ? (
                          <span className="basis-full text-[11px] text-muted-foreground">{target.detail}</span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </td>
                <td className="px-3 py-2.5 text-[11px] text-muted-foreground">{row.sources.join(", ")}</td>
              </tr>
            ))}
            {!rows.length ? (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-sm text-muted-foreground">
                  {tab === "ambiguous"
                    ? "No business term maps to more than one concept."
                    : "Nothing recorded in this category."}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      {rows.length > visible.length ? (
        <button
          type="button"
          className="text-xs font-medium text-primary hover:underline"
          onClick={() => setLimit((value) => value + PAGE * 2)}
        >
          Show more ({rows.length - visible.length} remaining)
        </button>
      ) : null}
    </div>
  );
}

function hint(tab: AiTab): string {
  switch (tab) {
    case "concepts":
      return "Business words mapped to a governed measure, dimension or attribute.";
    case "values":
      return "Everyday names normalised to the canonical value stored in the data.";
    case "ambiguous":
      return "Terms with several meanings; the AI uses the rest of the question or asks.";
    case "unavailable":
      return "Concepts the data cannot answer; the AI explains and offers alternatives.";
  }
}
