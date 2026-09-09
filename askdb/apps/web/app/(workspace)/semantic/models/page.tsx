"use client";

import { KeyRound, Link2 } from "lucide-react";

import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { useSemanticPack } from "@/hooks/use-semantic";

export default function SemanticModelsPage() {
  const pack = useSemanticPack();

  return (
    <>
      <PageHeader
        title="Semantic Models"
        description="Validated tables, grains, keys, columns and join contracts from the active YAML pack."
      />
      {pack.isPending ? (
        <LoadingState size="sm" title="Loading model contracts" />
      ) : pack.isError ? (
        <p className="text-sm text-danger">The semantic model is unavailable.</p>
      ) : (
        <>
          <div id="tables" className="grid gap-4 lg:grid-cols-2">
            {Object.entries(pack.data.model.tables).map(([name, table]) => (
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
                  <div className="mt-4 max-h-48 overflow-y-auto rounded-[var(--radius-control)] border border-border">
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

          <section id="relationships" className="mt-8">
            <h2 className="mb-3 text-base font-semibold">Relationship contracts</h2>
            <div className="card-surface divide-y divide-border">
              {pack.data.model.relationships.map((relationship) => (
                <div key={relationship.name} className="flex gap-3 px-4 py-3 text-sm">
                  <Link2 className="mt-0.5 size-4 shrink-0 text-primary" />
                  <div>
                    <p className="font-medium">
                      {relationship.displayName ?? relationship.name}
                    </p>
                    <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                      {relationship.fromTable}.{relationship.fromColumn} →{" "}
                      {relationship.toTable}.{relationship.toColumn} · {relationship.type}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </>
  );
}
