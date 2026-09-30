export type Readiness =
  | "ai_ready"
  | "needs_review"
  | "missing_synonyms"
  | "low_confidence"
  | "not_refreshed";

export type RefreshScope = "catalog" | "values" | "semantic_cache";

export interface CatalogRefreshInfo {
  id: string;
  scope: RefreshScope;
  trigger: "startup" | "data_load" | "manual" | "unknown_entity";
  status: "running" | "completed" | "failed";
  version: number;
  loadId: string;
  startedAt: string | null;
  finishedAt: string | null;
  rowsProcessed: number | null;
  newValueCount: number;
  changeCount: number;
  error: string | null;
}

export interface CatalogSummary {
  industry: string;
  lastRefresh: CatalogRefreshInfo | null;
  lastCompleted: CatalogRefreshInfo | null;
  catalogVersion: number;
  rowsProcessed: number | null;
  lastLoadId: string | null;
  totalEntities: number;
  totalValues: number;
  newValues: number;
  schemaDrift: {
    status: "not_checked" | "stable" | "changes_detected" | "action_required";
    label: string;
    count: number;
  };
  aiCoverage: number | null;
  entityReadiness: Partial<Record<Readiness, number>>;
  available: boolean;
  unavailableReason: "migration_pending" | "database_unreachable" | null;
}

export interface EntityRow {
  key: string;
  label: string;
  group: string;
  table: string;
  column: string;
  dataType: string | null;
  distinctValues: number;
  newValues: number;
  lastUpdated: string | null;
  aiKnown: boolean;
  readiness: Readiness;
  readinessCounts: Partial<Record<Readiness, number>>;
  aliases: string[];
  sampleValues: string[];
  newValueNames: string[];
  error: string | null;
}

export interface EntityValue {
  value: string;
  frequency: number;
  isNew: boolean;
  active: boolean;
  firstSeenAt: string | null;
  detectedInLoad: string | null;
  readiness: Readiness;
  readinessNotes: string[];
  aliases: string[];
  resolutionRule: string[];
}

export interface EntityDetail extends EntityRow {
  maxValues: number;
  values: EntityValue[];
  valuesTotal: number;
}

export interface CatalogChange {
  id: string;
  kind: string;
  severity: "high" | "medium" | "low";
  summary: string;
  table: string | null;
  column: string | null;
  domainKey: string | null;
  confidence: number | null;
  detail: Record<string, unknown>;
  impact: Record<string, string>;
  detectedAt: string | null;
}

export interface CatalogRefreshResult {
  refresh: CatalogRefreshInfo;
  summary: CatalogSummary;
}
