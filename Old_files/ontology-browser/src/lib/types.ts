/**
 * Shared ontology graph types (visualization layer only).
 */

export type NodeKind = "table" | "entity" | "measure" | "dimension" | "domain";

export type EdgeKind = "relationship" | "reference" | "maps_to" | "dependency";

export type LayoutMode = "force" | "centrality" | "hierarchy";

export interface ColumnMeta {
  name: string;
  displayName: string;
  type: string;
  role: string;
  references?: string;
}

export interface OntologyNodeData {
  id: string;
  label: string;
  kind: NodeKind;
  domain: string;
  description?: string;
  physicalName?: string;
  tableType?: string;
  grain?: string;
  primaryKey?: string;
  synonyms: string[];
  tables: string[];
  columns: ColumnMeta[];
  relationships: string[];
  lineage: string[];
  degree: number;
  category?: string;
  /** Cluster zone key used for filters + hulls */
  cluster: string;
  clusterColor: string;
  dimmed?: boolean;
  raw?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface OntologyEdgeData {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  label: string;
  fromColumn?: string;
  toColumn?: string;
  cardinality?: string;
}

export interface OntologyGraph {
  domain: string;
  description?: string;
  version?: string;
  nodes: OntologyNodeData[];
  edges: OntologyEdgeData[];
  clusters: ClusterMeta[];
}

export interface ClusterMeta {
  id: string;
  label: string;
  color: string;
}

export interface PackManifestEntry {
  id: string;
  label: string;
  modelUrl: string;
  glossaryUrl: string | null;
}

export interface PackManifest {
  generatedAt: string;
  packs: PackManifestEntry[];
}

/** Stable palette matching RAISE-style domain chips (not purple-first). */
export const CLUSTER_PALETTE: Record<string, string> = {
  Facts: "#2563eb",
  Dimensions: "#7c3aed",
  Entities: "#059669",
  Measures: "#db2777",
  Metrics: "#ca8a04",
  Domain: "#0f766e",
  Other: "#64748b",
};
