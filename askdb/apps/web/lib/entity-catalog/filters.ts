import type { CatalogChange, EntityRow, Readiness } from "@/lib/entity-catalog/types";

export const GROUP_FILTERS = [
  "Vehicle",
  "Sales",
  "Customer",
  "Dealer",
  "Geography",
  "Insurance",
] as const;

export const STATE_FILTERS = ["new_values", "schema_changes", "needs_review"] as const;

export type CatalogFilter = (typeof GROUP_FILTERS)[number] | (typeof STATE_FILTERS)[number];

export const FILTER_LABEL: Record<CatalogFilter, string> = {
  Vehicle: "Vehicle",
  Sales: "Sales",
  Customer: "Customer",
  Dealer: "Dealer",
  Geography: "Geography",
  Insurance: "Insurance",
  new_values: "New Values",
  schema_changes: "Schema Changes",
  needs_review: "Needs Review",
};

export const READINESS_LABEL: Record<Readiness, string> = {
  ai_ready: "AI Ready",
  needs_review: "Needs Review",
  missing_synonyms: "Missing Synonyms",
  low_confidence: "Low Confidence",
};

export const SCHEMA_KINDS = new Set([
  "new_column",
  "removed_column",
  "type_change",
  "possible_rename",
  "missing_in_database",
]);

export const CHANGE_LABEL: Record<string, string> = {
  new_column: "New column",
  removed_column: "Removed column",
  type_change: "Type change detected",
  possible_rename: "Possible column rename",
  missing_in_database: "Missing in warehouse",
  new_values: "New values",
  distinct_growth: "Value growth",
  distinct_reduction: "Value reduction",
};

function normalize(text: string): string {
  return text.toLowerCase().replace(/\s+/g, " ").trim();
}

/** Tables touched by a schema change, used by the "Schema Changes" filter. */
export function tablesWithSchemaChanges(changes: CatalogChange[]): Set<string> {
  return new Set(
    changes.filter((c) => SCHEMA_KINDS.has(c.kind) && c.table).map((c) => c.table as string),
  );
}

/** Where a query matched, so the grid can say "matched alias 'maruti'". */
export function matchReason(row: EntityRow, query: string): string | null {
  const q = normalize(query);
  if (!q) return null;
  if (
    [row.label, row.key, row.column, row.table, row.group].some((text) =>
      normalize(text).includes(q),
    )
  ) {
    return "entity";
  }
  const value = row.sampleValues.find((v) => normalize(v).includes(q));
  if (value) return `value “${value}”`;
  const alias = row.aliases.find((a) => normalize(a).includes(q));
  if (alias) return `alias “${alias}”`;
  const fresh = row.newValueNames.find((v) => normalize(v).includes(q));
  if (fresh) return `new value “${fresh}”`;
  return null;
}

export function filterEntities(
  rows: EntityRow[],
  {
    query,
    filters,
    schemaTables,
  }: { query: string; filters: Set<CatalogFilter>; schemaTables: Set<string> },
): EntityRow[] {
  const groups = GROUP_FILTERS.filter((g) => filters.has(g));
  return rows.filter((row) => {
    if (groups.length && !groups.includes(row.group as (typeof GROUP_FILTERS)[number])) {
      return false;
    }
    if (filters.has("new_values") && row.newValues === 0) return false;
    if (filters.has("needs_review") && row.readiness === "ai_ready") return false;
    if (filters.has("schema_changes") && !schemaTables.has(row.table)) return false;
    return query.trim() ? matchReason(row, query) !== null : true;
  });
}

export function coverageLabel(coverage: number | null): string {
  return coverage === null ? "—" : `${Math.round(coverage * 1000) / 10}%`;
}
