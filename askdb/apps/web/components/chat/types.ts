/** Client-side chat response contract — mirrors SSE meta from the API. */
import type { ChatResponseRating } from "@nql/shared-types";

export type GroundedSource =
  | "Semantic Layer"
  | "Business Glossary"
  | "KPI Definition"
  | "LLM"
  | "Schema"
  | "Data Quality Check";

export interface LlmRuntimeMeta {
  invoked: boolean;
  provider: string;
  model: string;
  configuredProvider: string;
  configuredModel: string;
}

export type ValidationStatus = "passed" | "auto_repaired" | "failed" | "skipped";

export type ResponseTab = "table" | "chart" | "narration" | "sql";

export type InsightDepth = "executive" | "analyst";

/** Executive narration built from the result: each section is present only when relevant. */
export interface NarrationSections {
  summary: string;
  highlights: string[];
  insight: string | null;
  focus: string | null;
  context?: string;
  evidence?: string[];
}

export interface QueryTimings {
  llmGenerationMs: number;
  semanticLookupMs: number;
  sqlValidationMs: number;
  sqlAutoRepairMs?: number;
  executionMs: number;
  renderMs: number;
}

export interface ProgressStep {
  id: string;
  label: string;
}

export interface ProgressState {
  steps: ProgressStep[];
  current: string;
  currentLabel: string;
  completed: string[];
  slowWarning?: boolean;
  message?: string;
}

export interface FailurePayload {
  category?: string;
  title?: string;
  reason?: string;
  retryable?: boolean;
  message?: string;
  sql?: string;
}

export interface QueryMeta {
  tablesUsed: string[];
  metricsUsed: string[];
  dimensionsUsed: string[];
  joinPath: string[];
  filtersApplied: string[];
  dateRange: string | null;
}

/** How a word in the question was mapped to a canonical business value. */
export interface ResolvedEntity {
  text: string;
  canonical: string;
  domain: string;
  column: string;
  method: "exact" | "synonym" | "fuzzy" | "alias" | "glossary";
  confidence: number;
}

export interface StructuredPlan {
  intent: string;
  brand: string | string[] | null;
  metric: string;
  dimension: string | string[];
  filters: Array<{ column: string; operator: string; values: string[] }>;
  year: number | null;
  analysis: string;
  chart: string;
}

export interface QueryPlanTrace {
  rewritten?: string;
  intent?: string;
  metric?: string;
  formula?: string;
  joins?: string[];
  filters?: string[];
  dimensions?: string[];
  chartType?: string;
  resolved?: ResolvedEntity[];
  structured?: StructuredPlan;
}

export interface AnomalyMarker {
  index: number;
  x: unknown;
  y: number;
  zScore: number;
  direction: "spike" | "dip";
  label: string;
}

export interface SqlDiffLine {
  op: "add" | "del" | "ctx";
  text: string;
}

export interface ChatCitation {
  title: string;
  snippet: string;
  locator: string;
  untrusted?: boolean;
  confidence?: number;
  collection?: string;
}

export interface ChartPayload {
  type: string;
  x: string;
  y: string;
  /** Wide comparison results: one plotted series per column (mg_revenue, kia_revenue). */
  series?: string[];
  points: Array<Record<string, unknown>>;
  anomalies?: AnomalyMarker[];
}

export type ResultShape =
  | "empty"
  | "single_value"
  | "time_series"
  | "ranking"
  | "comparison"
  | "breakdown"
  | "table";

/**
 * Deterministic description of the executed result, built by the API from the returned rows
 * (same formatting as the narration). The New Chat UI renders only what is in here.
 */
export interface ResultProfile {
  shape: ResultShape;
  rowCount: number;
  labelColumns: string[];
  measures: Array<{
    column: string;
    label: string;
    kind: "currency" | "percent" | "number";
    scalePercent?: boolean;
  }>;
  preview: Array<{ label: string | null; values: Array<{ column: string; text: string | null }> }>;
  previewTruncated: boolean;
  chartSuitable: boolean;
  mayBeTruncated: boolean;
}

