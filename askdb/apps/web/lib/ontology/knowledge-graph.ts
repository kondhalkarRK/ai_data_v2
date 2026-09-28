import type { OntologyEdge, OntologyNode, OntologySnapshot } from "@nql/shared-types";

import { isFactNode } from "@/lib/ontology/kind-filter";
import { relationshipVerb } from "@/lib/ontology/relationship-labels";

/** Semantic roles in the knowledge graph. Each concept plays exactly one. */
export type KnowledgeCategory = "actor" | "event" | "entity" | "attribute" | "outcome";

export type KnowledgeFilter = "all" | "connected" | KnowledgeCategory;

export const KNOWLEDGE_CATEGORIES: ReadonlyArray<{
  id: KnowledgeCategory;
  cluster: string;
  label: string;
  color: string;
  hint: string;
}> = [
  {
    id: "actor",
    cluster: "Actors",
    label: "Actor",
    color: "#34d399",
    hint: "Who or what takes part in the business — Dealer, Vehicle, Salesperson, Region.",
  },
  {
    id: "event",
    cluster: "Events",
    label: "Event",
    color: "#60a5fa",
    hint: "Something that happens and is recorded — a Sale, a Claim, a Premium payment.",
  },
  {
    id: "entity",
    cluster: "Context",
    label: "Entity",
    color: "#a78bfa",
    hint: "The master record that describes an actor — Car Line, Dealer Network, Geography.",
  },
  {
    id: "attribute",
    cluster: "Attributes",
    label: "Attribute",
    color: "#fbbf24",
    hint: "A property used to slice or filter — Date, Colour, Product.",
  },
  {
    id: "outcome",
    cluster: "Outcomes",
    label: "Outcome",
    color: "#f472b6",
    hint: "A result the business measures — Revenue, Units Sold, Loss Ratio.",
  },
];

export const CONNECTED_FILTER_HINT =
  "Also show everything directly linked to the selected roles, so you see how they connect.";

const CATEGORY_BY_CLUSTER = new Map(KNOWLEDGE_CATEGORIES.map((item) => [item.cluster, item]));

export function knowledgeMeta(category: KnowledgeCategory) {
  return KNOWLEDGE_CATEGORIES.find((item) => item.id === category)!;
}

export function knowledgeCategory(
  node: Pick<OntologyNode, "kind" | "tableType" | "id" | "cluster">,
): KnowledgeCategory {
  const byCluster = CATEGORY_BY_CLUSTER.get(node.cluster);
  if (byCluster) return byCluster.id;
  if (isFactNode(node)) return "event";
  if (node.kind === "measure") return "outcome";
  if (node.kind === "dimension") return "attribute";
  if (node.kind === "table") return "entity";
  return "actor";
}

export type KnowledgeEdgeKind = "relates" | "represents" | "measures" | "describes";

export const KNOWLEDGE_EDGE_STYLES: Record<KnowledgeEdgeKind, { color: string; label: string }> = {
  relates: { color: "#818cf8", label: "Semantic relationship" },
  represents: { color: "#fbbf24", label: "Recorded as (actor → entity)" },
  measures: { color: "#f472b6", label: "Outcome measured from" },
  describes: { color: "#2dd4bf", label: "Attribute describes" },
};

export function knowledgeEdgeKind(
  edge: Pick<OntologyEdge, "source" | "target">,
  nodes: Map<string, Pick<OntologyNode, "kind" | "tableType" | "id" | "cluster">>,
): KnowledgeEdgeKind {
  const source = nodes.get(edge.source);
  const target = nodes.get(edge.target);
  if (!source) return "relates";
  const from = knowledgeCategory(source);
  if (from === "outcome") return "measures";
  if (from === "attribute") return "describes";
  if (from === "actor" && target && knowledgeCategory(target) === "entity") return "represents";
  return "relates";
}

