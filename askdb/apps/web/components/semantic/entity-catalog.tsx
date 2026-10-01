"use client";

import {
  Activity,
  Database,
  GitCompareArrows,
  Hash,
  History,
  Layers,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Tag,
  Wand2,
} from "lucide-react";
import { useMemo, useState } from "react";

import { LoadingState } from "@/components/loading/loading-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, StatusPill } from "@/components/ui/status-pill";
import {
  useCatalogChanges,
  useCatalogEntities,
  useCatalogEntity,
  useCatalogRefresh,
  useCatalogSummary,
} from "@/hooks/use-entity-catalog";
import { useSession } from "@/hooks/use-session";
import { ApiError } from "@/lib/api-client";
import type { StatusTone } from "@/lib/design";
import {
  CHANGE_LABEL,
  FILTER_LABEL,
  GROUP_FILTERS,
  READINESS_LABEL,
  SCHEMA_KINDS,
  STATE_FILTERS,
  coverageLabel,
  filterEntities,
  matchReason,
  tablesWithSchemaChanges,
  type CatalogFilter,
} from "@/lib/entity-catalog/filters";
import type {
  CatalogChange,
  CatalogSummary,
  EntityRow,
  Readiness,
  RefreshScope,
} from "@/lib/entity-catalog/types";
import { cn } from "@/lib/utils";

const READINESS_TONE: Record<Readiness, StatusTone> = {
  ai_ready: "ok",
  needs_review: "warn",
  missing_synonyms: "info",
  low_confidence: "fail",
  not_refreshed: "neutral",
};

const UNAVAILABLE_MESSAGE: Record<string, string> = {
  migration_pending:
    "The catalog store has not been set up in the application database yet. An administrator needs to run the database migration (alembic upgrade head). Entities below come from the semantic pack.",
  database_unreachable:
    "The application database is not reachable, so refresh history and live values cannot be shown. Entities below come from the semantic pack; AI Chat keeps working with the pack vocabulary.",
};

const SEVERITY_TONE: Record<string, StatusTone> = { high: "fail", medium: "warn", low: "neutral" };

const IMPACT_TONE: Record<string, string> = {
  High: "text-danger",
  Medium: "text-warning-foreground dark:text-warning",
  Low: "text-muted-foreground",
};

const REFRESH_ACTIONS: { scope: RefreshScope; label: string; hint: string }[] = [
  {
    scope: "catalog",
    label: "Refresh Catalog",
    hint: "Reads warehouse metadata and every tracked column's values, checks for schema drift",
  },
  {
    scope: "values",
    label: "Refresh Entity Values",
    hint: "Re-reads distinct values only (fast); use after a data load",
  },
  {
    scope: "semantic_cache",
    label: "Rebuild Semantic Cache",
    hint: "Reloads the semantic pack, glossary, graph and AI vocabulary from the current catalog",
  },
];

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toLocaleString();
}

function refreshError(error: unknown): string {
  if (error instanceof ApiError && error.status === 403) {
    return "Refreshing the catalog needs analyst access.";
  }
  if (error instanceof ApiError && error.status === 409) {
    return "A refresh is already running. It will appear here when it finishes.";
  }
  if (error instanceof ApiError && error.status === 503) {
    return error.message;
  }
  return "The refresh could not start. The current catalog is still in use.";
}

