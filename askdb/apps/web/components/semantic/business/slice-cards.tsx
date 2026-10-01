"use client";

import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

import type { AttributeEntry, BusinessSemanticLayer, DimensionEntry } from "./semantic-layer";
import { Chip, FieldLabel, panelClass } from "./ui";

/** Prefer readable names over short codes (e.g. city names rather than state codes). */
function sampleValues(dimension: DimensionEntry, limit = 4): string[] {
  for (const minLength of [4, 2]) {
    for (const attr of dimension.attributes) {
      const values = attr.values.map((item) => item.value).filter((value) => value.length >= minLength);
      if (values.length >= 2) return values.slice(0, limit);
    }
  }
  return [];
}

function shownAttributes(dimension: DimensionEntry): AttributeEntry[] {
  const resolvable = dimension.attributes.filter((attr) => attr.aiResolvable || attr.values.length);
  return resolvable.length ? resolvable : dimension.attributes;
}

export function SliceCards({
  layer,
  openId,
  onToggle,
}: {
  layer: BusinessSemanticLayer;
  openId: string | null;
  onToggle: (id: string) => void;
}) {
  const dimensions = layer.dimensions.filter((dimension) => dimension.attributes.length || !dimension.synthetic);

  return (
    <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {dimensions.map((dimension) => {
        const open = openId === dimension.id;
        const samples = sampleValues(dimension);
        const attributes = shownAttributes(dimension);
        return (
          <li
            key={dimension.id}
            id={`dimension-${dimension.id}`}
            className={cn(panelClass, "scroll-mt-28 transition-colors", open && "border-primary/40 md:col-span-2 xl:col-span-3")}
          >
            <button
              type="button"
              className="flex w-full flex-col gap-3 p-5 text-left"
              aria-expanded={open}
              onClick={() => onToggle(dimension.id)}
            >
              <span className="flex w-full items-start justify-between gap-3">
                <span className="min-w-0">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="text-[15px] font-semibold text-foreground">{dimension.name}</span>
                    <Chip>{dimension.type}</Chip>
                  </span>
                  <span className={cn("mt-1 block text-xs leading-relaxed text-muted-foreground", !open && "line-clamp-2")}>
                    {dimension.definition}
                  </span>
                </span>
                <ChevronDown
                  className={cn("mt-1 size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
                />
              </span>
              {dimension.hierarchy ? (
                <span className="block text-xs text-foreground">
                  <span className="text-muted-foreground">Drill down: </span>
                  {dimension.hierarchy.levels.join(" → ")}
                </span>
              ) : null}
              {samples.length ? (
                <span className="block truncate text-xs text-foreground">
                  <span className="text-muted-foreground">e.g. </span>
                  {samples.join(", ")}
                </span>
              ) : null}
            </button>

            {open ? (
              <div className="border-t border-border/60 p-5">
                <FieldLabel>What you can filter or group by</FieldLabel>
                <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {attributes.map((attr) => (
                    <li key={attr.id} className="rounded-xl border border-border/60 bg-background/50 p-3">
                      <p className="text-sm font-medium text-foreground">{attr.name}</p>
                      {attr.values.length ? (
                        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                          {attr.values
                            .slice(0, 6)
                            .map((value) => value.value)
                            .join(", ")}
                          {attr.values.length > 6 ? "…" : ""}
                        </p>
                      ) : null}
                      {attr.synonyms.length ? (
                        <p className="mt-1 text-[11px] text-muted-foreground">Also called {attr.synonyms.slice(0, 3).join(", ")}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
                {dimension.aliases.length ? (
                  <p className="mt-4 text-xs text-muted-foreground">
                    People also say: <span className="text-foreground">{dimension.aliases.join(", ")}</span>
                  </p>
                ) : null}
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
