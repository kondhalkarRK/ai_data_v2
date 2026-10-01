"use client";

import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

import type { BusinessSemanticLayer, DimensionEntry, MeasureEntry } from "./semantic-layer";
import { Chip, ExampleQuestions, FieldLabel, panelClass } from "./ui";

const MAX_SLICES = 6;

/** Business-facing names a measure can be broken down by: real dimensions, plus fact-level attributes. */
export function breakdownsFor(measure: MeasureEntry, dimensionById: Map<string, DimensionEntry>): string[] {
  const names: string[] = [];
  for (const id of measure.dimensionIds) {
    const dimension = dimensionById.get(id);
    if (!dimension) continue;
    if (dimension.synthetic) {
      names.push(...dimension.attributes.filter((attr) => attr.aiResolvable).map((attr) => attr.name));
    } else {
      names.push(dimension.type === "Time" ? "Time" : dimension.name);
    }
  }
  const unique = [...new Set([...names, ...measure.localBreakdowns])];
  return unique.sort((a, b) => Number(b === "Time") - Number(a === "Time"));
}

export function MeasureCards({
  layer,
  openId,
  onToggle,
}: {
  layer: BusinessSemanticLayer;
  openId: string | null;
  onToggle: (id: string) => void;
}) {
  const dimensionById = new Map(layer.dimensions.map((dimension) => [dimension.id, dimension]));
  const derived = layer.derived.filter((metric) => metric.available);

  return (
    <div className="space-y-5">
      <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {layer.measures.map((measure) => {
          const open = openId === measure.id;
          const slices = breakdownsFor(measure, dimensionById);
          const shown = open ? slices : slices.slice(0, MAX_SLICES);
          return (
            <li
              key={measure.id}
              id={`measure-${measure.id}`}
              className={cn(panelClass, "scroll-mt-28 transition-colors", open && "border-primary/40 md:col-span-2 xl:col-span-3")}
            >
              <button
                type="button"
                className="flex w-full flex-col gap-3 p-5 text-left"
                aria-expanded={open}
                onClick={() => onToggle(measure.id)}
              >
                <span className="flex w-full items-start justify-between gap-3">
                  <span className="min-w-0">
                    <span className="block text-[15px] font-semibold text-foreground">{measure.name}</span>
                    <span className={cn("mt-1 block text-xs leading-relaxed text-muted-foreground", !open && "line-clamp-2")}>
                      {measure.definition}
                    </span>
                  </span>
                  <ChevronDown
                    className={cn("mt-1 size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
                  />
                </span>
                <span className="block">
                  <span className="mb-1.5 block text-[11px] font-medium text-muted-foreground">Break it down by</span>
                  {slices.length ? (
                    <span className="flex flex-wrap gap-1.5">
                      {shown.map((name) => (
                        <Chip key={name} tone="success">
                          {name}
                        </Chip>
                      ))}
                      {slices.length > shown.length ? <Chip>+{slices.length - shown.length} more</Chip> : null}
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">Totals only</span>
                  )}
                </span>
              </button>

              {open ? (
                <div className="grid gap-5 border-t border-border/60 p-5 lg:grid-cols-2">
                  <div>
                    <FieldLabel>How it is calculated</FieldLabel>
                    <p className="text-sm text-foreground">{measure.businessFormula}</p>
                    {measure.synonyms.length ? (
                      <div className="mt-4">
                        <FieldLabel>Also called</FieldLabel>
                        <p className="text-sm text-foreground">{measure.synonyms.join(", ")}</p>
                      </div>
                    ) : null}
                  </div>
                  <div>
                    <FieldLabel>Ask the AI</FieldLabel>
                    <ExampleQuestions items={measure.examples.slice(0, 3)} />
                  </div>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>

      {derived.length ? (
        <p className="text-xs leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">Calculated on top of any measure:</span>{" "}
          {derived.map((metric) => metric.name).join(", ")}
        </p>
      ) : null}
    </div>
  );
}
