"use client";

import { Ban, Calculator, ShieldCheck, Sigma } from "lucide-react";
import { Fragment } from "react";

import { cn } from "@/lib/utils";

import type { BusinessSemanticLayer, DerivedMetricEntry, MeasureEntry } from "./semantic-layer";
import { Chip, ChipList, ExampleQuestions, ExpandButton, Field, FieldLabel } from "./ui";

export function MeasuresTable({
  layer,
  openId,
  onToggle,
}: {
  layer: BusinessSemanticLayer;
  openId: string | null;
  onToggle: (id: string) => void;
}) {
  const dimensionName = new Map(layer.dimensions.map((d) => [d.id, d.name]));
  return (
    <div className="space-y-5">
      <div className="overflow-x-auto rounded-xl border border-border/60">
        <table className="w-full min-w-[820px] text-left text-sm">
          <thead className="bg-muted/30 text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="w-[22%] px-3 py-2.5 font-semibold">Measure</th>
              <th className="w-[24%] px-3 py-2.5 font-semibold">Formula</th>
              <th className="px-3 py-2.5 font-semibold">Business meaning</th>
              <th className="w-[26%] px-3 py-2.5 font-semibold">Dimensions available</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {layer.measures.map((measure) => {
              const open = openId === measure.id;
              return (
                <Fragment key={measure.id}>
                  <tr
                    id={`measure-${measure.id}`}
                    className={cn(
                      "cursor-pointer scroll-mt-28 align-top transition-colors hover:bg-muted/25",
                      open && "bg-primary/5",
                    )}
                    onClick={() => onToggle(measure.id)}
                  >
                    <td className="px-3 py-3">
                      <button
                        type="button"
                        className="text-left"
                        aria-expanded={open}
                        onClick={(event) => {
                          event.stopPropagation();
                          onToggle(measure.id);
                        }}
                      >
                        <span className="block font-semibold text-foreground">{measure.name}</span>
                        <span className="mt-1 flex flex-wrap items-center gap-1.5">
                          <Chip tone="info">{measure.category}</Chip>
                          <ExpandButton open={open} label="Details" />
                        </span>
                      </button>
                    </td>
                    <td className="px-3 py-3 text-[13px] text-foreground">{measure.businessFormula}</td>
                    <td className="px-3 py-3 text-[13px] text-muted-foreground">
                      <span className="line-clamp-2">{measure.definition}</span>
                    </td>
                    <td className="px-3 py-3">
                      <ChipList
                        items={measure.dimensionIds.map((id) => dimensionName.get(id) ?? id)}
                        empty="Own columns only"
                        max={4}
                      />
                    </td>
                  </tr>
                  {open ? (
                    <tr className="bg-primary/[0.03]">
                      <td colSpan={4} className="px-3 pb-4 pt-1">
                        <MeasureDetail measure={measure} layer={layer} />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {layer.derived.length ? (
        <div>
          <FieldLabel>Derived & restricted metrics</FieldLabel>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {layer.derived.map((metric) => (
              <DerivedCard
                key={metric.id}
                metric={metric}
                layer={layer}
                open={openId === metric.id}
                onToggle={() => onToggle(metric.id)}
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function MeasureDetail({ measure, layer }: { measure: MeasureEntry; layer: BusinessSemanticLayer }) {
  const dimensions = layer.dimensions.filter((d) => measure.dimensionIds.includes(d.id));
  return (
    <div className="grid gap-5 rounded-xl border border-border/60 bg-surface-raised p-4 lg:grid-cols-3">
      <div className="space-y-4">
        <Field label="Business definition">
          <p className="leading-relaxed">{measure.definition}</p>
          {!measure.definitionGoverned ? (
            <Chip tone="warning" className="mt-1.5">
              Generated: add a glossary definition
            </Chip>
          ) : null}
        </Field>
        <Field label="Formula">
          <p className="font-medium">{measure.businessFormula}</p>
          <code className="mt-1 block rounded-md bg-muted/40 px-2 py-1 font-mono text-[11px] text-muted-foreground">
            {measure.sqlExpression}
          </code>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Aggregation">{measure.aggregationLabel}</Field>
          <Field label="Format">{measure.formatLabel}</Field>
        </div>
      </div>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Source column">
            {measure.sourceColumns.length ? measure.sourceColumns.map((c) => c.displayName).join(", ") : "Calculated"}
          </Field>
          <Field label="Source table">{measure.sourceTables.map((t) => t.displayName).join(", ") || "—"}</Field>
        </div>
        <Field label="Related dimensions">
          {dimensions.length ? (
            <ul className="space-y-1">
              {dimensions.map((dimension) => (
                <li key={dimension.id} className="flex items-center justify-between gap-2 text-[13px]">
                  <span>{dimension.name}</span>
                  <span className="truncate text-[11px] text-muted-foreground">
                    {(measure.joinPaths[dimension.id] ?? []).length > 1
                      ? `via ${(measure.joinPaths[dimension.id] ?? []).slice(1).join(" → ")}`
                      : "Same table"}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <span className="text-xs text-muted-foreground">Reported on its own columns; no governed dimension joins.</span>
          )}
        </Field>
        <Field label="Also called">
          <ChipList items={measure.synonyms} empty="No business aliases yet" />
        </Field>
      </div>
      <div className="space-y-4">
        <Field label="Example questions">
          <ExampleQuestions items={measure.examples} />
        </Field>
        {measure.rules.length ? (
          <Field label="Governance rules">
            <ul className="space-y-1">
              {measure.rules.map((rule) => (
                <li key={rule} className="flex gap-1.5 text-xs text-muted-foreground">
                  <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-success" />
                  {rule}
                </li>
              ))}
            </ul>
          </Field>
        ) : null}
      </div>
    </div>
  );
}

function DerivedCard({
  metric,
  layer,
  open,
  onToggle,
}: {
  metric: DerivedMetricEntry;
  layer: BusinessSemanticLayer;
  open: boolean;
  onToggle: () => void;
}) {
  const applies = metric.appliesTo
    .map((id) => layer.measures.find((m) => m.id === id)?.name)
    .filter((name): name is string => Boolean(name));
  const Icon = metric.available ? Sigma : Ban;
  return (
    <div
      id={`measure-${metric.id}`}
      className={cn(
        "scroll-mt-28 rounded-xl border bg-background/50 transition-colors",
        open ? "border-primary/40" : "border-border/60",
      )}
    >
      <button type="button" className="flex w-full items-start gap-3 p-3 text-left" onClick={onToggle} aria-expanded={open}>
        <span
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-lg",
            metric.available ? "bg-primary/10 text-primary" : "bg-danger/10 text-danger",
          )}
        >
          <Icon className="size-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold text-foreground">{metric.name}</span>
            <Chip tone={metric.available ? "primary" : "danger"}>
              {metric.available ? "Derived metric" : "Not answerable"}
            </Chip>
          </span>
          <span className={cn("mt-1 block text-xs text-muted-foreground", !open && "line-clamp-2")}>
            {metric.definition}
          </span>
        </span>
        <ExpandButton open={open} label="More" />
      </button>
      {open ? (
        <div className="space-y-3 border-t border-border/50 px-3 pb-3 pt-3">
          {metric.available ? (
            <Field label="Applies to">
              <ChipList items={applies} empty="Any additive measure" />
            </Field>
          ) : null}
          <Field label="Also called">
            <ChipList items={metric.synonyms} empty="No aliases" />
          </Field>
          {metric.rules.length ? (
            <Field label={metric.available ? "Calculation rules" : "What the AI does instead"}>
              <ul className="space-y-1 text-xs text-muted-foreground">
                {metric.rules.map((rule) => (
                  <li key={rule} className="flex gap-1.5">
                    <Calculator className="mt-0.5 size-3.5 shrink-0 text-primary/70" />
                    {rule}
                  </li>
                ))}
              </ul>
            </Field>
          ) : null}
          {metric.examples.length ? (
            <Field label="Example questions">
              <ExampleQuestions items={metric.examples} />
            </Field>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
