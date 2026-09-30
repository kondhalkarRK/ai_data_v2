/** Client-side chat response contract — mirrors SSE meta from the API. */

export type GroundedSource =
  | "Semantic Layer"
  | "Business Glossary"
  | "KPI Definition"
  | "Data Quality Check";

export type ValidationStatus = "passed" | "auto_repaired" | "failed" | "skipped";

export type ResponseTab = "table" | "chart" | "narration" | "sql";

export type InsightDepth = "executive" | "analyst";

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

export interface ResponseMeta {
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
  insights: { executive: string; analyst: string };
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
  id: string;
  role: "user" | "assistant";
  question?: string;
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
  failure?: FailurePayload;
  progress?: ProgressState | null;
  meta?: ResponseMeta;
  latencyMs?: number;
}
