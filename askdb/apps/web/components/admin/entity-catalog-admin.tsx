"use client";

import { Loader2, RefreshCw } from "lucide-react";

import { LoadingState } from "@/components/loading/loading-state";
import { IndustrySwitcher } from "@/components/shell/industry-switcher";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/status-pill";
import { useCatalogEntities, useCatalogRefresh, useCatalogSummary } from "@/hooks/use-entity-catalog";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const TABLE_HEAD = "px-3 py-2 text-left text-xs font-medium text-muted-foreground";
const TABLE_CELL = "px-3 py-2";

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function refreshError(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) {
    return "A refresh is already running. The catalog updates when it finishes.";
  }
  if (error instanceof ApiError) return error.message;
  return "The refresh could not start. The current catalog is still in use.";
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="pt-4">
        <CardDescription>{label}</CardDescription>
        <p className="mt-1 truncate text-xl font-semibold tabular-nums text-foreground" title={value}>
          {value}
        </p>
      </CardContent>
    </Card>
  );
}

/** Lightweight governance view of the business values AI Chat recognises. */
export function EntityCatalogAdminPanel() {
  const summary = useCatalogSummary();
  const entities = useCatalogEntities();
  const refresh = useCatalogRefresh();

  if (summary.isPending || entities.isPending) return <LoadingState title="Loading Entity Catalog" />;
  if (summary.isError || entities.isError || !summary.data) {
    return (
      <EmptyState
        title="The Entity Catalog could not be loaded"
        detail={
          summary.error instanceof ApiError
            ? summary.error.message
            : "AI Chat keeps working with the semantic pack vocabulary."
        }
      />
    );
  }

  const data = summary.data;
  const rows = [...(entities.data ?? [])].sort(
    (a, b) => b.newValues - a.newValues || a.group.localeCompare(b.group) || a.label.localeCompare(b.label),
  );
  const lastRefresh = data.lastCompleted?.finishedAt ?? data.lastRefresh?.finishedAt ?? null;
  const running = refresh.isPending || data.lastRefresh?.status === "running";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted-foreground">
          The business values AI Chat recognises, such as brands, models and cities. Refresh after a data load
          so new values are understood straight away.
        </p>
        <div className="flex items-center gap-2">
          <IndustrySwitcher />
          <Button onClick={() => refresh.mutate("catalog")} disabled={running}>
            {running ? <Loader2 className="animate-spin" /> : <RefreshCw />}
            Refresh Catalog
          </Button>
        </div>
      </div>

      {!data.available ? (
        <p role="alert" className="rounded-[var(--radius-control)] bg-warning/10 px-3 py-2 text-sm">
          The catalog store is unavailable, so the list below comes from the semantic pack and counts are not live.
        </p>
      ) : null}
      {refresh.isError ? (
        <p role="alert" className="rounded-[var(--radius-control)] bg-danger/10 px-3 py-2 text-sm text-danger">
          {refreshError(refresh.error)}
        </p>
      ) : null}
      {refresh.isSuccess ? (
        <p role="status" className="rounded-[var(--radius-control)] bg-success/10 px-3 py-2 text-sm text-success">
          Catalog refreshed. {refresh.data.refresh.newValueCount.toLocaleString()} new value
          {refresh.data.refresh.newValueCount === 1 ? "" : "s"} detected.
        </p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label="Business entities" value={data.totalEntities.toLocaleString()} />
        <Tile label="New values detected" value={data.newValues.toLocaleString()} />
        <Tile label="Last refresh" value={formatDate(lastRefresh)} />
        <Tile label="Last data load ID" value={data.lastLoadId ?? "—"} />
      </div>

      <Card>
        <CardContent className="overflow-x-auto p-0">
          {rows.length ? (
            <table className="w-full text-sm">
              <thead className="border-b border-border/70">
                <tr>
                  <th className={TABLE_HEAD}>Business entity</th>
                  <th className={TABLE_HEAD}>Entity type</th>
                  <th className={cn(TABLE_HEAD, "text-right")}>Distinct values</th>
                  <th className={cn(TABLE_HEAD, "text-right")}>New values</th>
                  <th className={TABLE_HEAD}>Last refreshed</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key} className="border-b border-border/40 last:border-0">
                    <td className={cn(TABLE_CELL, "font-medium text-foreground")}>{row.label}</td>
                    <td className={cn(TABLE_CELL, "text-muted-foreground")}>{row.group}</td>
                    <td className={cn(TABLE_CELL, "text-right tabular-nums")}>{row.distinctValues.toLocaleString()}</td>
                    <td className={cn(TABLE_CELL, "text-right tabular-nums")}>
                      {row.newValues ? (
                        <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
                          +{row.newValues.toLocaleString()}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">0</span>
                      )}
                    </td>
                    <td className={cn(TABLE_CELL, "text-muted-foreground")}>{formatDate(row.lastUpdated)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="p-6 text-center text-sm text-muted-foreground">No entities are catalogued for this industry.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
