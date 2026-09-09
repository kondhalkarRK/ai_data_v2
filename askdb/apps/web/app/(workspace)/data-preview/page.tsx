"use client";

import type { PreviewPage, PreviewTableSummary } from "@nql/shared-types";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";

export default function DataPreviewPage() {
  const industry = useActiveIndustry();
  const [selected, setSelected] = useState<string | null>(null);

  const tables = useQuery({
    queryKey: ["data-tables", industry],
    queryFn: () => apiClient.get<PreviewTableSummary[]>("/api/v1/data/tables", { industry }),
  });

  const activeTable = selected ?? tables.data?.[0]?.name ?? null;

  const preview = useInfiniteQuery({
    queryKey: ["data-preview", industry, activeTable],
    enabled: Boolean(activeTable),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams();
      if (pageParam) params.set("cursor", pageParam);
      const qs = params.toString();
      return apiClient.get<PreviewPage>(
        `/api/v1/data/preview/${activeTable}${qs ? `?${qs}` : ""}`,
        { industry },
      );
    },
    getNextPageParam: (last) => (last.meta.hasMore ? last.meta.nextCursor : undefined),
  });

  const columns = preview.data?.pages[0]?.columns ?? [];
  const rows = useMemo(
    () => preview.data?.pages.flatMap((page) => page.items) ?? [],
    [preview.data],
  );

  return (
    <>
      <PageHeader
        title="Data Preview"
        description="Browse semantic tables for the active industry with server-side keyset pagination."
      />

      {tables.isPending ? (
        <LoadingState size="sm" title="Loading tables" />
      ) : tables.isError ? (
        <Card>
          <CardContent className="pt-5 text-sm text-danger">
            Could not load tables. Check that the analytics database is migrated and seeded.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
          <Card className="h-fit">
            <CardContent className="space-y-1 pt-4">
              <CardTitle className="mb-2 text-sm">Tables</CardTitle>
              {tables.data?.map((table) => (
                <button
                  key={table.name}
                  type="button"
                  onClick={() => setSelected(table.name)}
                  className={cn(
                    "flex w-full flex-col rounded-md px-2.5 py-2 text-left text-sm transition-colors",
                    activeTable === table.name
                      ? "bg-primary/10 text-foreground"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                  )}
                >
                  <span className="font-medium">{table.displayName}</span>
                  <span className="font-mono text-2xs opacity-80">{table.physicalName}</span>
                  <CardDescription className="mt-0.5 text-2xs">
                    {table.tableType}
                    {table.estimatedRows != null
                      ? ` · ~${table.estimatedRows.toLocaleString()} rows`
                      : ""}
                  </CardDescription>
                </button>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              {!activeTable ? (
                <p className="text-sm text-muted-foreground">Select a table to preview.</p>
              ) : preview.isPending ? (
                <LoadingState size="sm" title="Loading rows" />
              ) : preview.isError ? (
                <p className="text-sm text-danger">Preview failed for {activeTable}.</p>
              ) : (
                <>
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <CardTitle className="text-sm">{activeTable}</CardTitle>
                      <CardDescription className="font-mono text-2xs">
                        {preview.data?.pages[0]?.physicalName}
                      </CardDescription>
                    </div>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={!preview.hasNextPage || preview.isFetchingNextPage}
                      onClick={() => void preview.fetchNextPage()}
                    >
                      {preview.isFetchingNextPage ? "Loading…" : "Load more"}
                    </Button>
                  </div>
                  <div className="overflow-auto rounded-md border border-border">
                    <table className="min-w-full border-collapse text-left text-xs">
                      <thead className="bg-muted/40">
                        <tr>
                          {columns.map((column) => (
                            <th
                              key={column.name}
                              className="whitespace-nowrap px-3 py-2 font-medium text-muted-foreground"
                            >
                              {column.displayName}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row, index) => (
                          <tr key={index} className="border-t border-border/70">
                            {columns.map((column) => (
                              <td
                                key={column.name}
                                className="max-w-[220px] truncate px-3 py-1.5 font-mono text-foreground"
                                title={String(row.values[column.name] ?? "")}
                              >
                                {formatCell(row.values[column.name])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-2 text-2xs text-muted-foreground">
                    Showing {rows.length.toLocaleString()} rows
                    {preview.hasNextPage ? " (more available)" : ""}. Caps enforced server-side.
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
