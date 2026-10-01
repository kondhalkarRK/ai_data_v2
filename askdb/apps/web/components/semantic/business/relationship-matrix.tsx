"use client";

import { Check, ChevronRight, Minus } from "lucide-react";

import type { BusinessSemanticLayer } from "./semantic-layer";
import { FieldLabel } from "./ui";

export function RelationshipMatrix({
  layer,
  onPickMeasure,
  onPickDimension,
}: {
  layer: BusinessSemanticLayer;
  onPickMeasure: (id: string) => void;
  onPickDimension: (id: string) => void;
}) {
  const dimensions = layer.dimensions;
  const total = layer.measures.length * dimensions.length;
  const answerable = layer.measures.reduce((sum, m) => sum + m.dimensionIds.length, 0);

  return (
    <div className="space-y-5">
      <p className="text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{answerable}</span> of {total} measure × dimension combinations
        can be answered through governed joins. A dash means the AI will not slice that measure by that dimension.
      </p>
      <div className="overflow-x-auto rounded-xl border border-border/60">
        <table className="w-full text-sm">
          <thead className="bg-muted/30 text-[11px] text-muted-foreground">
            <tr>
              <th className="sticky left-0 z-10 bg-surface-raised px-3 py-2.5 text-left font-semibold uppercase tracking-wide">
                Measure
              </th>
              {dimensions.map((dimension) => (
                <th key={dimension.id} className="px-2 py-2.5 text-center font-semibold">
                  <button
                    type="button"
                    className="whitespace-nowrap hover:text-foreground hover:underline"
                    onClick={() => onPickDimension(dimension.id)}
                  >
                    {dimension.name}
                  </button>
                </th>
              ))}
              <th className="px-3 py-2.5 text-right font-semibold uppercase tracking-wide">Coverage</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {layer.measures.map((measure) => (
              <tr key={measure.id} className="hover:bg-muted/20">
                <th scope="row" className="sticky left-0 z-10 bg-surface-raised px-3 py-2 text-left font-medium">
                  <button
                    type="button"
                    className="whitespace-nowrap text-foreground hover:text-primary hover:underline"
                    onClick={() => onPickMeasure(measure.id)}
                  >
                    {measure.name}
                  </button>
                </th>
                {dimensions.map((dimension) => {
                  const ok = measure.dimensionIds.includes(dimension.id);
                  const path = measure.joinPaths[dimension.id] ?? [];
                  const title = ok
                    ? `${measure.name} by ${dimension.name}${path.length > 1 ? ` (via ${path.slice(1).join(" → ")})` : ""}`
                    : `${measure.name} cannot be analysed by ${dimension.name}`;
                  return (
                    <td key={dimension.id} className="px-2 py-2 text-center" title={title}>
                      {ok ? (
                        <span className="inline-flex size-6 items-center justify-center rounded-md bg-success/15 text-success">
                          <Check className="size-3.5" aria-label={title} />
                        </span>
                      ) : (
                        <Minus className="mx-auto size-3.5 text-muted-foreground/50" aria-label={title} />
                      )}
                    </td>
                  );
                })}
                <td className="px-3 py-2 text-right text-xs tabular-nums text-muted-foreground">
                  {measure.dimensionIds.length}/{dimensions.length}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {layer.hierarchies.length ? (
        <div>
          <FieldLabel>Governed drill-down paths</FieldLabel>
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {layer.hierarchies.map((hierarchy) => (
              <div key={hierarchy.name} className="rounded-xl border border-border/60 bg-background/50 px-3 py-2.5">
                <p className="text-xs font-semibold text-foreground">{hierarchy.name}</p>
                <p className="mt-1 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                  {hierarchy.levels.map((level, index) => (
                    <span key={`${level}-${index}`} className="inline-flex items-center gap-1">
                      {index ? <ChevronRight className="size-3" /> : null}
                      {level}
                    </span>
                  ))}
                </p>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