export function EntityCatalog() {
  const summary = useCatalogSummary();
  const entities = useCatalogEntities();
  const changes = useCatalogChanges();
  const refresh = useCatalogRefresh();
  const { data: user } = useSession();
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Set<CatalogFilter>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);

  const schemaTables = useMemo(() => tablesWithSchemaChanges(changes.data ?? []), [changes.data]);
  const rows = useMemo(
    () => filterEntities(entities.data ?? [], { query, filters, schemaTables }),
    [entities.data, query, filters, schemaTables],
  );
  const activeKey = selected ?? rows[0]?.key ?? null;

  function toggle(filter: CatalogFilter) {
    setFilters((current) => {
      const next = new Set(current);
      if (next.has(filter)) next.delete(filter);
      else next.add(filter);
      return next;
    });
  }

  if (summary.isPending || entities.isPending) {
    return <LoadingState title="Loading Entity Catalog" size="sm" />;
  }
  if (summary.isError || entities.isError || !summary.data) {
    const missing =
      (summary.error instanceof ApiError && summary.error.status === 404) ||
      (entities.error instanceof ApiError && entities.error.status === 404);
    return (
      <EmptyState
        title="The Entity Catalog is not available right now"
        detail={
          missing
            ? "The API does not have the catalog service yet. Restart the API so it loads the latest version."
            : "AI Chat keeps working with the semantic pack vocabulary."
        }
        action={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              void summary.refetch();
              void entities.refetch();
              void changes.refetch();
            }}
          >
            <RefreshCw />
            Try again
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      {!summary.data.available ? (
        <Card className="border-warning/40">
          <CardContent className="pt-5 text-sm">
            <p className="font-semibold text-foreground">Catalog store unavailable</p>
            <p className="mt-1 text-muted-foreground">
              {UNAVAILABLE_MESSAGE[summary.data.unavailableReason ?? ""] ??
                UNAVAILABLE_MESSAGE.database_unreachable}
            </p>
          </CardContent>
        </Card>
      ) : null}
      <RefreshBar
        summary={summary.data}
        pendingScope={refresh.isPending ? (refresh.variables ?? null) : null}
        onRefresh={(scope) => refresh.mutate(scope)}
        errorMessage={refresh.isError ? refreshError(refresh.error) : null}
        canRefresh={user?.role === "admin"}
      />
      <SummaryCards summary={summary.data} />

      <Card>
        <CardHeader className="gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base">Entities</CardTitle>
              <CardDescription>
                Every business column the AI can filter on, with its live values.
              </CardDescription>
            </div>
            <div className="relative w-full sm:w-80">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search entity, value or alias"
                className="pl-8"
                aria-label="Search entity, value or alias"
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filters">
            {[...GROUP_FILTERS, ...STATE_FILTERS].map((filter) => (
              <button
                key={filter}
                type="button"
                aria-pressed={filters.has(filter)}
                onClick={() => toggle(filter)}
                className={cn(
                  "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                  filters.has(filter)
                    ? "border-primary/45 bg-primary/10 text-foreground"
                    : "border-border/60 text-muted-foreground hover:bg-muted/40",
                )}
              >
                {FILTER_LABEL[filter]}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <EntityGrid
              rows={rows}
              query={query}
              activeKey={activeKey}
              onSelect={setSelected}
              total={entities.data?.length ?? 0}
            />
            <EntityDetailPanel key={activeKey ?? "none"} entityKey={activeKey} />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <ChangeMonitor
          title="Schema Drift Monitor"
          description="Column additions, removals, type changes and possible renames. Nothing is applied automatically."
          icon={GitCompareArrows}
          changes={(changes.data ?? []).filter((c) => SCHEMA_KINDS.has(c.kind))}
          empty={
            summary.data.schemaDrift.status === "not_checked"
              ? "Run Refresh Catalog to take the first schema baseline."
              : "No schema changes detected. The warehouse matches the semantic layer."
          }
        />
        <ChangeMonitor
          title="Data Change Monitoring"
          description="New values and changes in distinct counts per entity."
          icon={Activity}
          changes={(changes.data ?? []).filter((c) => !SCHEMA_KINDS.has(c.kind))}
          empty="No value changes since the baseline."
        />
      </div>
    </div>
  );
}

function RefreshBar({
  summary,
  pendingScope,
  onRefresh,
  errorMessage,
  canRefresh,
}: {
  summary: CatalogSummary;
  pendingScope: RefreshScope | null;
  onRefresh: (scope: RefreshScope) => void;
  errorMessage: string | null;
  canRefresh: boolean;
}) {
  const last = summary.lastRefresh;
  const status: { tone: StatusTone; label: string } = pendingScope
    ? { tone: "info", label: "Refreshing…" }
    : !last
      ? { tone: "neutral", label: "Not refreshed yet" }
      : last.status === "failed"
        ? { tone: "fail", label: "Failed" }
        : last.status === "running"
          ? { tone: "info", label: "Refreshing…" }
          : { tone: "ok", label: "Completed" };
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-3 pt-5">
        <div className="mr-auto min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-foreground">Metadata refresh</p>
            <StatusPill tone={status.tone} label={status.label} />
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {last
              ? `Last ${last.trigger.replace("_", " ")} refresh ${formatDate(last.finishedAt ?? last.startedAt)}`
              : "Runs on startup, after data loads, on demand, and when a question names an unknown value."}
            {last?.status === "failed" && last.error ? ` — ${last.error}` : ""}
          </p>
          {errorMessage ? <p className="mt-1 text-xs text-danger">{errorMessage}</p> : null}
        </div>
        {(canRefresh ? REFRESH_ACTIONS : []).map((action, index) => (
          <Button
            key={action.scope}
            variant={index === 0 ? "primary" : "secondary"}
            size="sm"
            title={action.hint}
            disabled={pendingScope !== null}
            onClick={() => onRefresh(action.scope)}
          >
            <RefreshCw className={cn(pendingScope === action.scope && "animate-spin")} />
            {action.label}
          </Button>
        ))}
      </CardContent>
    </Card>
  );
}

function SummaryCards({ summary }: { summary: CatalogSummary }) {
  const drift = summary.schemaDrift;
  const driftTone: StatusTone =
    drift.status === "action_required"
      ? "fail"
      : drift.status === "changes_detected"
        ? "warn"
        : drift.status === "stable"
          ? "ok"
          : "neutral";
  const cards: {
    label: string;
    value: string;
    detail?: string;
    icon: typeof Database;
    tone?: StatusTone;
  }[] = [
    {
      label: "Last Refresh",
      value: formatDate(summary.lastCompleted?.finishedAt),
      detail: summary.lastCompleted ? `Trigger: ${summary.lastCompleted.trigger.replace("_", " ")}` : "Never",
      icon: History,
    },
    {
      label: "Rows Processed",
      value: formatNumber(summary.rowsProcessed),
      detail: "Fact rows at last refresh",
      icon: Database,
    },
    { label: "Last Data Load ID", value: summary.lastLoadId ?? "—", icon: Hash },
    {
      label: "Catalog Version",
      value: summary.catalogVersion ? `v${summary.catalogVersion}` : "—",
      detail: "Changes only when content changes",
      icon: Layers,
    },
    {
      label: "Total Entities",
      value: formatNumber(summary.totalEntities),
      detail: `${formatNumber(summary.totalValues)} distinct values`,
      icon: Tag,
    },
    {
      label: "New Entities Detected",
      value: formatNumber(summary.newValues),
      detail: "New values in the last 7 days",
      icon: Sparkles,
      tone: summary.newValues ? "ai" : undefined,
    },
    {
      label: "Schema Drift",
      value: drift.label,
      detail: drift.count ? `${drift.count} change(s) in 30 days` : undefined,
      icon: GitCompareArrows,
      tone: driftTone,
    },
    {
      label: "AI Coverage",
      value: coverageLabel(summary.aiCoverage),
      detail: "Values AI Chat can resolve by name",
      icon: ShieldCheck,
    },
  ];
  const readiness = summary.entityReadiness;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <Card key={card.label}>
              <CardContent className="pt-4">
                <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                  <Icon className="size-3.5" aria-hidden="true" />
                  {card.label}
                </div>
                {card.tone ? (
                  <StatusPill tone={card.tone} label={card.value} className="mt-2 text-sm" />
                ) : (
                  <p className="mt-1 truncate text-lg font-semibold text-foreground" title={card.value}>
                    {card.value}
                  </p>
                )}
                {card.detail ? (
                  <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{card.detail}</p>
                ) : null}
              </CardContent>
            </Card>
          );
        })}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">AI readiness by entity:</span>
        {(Object.keys(READINESS_LABEL) as Readiness[])
          .filter((key) => key !== "not_refreshed")
          .map((key) => (
          <StatusPill
            key={key}
            tone={READINESS_TONE[key]}
            label={`${READINESS_LABEL[key]} ${readiness[key] ?? 0}`}
          />
        ))}
      </div>
    </div>
  );
}

