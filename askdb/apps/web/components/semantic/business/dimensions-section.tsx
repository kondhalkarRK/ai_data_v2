"use client";

import { ChevronRight, Sparkles } from "lucide-react";
import { Fragment } from "react";

import { cn } from "@/lib/utils";

import type { AttributeEntry, BusinessSemanticLayer, DimensionEntry } from "./semantic-layer";
import { Chip, ChipList, ExampleQuestions, ExpandButton, Field, FieldLabel, type Tone } from "./ui";

const TYPE_TONE: Record<string, Tone> = {
  Vehicle: "info",
  Product: "info",
  Geography: "success",
  Time: "warning",
};

export function DimensionsTable({
  layer,
  openId,
  onToggle,
}: {
  layer: BusinessSemanticLayer;
  openId: string | null;
  onToggle: (id: string) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border/60">
      <table className="w-full min-w-[820px] text-left text-sm">
        <thead className="bg-muted/30 text-[11px] uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="w-[20%] px-3 py-2.5 font-semibold">Dimension</th>
            <th className="w-[14%] px-3 py-2.5 font-semibold">Type</th>
            <th className="px-3 py-2.5 font-semibold">Description</th>
            <th className="w-[30%] px-3 py-2.5 font-semibold">Synonyms</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/50">
          {layer.dimensions.map((dimension) => {
            const open = openId === dimension.id;
            return (
              <Fragment key={dimension.id}>
                <tr
                  id={`dimension-${dimension.id}`}
                  className={cn(
                    "cursor-pointer scroll-mt-28 align-top transition-colors hover:bg-muted/25",
                    open && "bg-primary/5",
                  )}
                  onClick={() => onToggle(dimension.id)}
                >
                  <td className="px-3 py-3">
                    <button
                      type="button"
                      className="text-left"
                      aria-expanded={open}
                      onClick={(event) => {
                        event.stopPropagation();
                        onToggle(dimension.id);
                      }}
                    >
                      <span className="block font-semibold text-foreground">{dimension.name}</span>
                      <span className="mt-1 flex items-center gap-1.5">
                        <span className="text-[11px] text-muted-foreground">
                          {dimension.type === "Time"
                            ? "Time period"
                            : `${dimension.attributes.length} attribute${dimension.attributes.length === 1 ? "" : "s"}`}
                        </span>
                        <ExpandButton open={open} label="Details" />
                      </span>
                    </button>
                  </td>
                  <td className="px-3 py-3">
                    <Chip tone={TYPE_TONE[dimension.type] ?? "primary"}>{dimension.type}</Chip>
                  </td>
                  <td className="px-3 py-3 text-[13px] text-muted-foreground">
                    <span className="line-clamp-2">{dimension.definition}</span>
                  </td>
                  <td className="px-3 py-3">
                    <ChipList items={dimension.aliases} empty="No synonyms yet" max={5} />
                  </td>
                </tr>
                {open ? (
                  <tr className="bg-primary/[0.03]">
                    <td colSpan={4} className="px-3 pb-4 pt-1">
                      <DimensionDetail dimension={dimension} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DimensionDetail({ dimension }: { dimension: DimensionEntry }) {
  const normalised = dimension.attributes
    .flatMap((attr) => attr.values.filter((v) => v.aliases.length).map((v) => ({ attr: attr.name, ...v })))
    .slice(0, 6);
  return (
    <div className="space-y-4 rounded-xl border border-border/60 bg-surface-raised p-4">
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-4">
          <Field label="Dimension name">
            <span className="font-medium">{dimension.name}</span>
            <span className="ml-2 text-xs text-muted-foreground">{dimension.source.displayName}</span>
          </Field>
          <Field label="Business definition">
            <p className="leading-relaxed">{dimension.definition}</p>
            {!dimension.definitionGoverned ? (
              <Chip tone="warning" className="mt-1.5">
                Generated: add a glossary definition
              </Chip>
            ) : null}
          </Field>
          {dimension.hierarchy ? (
            <Field label={`Drill-down (${dimension.hierarchy.name})`}>
              <span className="flex flex-wrap items-center gap-1 text-[13px]">
                {dimension.hierarchy.levels.map((level, index) => (
                  <span key={level} className="inline-flex items-center gap-1">
                    {index ? <ChevronRight className="size-3 text-muted-foreground" /> : null}
                    {level}
                  </span>
                ))}
              </span>
            </Field>
          ) : null}
        </div>
        <div className="space-y-4">
          <Field label="Aliases">
            <ChipList items={dimension.aliases} empty="No aliases yet" />
          </Field>
          {normalised.length ? (
            <Field label="Values the AI normalises">
              <ul className="space-y-1 text-xs">
                {normalised.map((value) => (
                  <li key={`${value.attr}:${value.value}`} className="flex items-start gap-1.5">
                    <Sparkles className="mt-0.5 size-3 shrink-0 text-primary/70" />
                    <span className="text-muted-foreground">
                      {value.aliases.slice(0, 3).join(", ")}
                      {value.aliases.length > 3 ? "…" : ""}
                    </span>
                    <span className="text-muted-foreground">→</span>
                    <span className="font-medium text-foreground">{value.value}</span>
                  </li>
                ))}
              </ul>
            </Field>
          ) : null}
        </div>
        <Field label="Example questions">
          <ExampleQuestions items={dimension.examples} />
        </Field>
      </div>

      {dimension.attributes.length ? (
        <div>
          <FieldLabel>Business attributes & example values</FieldLabel>
          <div className="overflow-hidden rounded-lg border border-border/50">
            <table className="w-full text-left text-[13px]">
              <thead className="bg-muted/25 text-[10px] uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="w-[18%] px-3 py-2 font-semibold">Attribute</th>
                  <th className="w-[30%] px-3 py-2 font-semibold">Meaning</th>
                  <th className="w-[22%] px-3 py-2 font-semibold">Also called</th>
                  <th className="px-3 py-2 font-semibold">Example values</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {dimension.attributes.map((attr) => (
                  <AttributeRow key={attr.id} attr={attr} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function AttributeRow({ attr }: { attr: AttributeEntry }) {
  return (
    <tr className="align-top">
      <td className="px-3 py-2">
        <span className="font-medium text-foreground">{attr.name}</span>
        {attr.aiResolvable ? (
          <Chip tone="success" className="ml-1.5">
            AI-resolved
          </Chip>
        ) : null}
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground">{attr.description}</td>
      <td className="px-3 py-2">
        <ChipList items={attr.synonyms} empty="—" max={4} />
      </td>
      <td className="px-3 py-2">
        {attr.values.length ? (
          <span className="flex flex-wrap gap-1">
            {attr.values.slice(0, 8).map((value) => (
              <span
                key={value.value}
                className="rounded-md border border-border/60 bg-background/60 px-1.5 py-0.5 text-[11px]"
                title={value.aliases.length ? `Also: ${value.aliases.join(", ")}` : undefined}
              >
                {value.value}
              </span>
            ))}
            {attr.values.length > 8 || (attr.distinctValues ?? 0) > 8 ? (
              <span className="px-1 text-[11px] text-muted-foreground">
                +{Math.max(attr.values.length, attr.distinctValues ?? 0) - 8} more
              </span>
            ) : null}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground/80">Free-form or not yet profiled</span>
        )}
      </td>
    </tr>
  );
}