export interface ResponseMeta {
  analyticalExecution?: AnalyticalExecution;
  analyticalPlan?: AnalyticalPlanSnapshot;
  analyticalPresentation?: AnalyticalPresentation | null;
  analyticalAudit?: Record<string, unknown>;
  responseKind?: "conversation" | "definition" | "clarification" | "data" | "report" | "partial" | "unavailable" | "denied" | "empty" | "cancelled" | "failed";
  runId?: string;
  runUsage?: Record<string, number | boolean | string | string[] | null>;
  typedRequest?: { outcome: string; measures: Array<{ id: string }>; group_by: string[]; filters: unknown[]; period: unknown };
  limitations?: string[];
  resultProfile?: ResultProfile | null;
  groundedOn: GroundedSource[];
  ambiguityFlag: boolean;
  validationStatus: ValidationStatus;
  rowCount: number;
  executionTimeMs: number;
  sourceDatabase: string;
  dataAsOf: string | null;
  timings: QueryTimings;
  queryMeta: QueryMeta;
  queryPlan?: QueryPlanTrace;
  insights: { executive: string; analyst: string; narration?: NarrationSections };
  anomalies: AnomalyMarker[];
  alternateInterpretations: string[];
  dqFailed?: boolean;
  executionError?: string | null;
  autoRepaired?: boolean;
  cacheHit?: boolean;
  route?: "sql" | "knowledge" | "hybrid";
  routeReason?: string;
  confidence?: AnswerConfidence;
  decision?: RouteDecision;
  corrections?: Array<{ from: string; to: string }>;
  reinterpretedAs?: string | null;
  llmRuntime?: LlmRuntimeMeta;
}

export interface AnswerConfidence {
  level: "high" | "medium" | "needs_clarification";
  label: string;
  score: number;
  reasons: string[];
}

export interface RouteDecision {
  path: "semantic" | "llm_reasoning" | "clarify";
  label: string;
  complexity: "simple" | "complex";
  reason: string;
  llmAvailable: boolean;
  governedFallback: boolean;
  answeredBy?: "semantic" | "llm";
}

export interface ChatMessage {
  analysisProgress?: AnalyticalProgress | null;
  report?: ChatReportPreview;
  complete?: boolean;
  ratingDisabled?: boolean;
  rating?: ResponseRating | null;
  id: string;
  role: "user" | "assistant";
  question?: string;
  documentsEnabled?: boolean;
  historyId?: string;
  sql?: string;
  priorSql?: string;
  sqlDiff?: SqlDiffLine[] | null;
  rows?: Array<Record<string, unknown>>;
  columns?: string[];
  chart?: ChartPayload;
  narrative?: string;
  path?: string;
  clarification?: string;
  clarificationTitle?: string;
  /** clarify | unsupported | unresolved | recovery */
  clarificationKind?: string;
  options?: string[];
  followups?: string[];
  citations?: ChatCitation[];
  route?: string;
  cancelled?: boolean;
  error?: string;
  /** Set when the weekly AI quota blocked the question; shown verbatim. */
  quotaNotice?: string;
  failure?: FailurePayload;
  progress?: ProgressState | null;
  meta?: ResponseMeta;
  latencyMs?: number;
}

export interface AnalyticalProgress {
  version: 1;
  planId: string;
  phase: "running" | "checking";
  total: number;
  completed: number;
  message: string;
  steps: Array<{ id: string; label: string; status: string }>;
}

export interface AnalyticalColumn {
  key: string;
  label: string;
  kind: "currency" | "percent" | "number" | "date" | "text";
  role?: string;
  semanticId?: string;
}

export interface AnalyticalStepView {
  id: string;
  title: string;
  operation: string;
  dependsOn: string[];
  status: string;
  verified: boolean;
  completenessVerified?: boolean | null;
  summary: string;
  columns: AnalyticalColumn[];
  displayedRows: number;
  totalGroups: number;
  selectedGroups: number;
  notes: string[];
  searchPeriod?: { label: string; start: string | null; endExclusive: string | null };
  comparisonPeriods: Array<{ currentStart: string; currentEnd: string; baselineStart: string; baselineEnd: string }>;
  baseline?: { kind: string; origin: string } | null;
  filters?: Array<{ field: string; label: string; operator: string; values: string[] }>;
}

export interface AnalyticalPresentation {
  version: 1;
  status: string;
  summary: string;
  scope: string[];
  steps: AnalyticalStepView[];
  unanswered: Array<{ id: string; reason: string; status: string }>;
  notes: string[];
  checks: Array<{ passed: boolean; measure?: string; headlineStep?: string; contributorStep?: string }>;
  legacy?: boolean;
}

export interface AnalyticalExecution {
  status: string;
  message: string;
  scope_labels?: string[];
  steps: Array<{ id: string; status: string; columns: string[]; rows: Array<Record<string, unknown>>;
    verified: boolean; completeness_verified?: boolean | null; total_groups: number;
    selected_groups?: number; notes: string[] }>;
}

export interface AnalyticalPlanSnapshot {
  steps: Array<{ id: string; label: string; operation: string; depends_on: string[];
    outputs: Array<{ name: string; role: string; semantic_id: string; value_type: string }> }>;
}

export type ResponseRating = ChatResponseRating;

export interface ChatReportPreview {
  reportId: string; revision: number; partial: boolean; briefing: string;
  panels: Array<{id: string; title?: string; kind?: string; status: string; result?: {result: {sql?: string; columns: string[]; rows: Array<Record<string, unknown>>; meta?: Record<string, unknown>}}}>;
}
