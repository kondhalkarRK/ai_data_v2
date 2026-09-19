/**
 * Contract types shared between the FastAPI backend and the Next.js frontend.
 *
 * These mirror the Pydantic schemas in `apps/api/app/schemas`. When a schema changes,
 * change it here in the same commit — this package is the single place the two sides
 * agree on shape.
 */

// --- primitives -------------------------------------------------------------

export type Industry = "automotive" | "insurance";
export type Role = "admin" | "analyst" | "viewer";

export const INDUSTRIES: readonly Industry[] = ["automotive", "insurance"] as const;
export const ROLES: readonly Role[] = ["admin", "analyst", "viewer"] as const;

/** Role precedence, used for client-side affordance hiding. */
const ROLE_RANK: Record<Role, number> = { viewer: 0, analyst: 1, admin: 2 };

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

export interface UserProfile {
  id: string;
  email: string;
  fullName: string;
  role: Role;
  defaultIndustry: Industry;
  isActive: boolean;
  mustChangePassword: boolean;
  lastLoginAt: string | null;
  createdAt: string;
}

export interface SessionResponse {
  user: UserProfile;
  csrfToken: string;
  accessExpiresAt: string;
}

export interface LoginRequest {
  email: string;
  password: string;
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
  };
  glossary: {
    version: string;
    domain: string;
    terms: Record<string, GlossaryTerm>;
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
  | "breakdown"
  | "ranking"
  | "top_n"
  | "bottom_n"
  | "contribution"
  | "running_total"
  | "moving_average"
  | "period_growth"
  | "trend"
  | "variance";

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
    points: Array<Record<string, unknown>>;
  } | null;
  recommendedViz: AnalyticsVizKind;
  insights?: { executive: string; analyst: string } | null;
  meta: Record<string, unknown>;
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