/** Exact business name, ignoring case, prefixes and plurals — "Sales Transactions" = "Sales Transaction". */
function semanticKey(label: string): string {
  return label
    .toLowerCase()
    .replace(/^(fact|dim|dimension|table|entity|measure)\s+/g, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .map((word) => (word.length > 3 && word.endsWith("s") && !word.endsWith("ss") ? word.slice(0, -1) : word))
    .join(" ");
}

/** "Vehicle / Car Line" → "Car Line": the record's own name, distinct from the actor it describes. */
function entityLabel(node: OntologyNode): string {
  if (node.kind !== "table" || isFactNode(node)) return node.label;
  const parts = node.label.split("/").map((part) => part.trim()).filter(Boolean);
  return parts.length > 1 ? parts[parts.length - 1]! : node.label;
}

const KIND_RANK: Record<OntologyNode["kind"], number> = {
  entity: 5,
  measure: 4,
  dimension: 3,
  domain: 2,
  table: 1,
};

function mergeMembers(members: OntologyNode[]): OntologyNode {
  const survivor = members.reduce((best, node) => {
    const rank = KIND_RANK[node.kind] - KIND_RANK[best.kind];
    if (rank !== 0) return rank > 0 ? node : best;
    return node.degree > best.degree ? node : best;
  });
  const table = members.find((node) => node.kind === "table");
  const label = entityLabel(survivor);
  const seen = new Set([semanticKey(label)]);
  const synonyms: string[] = [];
  for (const alias of members.flatMap((node) => [node.label, ...node.synonyms])) {
    const key = semanticKey(alias);
    if (seen.has(key)) continue;
    seen.add(key);
    synonyms.push(alias);
  }
  const fact = members.find((node) => isFactNode(node));
  const role = fact ? knowledgeMeta("event") : knowledgeMeta(knowledgeCategory(survivor));
  const widest = members.reduce((best, node) => (node.columns.length > best.columns.length ? node : best));
  return {
    ...survivor,
    label,
    synonyms,
    cluster: role.cluster,
    clusterColor: role.color,
    description: survivor.description || members.find((node) => node.description)?.description,
    physicalName: table?.physicalName ?? survivor.physicalName,
    tableType: table?.tableType ?? survivor.tableType,
    grain: table?.grain ?? survivor.grain,
    primaryKey: table?.primaryKey ?? survivor.primaryKey,
    columns: widest.columns,
    tables: [...new Set(members.flatMap((node) => node.tables))],
    relationships: [...new Set(members.flatMap((node) => node.relationships))],
    lineage: [...new Set(members.flatMap((node) => node.lineage))],
  };
}

function knowledgeVerb(edge: OntologyEdge, source: OntologyNode, target: OntologyNode): string {
  const from = knowledgeCategory(source);
  const to = knowledgeCategory(target);
  if (from === "outcome") return "measured from";
  if (from === "attribute") return "describes";
  if (from === "actor" && to === "entity") return "recorded as";
  if (from === "actor" && to === "event") return "takes part in";
  return relationshipVerb(edge, source, target);
}

/**
 * The semantic knowledge graph: actors, the entity records behind them, the events they take
 * part in, and the outcomes and attributes around those events. Only concepts with the same
 * business name are merged, so the actor → entity → event layering stays visible.
 */
export function buildKnowledgeGraph(snapshot: OntologySnapshot): OntologySnapshot {
  const groups = new Map<string, OntologyNode[]>();
  for (const node of snapshot.nodes) {
    if (node.kind === "domain") continue;
    const key = semanticKey(entityLabel(node));
    groups.set(key, [...(groups.get(key) ?? []), node]);
  }

  const survivorByOldId = new Map<string, string>();
  const merged: OntologyNode[] = [];
  for (const members of groups.values()) {
    const concept = mergeMembers(members);
    for (const member of members) survivorByOldId.set(member.id, concept.id);
    merged.push(concept);
  }
  const byId = new Map(merged.map((node) => [node.id, node]));

  const edges: OntologyEdge[] = [];
  const seen = new Set<string>();
  for (const edge of snapshot.edges) {
    const source = survivorByOldId.get(edge.source);
    const target = survivorByOldId.get(edge.target);
    if (!source || !target || source === target) continue;
    const key = [source, target].sort().join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    edges.push({ ...edge, source, target, label: knowledgeVerb(edge, byId.get(source)!, byId.get(target)!) });
  }

  const degrees = new Map<string, number>();
  for (const edge of edges) {
    degrees.set(edge.source, (degrees.get(edge.source) ?? 0) + 1);
    degrees.set(edge.target, (degrees.get(edge.target) ?? 0) + 1);
  }
  const nodes = merged.map((node) => ({ ...node, degree: degrees.get(node.id) ?? 0 }));
  const clusters = KNOWLEDGE_CATEGORIES.filter((meta) => nodes.some((node) => node.cluster === meta.cluster)).map(
    (meta) => ({ id: meta.cluster, label: meta.label, color: meta.color }),
  );

  return {
    ...snapshot,
    nodes,
    edges,
    clusters,
    metadata: { ...snapshot.metadata, nodeCount: nodes.length, edgeCount: edges.length },
  };
}

/**
 * Concepts visible for the selected roles. "Connected" widens the selection to everything one
 * step away; on its own it keeps every concept that has at least one relationship.
 */
export function knowledgeVisibleIds(
  snapshot: OntologySnapshot,
  filters: readonly KnowledgeFilter[],
): Set<string> | null {
  if (filters.length === 0 || filters.includes("all")) return null;
  const roles = filters.filter((filter): filter is KnowledgeCategory => filter !== "connected");
  const connected = filters.includes("connected");
  const visible = new Set(
    snapshot.nodes
      .filter((node) => (roles.length ? roles.includes(knowledgeCategory(node)) : connected && node.degree > 0))
      .map((node) => node.id),
  );
  if (connected && roles.length) {
    const core = new Set(visible);
    for (const edge of snapshot.edges) {
      if (core.has(edge.source)) visible.add(edge.target);
      if (core.has(edge.target)) visible.add(edge.source);
    }
  }
  return visible;
}
