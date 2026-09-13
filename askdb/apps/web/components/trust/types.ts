export interface TrustComponent {
  id: string;
  label: string;
  score: number;
  weight: number;
  contribution: number;
}

export interface TrustHero {
  score: number | null;
  label: string;
  available: boolean;
  unavailableReason?: string | null;
  components: TrustComponent[];
  formulaNote: string;
  datasets: number;
  dqChecks: number;
  activeIncidents: number;
  schemaDrift: number;
}

export interface BlastRadius {
  kpis: number;
  dashboards: number;
  insights: number;
}

export interface TrustIncident {
  id: string;
  title: string;
  summary: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  status: "open" | "resolved" | "recovering";
  dataset: string;
  detectedAt: string;
  resolvedAt?: string | null;
  timeToDetectHours?: number | null;
  timeToResolveHours?: number | null;
  impactedAssets: string[];
  rootCauseHint?: string | null;
  blastRadius: BlastRadius;
}

export interface DatasetHealth {
  name: string;
  displayName: string;
  physicalName: string;
  tableType: string;
  healthScore: number;
  dimensions: Record<string, number>;
  flags: Record<string, "ok" | "warn" | "fail">;
  sparkline: number[];
  lastRefresh: string | null;
  slaHours: number | null;
  classification: string;
  certified: boolean;
  restricted: boolean;
}

export interface SchemaChange {
  dataset: string;
  displayName: string;
  fromVersion: number | null;
  toVersion: number | null;
  added: string[];
  removed: string[];
  typeChanges: Array<Record<string, string>>;
  timeline: Array<{ at: string; event: string }>;
  affectedAssets: string[];
  detectedAt: string | null;
}

export interface ColumnProfile {
  name: string;
  nullPct: number;
  distinctCount?: number | null;
  minValue?: string | null;
  maxValue?: string | null;
  topValues?: Array<Record<string, unknown>>;
  pattern?: string | null;
  issue?: string | null;
}

export interface DatasetProfile {
  name: string;
  displayName: string;
  rows: number;
  columns: number;
  nullPct: number;
  duplicates: number;
  lastRefresh: string | null;
  columnProfiles: ColumnProfile[];
  available: boolean;
  unavailableReason?: string | null;
}

export interface GovernanceRecord {
  dataset: string;
  displayName: string;
  technicalOwner: string | null;
  businessOwner: string | null;
  classification: string;
  certified: boolean;
  lastUpdated: string | null;
  glossaryLinked: boolean;
  semanticLinked: boolean;
  lineageAvailable: boolean;
  activeRules: number;
  restricted: boolean;
  visible: boolean;
}

export interface DqRule {
  id: string;
  name: string;
  dataset: string;
  dimension: string;
  threshold: number;
  unit: string;
  passing: boolean;
  observed: number;
  owner: string;
  lastModified: string;
  editable: boolean;
}

export interface NotificationRule {
  id: string;
  name: string;
  minSeverity: string;
  channel: string;
  target: string;
  enabled: boolean;
  note?: string | null;
}

export interface AiSteward {
  summary: string;
  risks: string[];
  recommendations: string[];
  impactAssessment: string;
  groundedOn: string[];
}

export interface TrendPoint {
  period: string;
  trustScore: number | null;
  failedChecks: number;
  freshness: number | null;
  completeness: number | null;
  schemaStability: number | null;
}

export interface LineageImpact {
  dataset: string;
  nodes: Array<Record<string, unknown>>;
  edges: Array<{ source: string; target: string }>;
  explorePath: string;
}

export interface DataTrustCenter {
  industry: string;
  computedAt: string;
  dataAsOf: string | null;
  cacheTtlSeconds: number;
  hero: TrustHero;
  incidents: TrustIncident[];
  incidentHistory: TrustIncident[];
  trends: TrendPoint[];
  datasets: DatasetHealth[];
  schemaChanges: SchemaChange[];
  profiles: DatasetProfile[];
  governance: GovernanceRecord[];
  lineage: LineageImpact[];
  rules: DqRule[];
  notificationRules: NotificationRule[];
  steward: AiSteward;
  defaultView: "overview" | "technical";
}

export interface TrustSnapshot {
  available: boolean;
  score: number | null;
  label: string;
  components: TrustComponent[];
  formulaNote?: string;
  activeIncidents?: number;
  computedAt?: string;
}
