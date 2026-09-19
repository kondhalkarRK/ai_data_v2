"use client";

import type { SemanticPackResponse } from "@nql/shared-types";
import { KeyRound, Link2 } from "lucide-react";

import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";

export function SemanticModelPanel({ pack }: { pack: SemanticPackResponse }) {
  return (
    <div className="space-y-6">
      <div className="grid max-h-[70vh] gap-4 overflow-y-auto lg:grid-cols-2">
        {Object.entries(pack.model.tables).map(([name, table]) => (
          <Card key={name}>
            <CardContent className="pt-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <CardTitle className="text-base">{table.displayName}</CardTitle>
                  <CardDescription className="mt-1 font-mono text-xs">
                    {table.physicalName}
                  </CardDescription>
                </div>
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-2xs font-medium uppercase text-primary">
                  {table.type}
                </span>
              </div>
              <dl className="mt-4 grid grid-cols-[5rem_1fr] gap-x-3 gap-y-2 text-xs">
                <dt className="text-muted-foreground">Grain</dt>
                <dd>{table.grain ?? "Not specified"}</dd>
                <dt className="text-muted-foreground">Primary key</dt>
                <dd className="flex items-center gap-1.5 font-mono">
                  <KeyRound className="size-3 text-warning" />
                  {table.primaryKey}
                </dd>
                <dt className="text-muted-foreground">Columns</dt>
                <dd>{Object.keys(table.columns).length}</dd>
              </dl>
              <div className="mt-4 max-h-40 overflow-y-auto rounded-[var(--radius-control)] border border-border">
                {Object.entries(table.columns).map(([columnName, column]) => (
                  <div
                    key={columnName}
                    className="grid grid-cols-[1fr_6rem] gap-2 border-b border-border px-3 py-2 text-xs last:border-0"
                  >
                    <span className="font-mono">{columnName}</span>
                    <span className="text-right text-muted-foreground">{column.type}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <section>
        <h2 className="mb-3 text-base font-semibold">Relationship contracts</h2>
        <div className="card-surface max-h-[240px] divide-y divide-border overflow-y-auto">
          {pack.model.relationships.map((relationship) => (
            <div key={relationship.name} className="flex gap-3 px-4 py-3 text-sm">
              <Link2 className="mt-0.5 size-4 shrink-0 text-primary" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium">{relationship.displayName ?? relationship.name}</p>
                  <span className="rounded-full border border-border bg-muted/40 px-2 py-0.5 font-mono text-2xs font-semibold">
                    {cardinalityLabel(relationship.type)}
                  </span>
                </div>
                <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                  {relationship.fromTable}.{relationship.fromColumn} → {relationship.toTable}.
                  {relationship.toColumn}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function cardinalityLabel(type: string): string {
  const normalized = type.trim().toLowerCase().replace(/[-\s]/g, "_");
  if (normalized.includes("one_to_one") || normalized === "1:1") return "1:1";
  if (normalized.includes("many_to_one") || normalized.includes("n_to_1") || normalized === "n:1") {
    return "M:1";
  }
  if (normalized.includes("one_to_many") || normalized === "1:n") return "1:M";
  if (normalized.includes("many_to_many") || normalized === "m:n") return "M:N";
  return type || "join";
}