function EntityGrid({
  rows,
  query,
  activeKey,
  onSelect,
  total,
}: {
  rows: EntityRow[];
  query: string;
  activeKey: string | null;
  onSelect: (key: string) => void;
  total: number;
}) {
  if (!total) {
    return (
      <EmptyState
        title="No entities catalogued yet"
        detail="Run Refresh Catalog to read the warehouse values."
      />
    );
  }
  if (!rows.length) {
    return <EmptyState title="No entities match" detail="Try another search or clear the filters." />;
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-border/60">
      <table className="w-full text-left text-sm">
        <thead className="bg-muted/40 text-xs text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">Domain</th>
            <th className="px-3 py-2 font-medium">Table</th>
            <th className="px-3 py-2 font-medium">Column</th>
            <th className="px-3 py-2 text-right font-medium">Distinct Values</th>
            <th className="px-3 py-2 text-right font-medium">New Values</th>
            <th className="px-3 py-2 font-medium">AI Readiness</th>
            <th className="px-3 py-2 font-medium">Last Updated</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const reason = matchReason(row, query);
            return (
              <tr
                key={row.key}
                onClick={() => onSelect(row.key)}
                className={cn(
                  "cursor-pointer border-t border-border/50 hover:bg-muted/30",
                  activeKey === row.key && "bg-primary/5",
                )}
                aria-selected={activeKey === row.key}
              >
                <td className="px-3 py-2">
                  <button type="button" className="text-left font-medium text-foreground">
                    {row.group} · {row.label}
                  </button>
                  {reason && reason !== "entity" ? (
                    <p className="text-[11px] text-muted-foreground">Matched {reason}</p>
                  ) : null}
                </td>
                <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                  {row.table.split(".").pop()}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{row.column}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatNumber(row.distinctValues)}
                </td>
                <td className="px-3 py-2 text-right">
                  {row.newValues ? (
                    <StatusPill tone="ai" label={`+${row.newValues}`} />
                  ) : (
                    <span className="text-muted-foreground">0</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <StatusPill tone={READINESS_TONE[row.readiness]} label={READINESS_LABEL[row.readiness]} />
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground">
                  {formatDate(row.lastUpdated)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function EntityDetailPanel({ entityKey }: { entityKey: string | null }) {
  const detail = useCatalogEntity(entityKey);
  const [valueQuery, setValueQuery] = useState("");
  if (!entityKey) {
    return <EmptyState title="Select an entity" detail="Its values, aliases and AI rules appear here." />;
  }
  if (detail.isPending) return <LoadingState title="Loading values" size="sm" />;
  if (detail.isError || !detail.data) {
    return <EmptyState title="Values could not be loaded" detail="Try selecting the entity again." />;
  }
  const entity = detail.data;
  const q = valueQuery.trim().toLowerCase();
  const values = entity.values.filter(
    (v) =>
      !q ||
      v.value.toLowerCase().includes(q) ||
      v.aliases.some((alias) => alias.toLowerCase().includes(q)),
  );
  return (
    <div className="flex min-h-0 flex-col rounded-xl border border-border/60 bg-surface-raised/40 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-base font-semibold text-foreground">{entity.label}</p>
          <p className="text-xs text-muted-foreground">
            {entity.group} · {entity.aiKnown ? "In AI value dictionary" : "Watched column"}
          </p>
        </div>
        <StatusPill tone={READINESS_TONE[entity.readiness]} label={READINESS_LABEL[entity.readiness]} />
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
        <dt className="text-muted-foreground">Column Name</dt>
        <dd className="truncate font-mono">{entity.table}.{entity.column}</dd>
        <dt className="text-muted-foreground">Domain</dt>
        <dd>{entity.group}</dd>
        <dt className="text-muted-foreground">Total Distinct Values</dt>
        <dd className="tabular-nums">{formatNumber(entity.distinctValues)}</dd>
        <dt className="text-muted-foreground">Data Type</dt>
        <dd>{entity.dataType ?? "—"}</dd>
        <dt className="text-muted-foreground">Last Updated</dt>
        <dd>{formatDate(entity.lastUpdated)}</dd>
        {entity.aiKnown ? (
          <>
            <dt className="text-muted-foreground">AI dictionary cap</dt>
            <dd>Top {entity.maxValues} by volume, plus values found on demand</dd>
          </>
        ) : null}
      </dl>
      {entity.error ? (
        <p className="mt-2 text-xs text-warning-foreground dark:text-warning">
          The last refresh could not read this column; showing the previous values.
        </p>
      ) : null}
      <div className="relative mt-3">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={valueQuery}
          onChange={(event) => setValueQuery(event.target.value)}
          placeholder={`Search ${entity.valuesTotal} values or aliases`}
          className="h-8 pl-8 text-xs"
          aria-label="Search values"
        />
      </div>
      <ul className="mt-2 max-h-[28rem] space-y-1.5 overflow-y-auto pr-1">
        {values.length === 0 ? (
          <li className="py-4 text-center text-xs text-muted-foreground">
            {entity.valuesTotal ? "No values match." : "Values appear after the first catalog refresh."}
          </li>
        ) : null}
        {values.map((value) => (
          <li
            key={value.value}
            className={cn(
              "rounded-lg border px-3 py-2 text-xs",
              value.isNew ? "border-accent/40 bg-accent/5" : "border-border/50",
              !value.active && "opacity-60",
            )}
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-medium text-foreground">{value.value}</span>
              {value.isNew ? <StatusPill tone="ai" label="NEW" /> : null}
              {!value.active ? <StatusPill tone="neutral" label="No longer in data" /> : null}
              <span className="ml-auto tabular-nums text-muted-foreground">
                {formatNumber(value.frequency)} rows
              </span>
              <StatusPill tone={READINESS_TONE[value.readiness]} label={READINESS_LABEL[value.readiness]} />
            </div>
            {value.readinessNotes.length ? (
              <p className="mt-1 text-muted-foreground">{value.readinessNotes.join(" · ")}</p>
            ) : null}
            <div className="mt-1 grid gap-0.5 text-muted-foreground">
              <p>
                <span className="text-foreground/80">Canonical name:</span> {value.value}
                {value.aliases.length ? (
                  <>
                    {" · "}
                    <span className="text-foreground/80">Known aliases:</span>{" "}
                    {value.aliases.join(", ")}
                  </>
                ) : null}
              </p>
              {value.resolutionRule.length ? (
                <p className="flex items-start gap-1">
                  <Wand2 className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
                  <span>
                    <span className="text-foreground/80">AI resolution rule:</span>{" "}
                    {value.resolutionRule.join(" → ")}
                  </span>
                </p>
              ) : null}
              {value.isNew ? (
                <p>
                  First seen {formatDate(value.firstSeenAt)} · Detected in load{" "}
                  <span className="font-mono">{value.detectedInLoad}</span>
                </p>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
      {entity.valuesTotal > entity.values.length ? (
        <p className="mt-2 text-[11px] text-muted-foreground">
          Showing {entity.values.length} of {entity.valuesTotal} values (new values first).
        </p>
      ) : null}
    </div>
  );
}

function ChangeMonitor({
  title,
  description,
  icon: Icon,
  changes,
  empty,
}: {
  title: string;
  description: string;
  icon: typeof Activity;
  changes: CatalogChange[];
  empty: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Icon className="size-4" aria-hidden="true" />
          {title}
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {changes.length === 0 ? (
          <EmptyState title={empty} className="py-6" />
        ) : (
          <ul className="max-h-[32rem] space-y-2 overflow-y-auto pr-1">
            {changes.map((change) => (
              <ChangeItem key={change.id} change={change} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function ChangeItem({ change }: { change: CatalogChange }) {
  const detail = change.detail;
  const affected = Array.isArray(detail.affectedObjects) ? (detail.affectedObjects as string[]) : [];
  const suggested = detail.suggestedDomain as { group?: string; role?: string } | undefined;
  return (
    <li className="rounded-lg border border-border/50 p-3 text-xs">
      <div className="flex flex-wrap items-center gap-1.5">
        <StatusPill
          tone={SEVERITY_TONE[change.severity] ?? "neutral"}
          label={CHANGE_LABEL[change.kind] ?? change.kind}
        />
        {change.kind === "possible_rename" && change.confidence !== null ? (
          <StatusPill tone="info" label={`${Math.round(change.confidence * 100)}% confidence`} />
        ) : null}
        <span className="ml-auto text-muted-foreground">{formatDate(change.detectedAt)}</span>
      </div>
      <p className="mt-1.5 text-sm text-foreground">{change.summary}</p>
      <div className="mt-1 space-y-0.5 text-muted-foreground">
        {suggested ? (
          <p>
            Suggested domain: {suggested.group ?? "Unassigned"} ({suggested.role ?? "attribute"})
          </p>
        ) : null}
        {typeof detail.lastSeen === "string" && detail.lastSeen ? (
          <p>Last seen {formatDate(detail.lastSeen)}</p>
        ) : null}
        {affected.length ? <p>Affected objects: {affected.slice(0, 6).join(", ")}</p> : null}
        {change.kind === "possible_rename" ? (
          <p>Not applied automatically — confirm and update the semantic model to accept it.</p>
        ) : null}
      </div>
      {Object.keys(change.impact).length ? (
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 border-t border-border/40 pt-2">
          <span className="font-medium text-foreground">AI impact:</span>
          {Object.entries(change.impact).map(([area, level]) => (
            <span key={area}>
              {area}: <span className={cn("font-medium", IMPACT_TONE[level] ?? "text-foreground")}>{level}</span>
            </span>
          ))}
        </div>
      ) : null}
    </li>
  );
}
