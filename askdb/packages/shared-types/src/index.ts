/**
 * Contract types shared between the FastAPI backend and the Next.js frontend.
 *
 * These mirror the Pydantic schemas in `apps/api/app/schemas`. When a schema changes,
 * change it here in the same commit — this package is the single place the two sides
 * agree on shape.
 */

// --- primitives -------------------------------------------------------------

export type Industry = "automotive" | "insurance";
/** Two roles only: an admin can do everything a user can, plus the Admin Center. */
export type Role = "admin" | "user";

export const INDUSTRIES: readonly Industry[] = ["automotive", "insurance"] as const;
export const ROLES: readonly Role[] = ["admin", "user"] as const;

/** Role precedence, used for client-side affordance hiding. */
const ROLE_RANK: Record<Role, number> = { user: 0, admin: 1 };

export function roleAtLeast(actual: Role, required: Role): boolean {
  return ROLE_RANK[actual] >= ROLE_RANK[required];
}

// --- errors -----------------------------------------------------------------

export interface ApiErrorBody {
  code: string;
  message: string;
  requestId: string;
  details: Record<string, unknown>;
}

export interface ApiErrorResponse {
  error: ApiErrorBody;
}

// --- auth -------------------------------------------------------------------

export interface RegionAccess {
  unrestricted: boolean;
  zones: string[];
  hideRegionFilter: boolean;
}

/** Safe feature flags from GET /auth/me (backend-sourced). */
export interface UserCapabilities {
  ragEnabled: boolean;
}

export interface UserProfile {
  id: string;
  username: string;
  email: string;
  fullName: string;
  role: Role;
  defaultIndustry: Industry;
  isActive: boolean;
  mustChangePassword: boolean;
  /** `null` means no weekly limit. */
  weeklyTokenLimit: number | null;
  weeklyCallLimit: number | null;
  lastLoginAt: string | null;
  createdAt: string;
  regionAccess: RegionAccess;
  capabilities?: UserCapabilities;
}

/** `GET /auth/me/usage` — the caller's AI usage since Monday 00:00 UTC. */
export interface WeeklyUsage {
  tokenLimit: number | null;
  tokensUsed: number;
  tokensRemaining: number | null;
  callLimit: number | null;
  callsUsed: number;
  callsRemaining: number | null;
  unlimited: boolean;
  weekStart: string;
  resetsAt: string;
}

export interface SessionResponse {
  user: UserProfile;
  csrfToken: string;
  accessExpiresAt: string;
}

export interface LoginRequest {
  username: string;
  password: string;
  rememberMe: boolean;
}

// --- system -----------------------------------------------------------------

export type DependencyStatus = "ok" | "degraded" | "unavailable" | "not_configured";

export interface DependencyReport {
  name: string;
  status: DependencyStatus;
  detail: string;
  latencyMs: number | null;
}

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  environment: string;
  time: string;
}

export interface ReadinessResponse {
  status: "ready" | "degraded" | "not_ready";
  checkedAt: string;
  dependencies: DependencyReport[];
}

export interface IndustrySummary {
  id: Industry;
  label: string;
  description: string;
  icon: string;
  databaseAvailable: boolean;
  semanticPackLoaded: boolean;
  isDefault: boolean;
}

export interface IndustryListResponse {
  industries: IndustrySummary[];
  active: Industry;
}

// --- pagination -------------------------------------------------------------

export interface PageMeta {
  total: number | null;
  limit: number;
  nextCursor: string | null;
  hasMore: boolean;
}

export interface Page<T> {
  items: T[];
  meta: PageMeta;
}

// --- ontology (Phase 2) -----------------------------------------------------

export type OntologyNodeKind = "domain" | "entity" | "table" | "measure" | "dimension";
export type OntologyEdgeKind = "relationship" | "reference" | "maps_to" | "dependency";

export interface OntologyColumn {
  name: string;
  displayName: string;
  type: string;
  role: string;
  references?: string;
  nullable?: boolean;
}

export interface OntologyNode {
  [key: string]: unknown;
  id: string;
  label: string;
  kind: OntologyNodeKind;
  domain: string;
  description?: string;
  physicalName?: string;
  tableType?: string;
  grain?: string;
  primaryKey?: string;
  synonyms: string[];
  tables: string[];
  columns: OntologyColumn[];
  relationships: string[];
  lineage: string[];
  degree: number;
  cluster: string;
  clusterColor: string;
  /** Client-only search/filter presentation; never required from the API. */
  dimmed?: boolean;
}

export interface OntologyEdge {
  id: string;
  source: string;
  target: string;
  kind: OntologyEdgeKind;
  label: string;
  fromColumn?: string;
  toColumn?: string;
  cardinality?: string;
}

