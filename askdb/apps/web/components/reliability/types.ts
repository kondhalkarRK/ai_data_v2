/** Mirrors `DataReliabilityResponse` (apps/api/app/schemas/reliability.py). */

export type DimensionKey =
  | "accuracy"
  | "completeness"
  | "consistency"
  | "timeliness"
  | "validity"
  | "uniqueness";
export type Severity = "critical" | "high" | "medium" | "low";
export type RuleStatus = "passing" | "failing" | "no_data" | "error" | "disabled";
export type Tone = "positive" | "info" | "warning" | "risk";
export type Band = "excellent" | "good" | "fair" | "risk" | "unknown";

export interface ReliabilityHero {
  available: boolean;
  unavailableReason: string | null;
  score: number | null;
  band: Band;
  bandLabel: string;
  delta7d: number | null;
  rulesTotal: number;
  rulesActive: number;
  rulesPassing: number;
  rulesFailing: number;
  rulesErrored: number;
  criticalIssues: number;
  datasetsMonitored: number;
  recordsChecked: number;
}

export interface TrustSummary {
  headline: string;
  statements: Array<{ tone: Tone; text: string }>;
}

export interface DimensionCard {
  key: DimensionKey;
  label: string;
  question: string;
  weight: number;
  effectiveWeight: number | null;
  score: number | null;
  band: Band;
  rules: number;
  passing: number;
  failing: number;
  errored: number;
  delta7d: number | null;
  sparkline: Array<number | null>;
  lastFailureAt: string | null;
  topIssue: string | null;
}

export interface TrendPoint {
  date: string;
  score: number | null;
  dimensions: Partial<Record<DimensionKey, number | null>>;
  measured: number | null;
}

export interface TrendEvent {
  date: string;
  kind: "drop" | "incident" | "drift";
  title: string;
  detail: string;
  ruleIds: string[];
}

export interface TrustTrend {
  points: TrendPoint[];
  events: TrendEvent[];
  basis: string;
  measuredRuns: number;
  endDate: string | null;
}

export interface RuleRow {
  id: string;
  name: string;
  description: string;
  dimension: DimensionKey;
  dataset: string;
  datasetLabel: string;
  severity: Severity;
  kind: string;
  threshold: number;
  unit: string;
  status: RuleStatus;
  passRate: number | null;
  score: number | null;
  total: number;
  failed: number;
  observed: string;
  valueAtRisk: number | null;
  lastRunAt: string | null;
  lastFailureAt: string | null;
  failingSince: string | null;
  owner: string;
  tags: string[];
  enabled: boolean;
  custom: boolean;
  impact: string | null;
  assets: string[];
  samples: string[];
  sparkline: number[];
  durationMs: number;
}

export interface AlertItem {
  id: string;
  ruleId: string;
  severity: Severity;
  kind: "rule" | "error";
  title: string;
  dataset: string;
  datasetLabel: string;
  dimension: DimensionKey;
  failedRecords: number;
  unit: string;
  impact: string;
  valueAtRisk: number | null;
  detectedAt: string | null;
  assets: string[];
}

export interface BusinessImpact {
  headline: string;
  recordsAffected: number;
  valueAtRisk: number | null;
  items: Array<{ asset: string; severity: Severity; statements: string[]; ruleIds: string[] }>;
}

export interface DatasetTrust {
  name: string;
  label: string;
  kind: string;
  domain: string;
  score: number | null;
  band: Band;
  rank: number | null;
  rules: number;
  passing: number;
  failing: number;
  rows: number | null;
  lastRefresh: string | null;
  topIssue: string | null;
  assets: string[];
}

export interface FreshnessRow {
  dataset: string;
  label: string;
  cadence: string;
  ruleId: string | null;
  lastRefresh: string | null;
  expectedBy: string | null;
  slaHours: number | null;
  lagHours: number | null;
  delayHours: number | null;
  status: "on_time" | "delayed" | "stale" | "unknown";
}

export interface DriftEvent {
  id: string;
  kind: string;
  severity: string;
  summary: string;
  table: string | null;
  column: string | null;
  detectedAt: string | null;
  impact: Record<string, string>;
}

export interface SchemaDrift {
  status: "stable" | "drift" | "not_checked" | "unavailable";
  label: string;
  events: DriftEvent[];
}

export interface EntityChanges {
  available: boolean;
  total: number;
  lastRefreshAt: string | null;
  groups: Array<{
    key: string;
    label: string;
    count: number;
    values: Array<{ value: string; domain: string; firstSeenAt: string | null }>;
  }>;
}

export interface Methodology {
  formula: string;
  dimensions: Array<{
    key: DimensionKey;
    label: string;
    weight: number;
    effectiveWeight: number | null;
    measured: boolean;
  }>;
  severityWeights: Record<Severity, number>;
  bands: Array<{ key: Band; label: string; min: number }>;
  notes: string[];
}

export interface InsightItem {
  id: string;
  tone: Tone;
  title: string;
  detail: string;
  ruleIds: string[];
  dimension: DimensionKey | null;
  dataset: string | null;
}

export interface MonitorCatalog {
  datasets: Array<{
    name: string;
    label: string;
    columns: Array<{ name: string; label: string; type: string }>;
  }>;
  owners: string[];
  tags: string[];
}

export interface Capability {
  key: string;
  label: string;
  status: "live" | "next" | "planned";
  detail: string;
}

export interface DataReliability {
  industry: string;
  computedAt: string;
  dataAsOf: string | null;
  storage: "database" | "memory";
  runDurationMs: number;
  hero: ReliabilityHero;
  summary: TrustSummary;
  dimensions: DimensionCard[];
  trend: TrustTrend;
  rules: RuleRow[];
  alerts: AlertItem[];
  impact: BusinessImpact;
  datasets: DatasetTrust[];
  freshness: FreshnessRow[];
  schemaDrift: SchemaDrift;
  entities: EntityChanges;
  methodology: Methodology;
  insights: InsightItem[];
  catalog: MonitorCatalog;
  capabilities: Capability[];
}

export interface MonitorMutationResult {
  ok: boolean;
  updated: string[];
  skipped: string[];
  storage: "database" | "memory";
  message: string | null;
}

export type BulkAction =
  | "assign_dimension"
  | "assign_owner"
  | "add_tags"
  | "remove_tags"
  | "set_severity"
  | "enable"
  | "disable";

/** Cross-filter shared by every panel. */
export interface TrustFilters {
  dimension?: DimensionKey;
  dataset?: string;
  severity?: Severity;
  status?: RuleStatus;
}

export type Drilldown =
  | { kind: "dimension"; key: DimensionKey }
  | { kind: "rule"; id: string }
  | { kind: "dataset"; name: string };
