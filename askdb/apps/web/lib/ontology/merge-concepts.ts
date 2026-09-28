import type { OntologyEdge, OntologyNode, OntologySnapshot } from "@nql/shared-types";

import { CONCEPT_CATEGORIES, conceptCategory } from "@/lib/ontology/kind-filter";
import { relationshipVerb } from "@/lib/ontology/relationship-labels";

const KIND_RANK: Record<OntologyNode["kind"], number> = {
  entity: 5,
  measure: 4,
  dimension: 3,
  domain: 2,
  table: 1,
};

/** "Vehicle / Car Line" → "vehicle", "Sales Transactions" → "sale transaction". */
export function normalizeConceptKey(label: string): string {
  return label
    .split("/")[0]!
    .toLowerCase()
    .replace(/^(fact|dim|dimension|table|entity|measure)\s+/g, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .map((word) => (word.length > 3 && word.endsWith("s") && !word.endsWith("ss") ? word.slice(0, -1) : word))
    .join(" ");
}

/** "Vehicle / Car Line" → "Vehicle". */
export function canonicalLabel(label: string): string {
  return label.split("/")[0]!.trim() || label;
}

function labelParts(label: string): string[] {
  return label
    .split("/")
    .map((part) => part.trim())
    .filter(Boolean);
}

/** Logical table a node describes, when it is the same business thing as that table. */
function boundTable(node: OntologyNode, factTables: Set<string>): string | null {
  if (node.kind === "table") return node.id.replace(/^table:/, "");
  if (node.kind === "entity") return node.tables[0] ?? null;
  if (node.kind === "dimension") {
    const table = node.tables[0];
    // A date on the sales fact is a breakdown of the sale, not the sale itself.
    return table && !factTables.has(table) ? table : null;
  }
  return null;
}

class UnionFind {
  private parent = new Map<string, string>();
  find(id: string): string {
    const parent = this.parent.get(id) ?? id;
    if (parent === id) return id;
    const root = this.find(parent);
    this.parent.set(id, root);
    return root;
  }
  union(a: string, b: string) {
    const ra = this.find(a);
    const rb = this.find(b);
    if (ra !== rb) this.parent.set(rb, ra);
  }
}

function pickSurvivor(members: OntologyNode[]): OntologyNode {
  return members.reduce((best, node) => {
    const rank = KIND_RANK[node.kind] - KIND_RANK[best.kind];
    if (rank !== 0) return rank > 0 ? node : best;
    return node.degree > best.degree ? node : best;
  });
}

function mergeGroup(members: OntologyNode[]): OntologyNode {
  const survivor = pickSurvivor(members);
  const table = members.find((node) => node.kind === "table");
  const label = canonicalLabel(survivor.label);
  const aliasPool = [
    ...members.flatMap((node) => [...labelParts(node.label), ...node.synonyms]),
  ];
  const seen = new Set([normalizeConceptKey(label)]);
  const synonyms: string[] = [];
  for (const alias of aliasPool) {
    const key = normalizeConceptKey(alias);
    if (seen.has(key)) continue;
    seen.add(key);
    synonyms.push(alias);
  }
  const widest = members.reduce((best, node) => (node.columns.length > best.columns.length ? node : best));
  return {
    ...survivor,
    label,
    synonyms,
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

function withCategory(node: OntologyNode): OntologyNode {
  const meta = CONCEPT_CATEGORIES.find((item) => item.id === conceptCategory(node))!;
  return { ...node, cluster: meta.cluster, clusterColor: meta.color };
}

/**
 * One node per business concept. Entity, table, and dimension records that describe the
 * same business thing (Vehicle, "Vehicle / Car Line", Car) collapse into a canonical
 * concept; every other name is kept as an alias on that concept.
 */
export function mergeOntologyConcepts(snapshot: OntologySnapshot): OntologySnapshot {
  const factTables = new Set(
    snapshot.nodes
      .filter((node) => node.kind === "table" && node.tableType === "fact")
      .map((node) => node.id.replace(/^table:/, "")),
  );

  const uf = new UnionFind();
  const byTable = new Map<string, string>();
  const byLabel = new Map<string, string>();
  for (const node of snapshot.nodes) {
    const table = boundTable(node, factTables);
    if (table) {
      const existing = byTable.get(table);
      if (existing) uf.union(existing, node.id);
      else byTable.set(table, node.id);
    }
    if (node.kind === "domain") continue;
    const key = normalizeConceptKey(node.label);
    const existing = byLabel.get(key);
    if (existing) uf.union(existing, node.id);
    else byLabel.set(key, node.id);
  }

  const kindById = new Map(snapshot.nodes.map((node) => [node.id, node.kind]));
  for (const node of snapshot.nodes) {
    if (node.kind === "domain" || node.kind === "measure") continue;
    for (const synonym of node.synonyms) {
      const match = byLabel.get(normalizeConceptKey(synonym));
      const kind = match ? kindById.get(match) : undefined;
      if (match && kind !== "measure" && kind !== "domain") uf.union(match, node.id);
    }
  }

  const groups = new Map<string, OntologyNode[]>();
  for (const node of snapshot.nodes) {
    const root = uf.find(node.id);
    groups.set(root, [...(groups.get(root) ?? []), node]);
  }

  const survivorByOldId = new Map<string, string>();
  const merged: OntologyNode[] = [];
  for (const members of groups.values()) {
    const concept = withCategory(mergeGroup(members));
    for (const member of members) survivorByOldId.set(member.id, concept.id);
    merged.push(concept);
  }
  const byId = new Map(merged.map((node) => [node.id, node]));

  const edges: OntologyEdge[] = [];
  const seenPairs = new Set<string>();
  for (const edge of snapshot.edges) {
    const source = survivorByOldId.get(edge.source) ?? edge.source;
    const target = survivorByOldId.get(edge.target) ?? edge.target;
    if (source === target) continue;
    const pair = [source, target].sort().join("|");
    if (seenPairs.has(pair)) continue;
    seenPairs.add(pair);
    const sourceNode = byId.get(source);
    const targetNode = byId.get(target);
    edges.push({
      ...edge,
      source,
      target,
      label: sourceNode && targetNode ? relationshipVerb(edge, sourceNode, targetNode) : edge.label,
    });
  }

  const degrees = new Map<string, number>();
  for (const edge of edges) {
    degrees.set(edge.source, (degrees.get(edge.source) ?? 0) + 1);
    degrees.set(edge.target, (degrees.get(edge.target) ?? 0) + 1);
  }
  const nodes = merged.map((node) => ({ ...node, degree: degrees.get(node.id) ?? 0 }));

  const clusters = CONCEPT_CATEGORIES.filter((meta) =>
    nodes.some((node) => node.cluster === meta.cluster),
  ).map((meta) => ({ id: meta.cluster, label: meta.label, color: meta.color }));

  return {
    ...snapshot,
    nodes,
    edges,
    clusters,
    metadata: { ...snapshot.metadata, nodeCount: nodes.length, edgeCount: edges.length },
  };
}

/** Drop the industry domain hub (Automotive / Insurance). It is not a business concept. */
export function withoutDomainNodes(snapshot: OntologySnapshot): OntologySnapshot {
  const nodes = snapshot.nodes.filter((node) => node.kind !== "domain");
  const ids = new Set(nodes.map((node) => node.id));
  const edges = snapshot.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  const clusters = snapshot.clusters.filter(
    (cluster) => cluster.id !== "Domain" && nodes.some((node) => node.cluster === cluster.id),
  );
  return {
    ...snapshot,
    nodes,
    edges,
    clusters,
    metadata: { ...snapshot.metadata, nodeCount: nodes.length, edgeCount: edges.length },
  };
}