export interface OntologyCluster {
  id: string;
  label: string;
  color: string;
}

/** The compiled snapshot shape required by spec section 11. */
export interface OntologySnapshot {
  nodes: OntologyNode[];
  edges: OntologyEdge[];
  clusters: OntologyCluster[];
  metadata: {
    industry: Industry;
    version: string;
    compiledAt: string;
    nodeCount: number;
    edgeCount: number;
    buildMs: number;
  };
}

export interface SemanticPackSummary {
  industry: Industry;
  label: string;
  description: string;
  version: string;
  domain: string;
  tableCount: number;
  relationshipCount: number;
  measureCount: number;
  dimensionCount: number;
  glossaryTermCount: number;
}

export interface SemanticColumn {
  displayName: string;
  type: string;
  role: string;
  references?: string;
  description?: string;
  nullable?: boolean;
}

export interface SemanticTable {
  type: "fact" | "dimension" | "bridge" | "table";
  physicalName: string;
  displayName: string;
  description?: string;
  grain?: string;
  primaryKey: string;
  columns: Record<string, SemanticColumn>;
}

export interface SemanticMeasure {
  displayName: string;
  expression: string;
  sourceTable?: string;
  sourceColumn?: string;
  description?: string;
  aggregation: string;
  format: string;
  synonyms: string[];
}

export interface SemanticDimension {
  displayName: string;
  sourceTable: string;
  sourceColumn?: string;
  attributes: string[];
  type?: string;
  displayExpression?: string;
  synonyms: string[];
}

export interface GlossaryTerm {
  definition: string;
  displayLabel?: string;
  synonyms: string[];
  category: string;
  mapsToMeasure?: string;
  mapsToDimension?: string;
  mapsToAttribute?: string;
  sqlExpression?: string;
  calculationRules: string[];
  disambiguation: string[];
  relatedTerms: string[];
  exampleQuestions: string[];
}

export interface SemanticValueDomain {
  table: string;
  column: string;
  label: string;
  maxValues: number;
  aliases: string[];
  valueAliases: Record<string, string[]>;
}

export interface SemanticPackResponse {
  summary: SemanticPackSummary;
  model: {
    version: string;
    domain: string;
    description: string;
    tables: Record<string, SemanticTable>;
    relationships: Array<{
      name: string;
      fromTable: string;
      fromColumn: string;
      toTable: string;
      toColumn: string;
      type: string;
      displayName?: string;
      autoJoin: boolean;
    }>;
    measures: Record<string, SemanticMeasure>;
    dimensions: Record<string, SemanticDimension>;
    businessEntities: Array<{ name: string; table: string; description?: string }>;
    hierarchies?: Record<string, string[]>;
    domainRules?: Record<string, string[]>;
    valueDomains?: Record<string, SemanticValueDomain>;
  };
  glossary: {
    version: string;
    domain: string;
    terms: Record<string, GlossaryTerm>;
    domainRules?: Record<string, string[]>;
  };
}

// --- data preview / quality (Phase 3) --------------------------------------

export interface PreviewTableSummary {
  name: string;
  displayName: string;
  physicalName: string;
  tableType: string;
  primaryKey: string;
  grain?: string;
  estimatedRows: number | null;
  columnCount: number;
}

export interface PreviewColumn {
  name: string;
  displayName: string;
  type: string;
  role: string;
}

export interface PreviewRow {
  values: Record<string, unknown>;
}

export interface PreviewPage {
  table: string;
  physicalName: string;
  columns: PreviewColumn[];
  items: PreviewRow[];
  meta: PageMeta;
}

export interface DataQualityReport {
  table: string;
  physicalName: string;
  sampleRows: number;
  healthScore: number;
  totalRows: number;
  totalCols: number;
  totalNullPct: number;
  duplicateCount: number;
  duplicatePct: number;
  nullSummary: Record<string, { count: number; pct: number }>;
  outliers: Record<string, unknown>;
  typeIssues: Array<Record<string, unknown>>;
  cardinalityFlags: Array<Record<string, unknown>>;
  dateGaps: string[];
  dateCol: string | null;
  computedIn: string;
}

// --- analytics builder ------------------------------------------------------

export type AnalyticsVizKind =
  | "table"
  | "bar"
  | "line"
  | "area"
  | "pie"
  | "donut"
  | "scatter"
  | "kpi"
  | "heatmap"
  | "treemap"
  | "auto";

export type AnalyticsAnalysisKind =
  | "basic"
  | "trend"
  | "comparison"
  | "top_n"
  | "bottom_n"
  | "top_n_per_group"
  | "ranking"
  | "contribution"
  | "running_total"
  | "moving_average"
  | "period_growth"
  | "yoy_growth"
  | "growth_contribution"
  | "actual_vs_target"
  | "above_average"
  /** Saved before the redesign: Standard and Above average. */
  | "breakdown"
  | "variance";

export type AnalyticsRankMethod = "rank" | "dense_rank" | "row_number";

export interface AnalyticsFilterSpec {
  domain: string;
  values: string[];
  operator?: string;
}

export interface AnalyticsSpec {
  metrics: string[];
  dimensions: string[];
  filters: AnalyticsFilterSpec[];
  analysis: AnalyticsAnalysisKind;
  limit: number;
  orderDirection: "asc" | "desc";
  timeGrain?: string | null;
  viz: AnalyticsVizKind;
  datePreset?: string | null;
  dateFrom?: string | null;
  dateTo?: string | null;
  rankMethod?: AnalyticsRankMethod;
  window?: number;
}

export interface AnalyticsNarration {
  summary: string;
  highlights: string[];
  insight?: string | null;
  focus?: string | null;
}

export interface AnalyticsRunMeta {
  path?: string;
  analysis?: AnalyticsAnalysisKind;
  metric?: string | null;
  metricFormat?: string;
  valueColumn?: string;
  dimensions?: string[];
  rowCount?: number;
  truncated?: boolean;
  dataAsOf?: string | null;
  dateLabel?: string | null;
  partialPeriod?: string | null;
  notes?: string[];
  warnings?: string[];
  [key: string]: unknown;
}

export interface AnalyticsRunResponse {
  title: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  sql: string;
  chart: {
    type: string;
    x: string;
    y: string;
    series?: string[];
    points: Array<Record<string, unknown>>;
    note?: string | null;
  } | null;
  recommendedViz: AnalyticsVizKind;
  insights?: { executive: string; analyst: string; narration?: AnalyticsNarration | null } | null;
  meta: AnalyticsRunMeta;
}

export type AnalyticsFixAction =
  | "add_dimension"
  | "remove_dimension"
  | "set_analysis"
  | "set_metric"
  | "open_filters"
  | "remove_filter"
  | "clear_date";

export interface AnalyticsFix {
  label: string;
  action: AnalyticsFixAction;
  value?: string | null;
}

export interface AnalyticsIssue {
  code: string;
  severity: "error" | "warning";
  message: string;
  fixes: AnalyticsFix[];
}

export interface AnalyticsOption {
  id: string;
  label: string;
  available: boolean;
  reason?: string | null;
}

export interface AnalyticsSuggestion {
  label: string;
  description: string;
  spec: AnalyticsSpec;
}

export interface AnalyticsInspection {
  valid: boolean;
  issues: AnalyticsIssue[];
  analyses: AnalyticsOption[];
  metrics: AnalyticsOption[];
  dimensions: AnalyticsOption[];
  suggestions: AnalyticsSuggestion[];
}

export interface AnalyticsCapabilities {
  metrics: Array<{
    id: string;
    label: string;
    description?: string | null;
    format: string;
    additive: boolean;
    supported: boolean;
    reason?: string | null;
  }>;
  dimensions: Array<{ id: string; label: string; group: string; time: boolean; filterDomain?: string | null }>;
  analyses: Array<{ id: AnalyticsAnalysisKind; label: string; group: string; description: string; requirement: string }>;
  filterDomains: Array<{ id: string; label: string }>;
  datePresets: Array<{ id: string; label: string }>;
  dataAsOf?: string | null;
}

export interface AnalyticsAssistResponse {
  spec: AnalyticsSpec;
  explanation: string;
  glossaryHits: string[];
}

export interface FilterValueItem {
  value: string;
  frequency: number;
  label?: string | null;
}

export interface FilterValuesResponse {
  domain: string;
  label: string;
  values: FilterValueItem[];
}

export interface SavedAnalysis {
  id: string;
  title: string;
  industry: string;
  spec: AnalyticsSpec | Record<string, unknown>;
  viz: string;
  sqlSnapshot?: string | null;
  createdAt: string;
  updatedAt: string;
}

/** Server-issued, user/scope-bound facts for the augmented executive dashboard. */
export interface DashboardContext {
  resultId: string;
  industry: Industry;
  semanticRevision: string;
  periodLabel: string;
  compareLabel: string;
  start: string | null;
  end: string | null;
  priorStart: string | null;
  priorEnd: string | null;
  filters: Record<string, string>;
  dataAsOf: string;
  computedAt: string;
}

export interface DashboardMetric {
  id: string;
  label: string;
  format: "currency" | "integer" | "percent";
  current: number | null;
  prior: number | null;
  definition: string;
  dimensions: string[];
  supported: boolean;
  unavailableReason: string | null;
}

export interface DashboardAugmentation {
  snapshotToken: string;
  context: DashboardContext;
  metrics: DashboardMetric[];
  highlights: Array<{ metricId: string; title: string; body: string; tone: "positive" | "negative" | "neutral" }>;
  caveats: string[];
  performance: { elapsedMs: number; queryCount: number; warehouseMs: number; cacheHit: boolean };
}

export interface DashboardContributor {
  label: string;
  current: number;
  prior: number;
  change: number;
  filters: Record<string, string>;
  residual: boolean;
}

export interface DashboardExplanation {
  context: DashboardContext;
  metric: DashboardMetric;
  dimension: string;
  narrative: string;
  contributors: DashboardContributor[];
  caveats: string[];
  sourceTables: string[];
  sql: string | null;
  sqlParameters: Record<string, unknown>;
  priorSqlParameters: Record<string, unknown>;
  reconciled: boolean;
  evidenceChanged: boolean;
  evidenceComputedAt?: string | null;
  queryCount: number;
  elapsedMs: number;
  conversationId: string | null;
  suggestedQuestions: string[];
}
// Automotive AskWiz Auto boards; Custom analyses retain their existing contracts.
export interface AskWizChart {
  id: string; title: string;
  metric: "revenue" | "units_sold" | "orders" | "average_selling_price" | "active_salespeople";
  dimension: "day" | "month" | "make" | "model" | "region" | "state" | "city" | "dealer" | "car_type" | "engine_type";
  viz: "bar" | "line" | "area" | "pie" | "table";
}
export interface AskWizDefinition {
  version: 1; recipe: string; start: string; end: string; priorStart: string; priorEnd: string;
  timezone: string; filters: Record<string, string[]>; charts: AskWizChart[];
}
export interface AskWizBoard {
  id: string; title: string; revision: number; saved: boolean; definition: AskWizDefinition;
  canUndo: boolean; message: string; llmCalls: number; tokens: number;
}
export interface AskWizChartResult {
  chartId: string; result: AnalyticsRunResponse | null; error: string | null; cacheHit: boolean;
}
export interface AskWizResults {
  boardId: string; revision: number; charts: AskWizChartResult[]; kpis: AskWizChartResult[];
  elapsedMs: number; queryCount: number; cacheHits: number; computedAt: string;
}
export interface AskWizNarration {
  revision: number; paragraphs: string[]; aiUsed: boolean; llmCalls: number; tokens: number;
  limitation: string | null;
}

/** Unified automotive analytics: business definitions, never executable SQL. */
export interface AnalyticsWorkspacePanel {
  id: string;
  title: string;
  kind: "kpi" | "chart" | "table";
  spec: AnalyticsSpec;
  rationale: string;
  daily: boolean;
}
export interface AnalyticsWorkspacePlan {
  answerKind: "clarification" | "single_value" | "analysis" | "report" | "dashboard";
  title: string;
  panels: AnalyticsWorkspacePanel[];
  clarification: string | null;
  assumptions: string[];
}
export interface SavedAnalyticsWorkspace {
  id: string;
  revision: number;
  plan: AnalyticsWorkspacePlan;
  warning: string | null;
  messages: Array<{ question: string; answer: string }>;
}
// AskBI v2: durable report conversation, independent of AI Chat.
export type BiPanel = AnalyticsWorkspacePanel & {
  calculation: "z_score" | "index_to_average" | null;
  grain: "day" | "week" | "month" | "quarter" | "year" | null;
  section: string;
  dateIntent: string | null;
};
export interface BiPlan {
  version: 2;
  title: string;
  answerKind: "single_value" | "analysis" | "report" | "dashboard";
  panels: BiPanel[];
  assumptions: string[];
  reportFilter?: BiReportFilter | null;
}
export interface BiReportFilter {
  period: "year" | "month" | "week";
  year: number;
  month?: number | null;
  weekStart?: string | null;
  make?: string | null;
  region?: string | null;
}
export interface BiTurn {
  id: string;
  question: string;
  answer: string;
  kind: "answer" | "clarification" | "unsupported" | "error" | "edit";
  code: string | null;
  changedPanelIds: string[];
}
export interface BiUsage {
  validationQueries?: number;
  llmCalls: number;
  tokens: number;
  usageComplete: boolean;
  elapsedMs: number;
}
export interface BiReport {
  id: string;
  revision: number;
  title: string;
  saved: boolean;
  warning: string | null;
  state: {
    plan: BiPlan | null;
    previous: BiPlan | null;
    pending: { question: string; clarification: string; selectedPanelId: string | null } | null;
    turns: BiTurn[];
    usage: BiUsage;
  };
}
