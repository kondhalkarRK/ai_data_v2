import type { OntologyEdge, OntologyNode, OntologySnapshot } from "@nql/shared-types";

const KIND_RANK: Record<OntologyNode["kind"], number> = {
  entity: 5,
  measure: 4,
  dimension: 3,
  domain: 2,
  table: 1,
};

const CLUSTER_REMAP: Record<string, { id: string; label: string; color: string }> = {
  Facts: { id: "Events", label: "Events", color: "#2563eb" },
  Dimensions: { id: "Context", label: "Context", color: "#7c3aed" },
  Entities: { id: "Actors", label: "Actors", color: "#059669" },
  Measures: { id: "Outcomes", label: "Outcomes", color: "#db2777" },
  Metrics: { id: "Attributes", label: "Attributes", color: "#ca8a04" },
  Domain: { id: "Domain", label: "Domain", color: "#0f766e" },
};

export function normalizeConceptKey(label: string): string {
  return label
    .toLowerCase()
    .replace(/^(fact|dim|dimension|table|entity|measure)\s+/g, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function preferNode(a: OntologyNode, b: OntologyNode): OntologyNode {
  const rank = KIND_RANK[a.kind] - KIND_RANK[b.kind];
  if (rank !== 0) return rank > 0 ? a : b;
  return a.degree >= b.degree ? a : b;
}

function mergeNode(keep: OntologyNode, drop: OntologyNode): OntologyNode {
  return {
    ...keep,
    synonyms: [...new Set([...keep.synonyms, ...drop.synonyms, drop.label])],
    tables: [...new Set([...keep.tables, ...drop.tables])],
    columns: keep.columns.length >= drop.columns.length ? keep.columns : drop.columns,
    relationships: [...new Set([...keep.relationships, ...drop.relationships])],
    lineage: [...new Set([...keep.lineage, ...drop.lineage])],
    description: keep.description || drop.description,
    physicalName: keep.physicalName || drop.physicalName,
    degree: Math.max(keep.degree, drop.degree),
  };
}

function semanticCluster(node: OntologyNode): OntologyNode {
  const mapped = CLUSTER_REMAP[node.cluster];
  if (!mapped) return node;
  return { ...node, cluster: mapped.id, clusterColor: mapped.color };
}

/**
 * Collapse duplicate business concepts (Vehicle entity + Vehicle table) into one
 * graph node and rewrite edges so relationships stay, without a second copy.
 */
export function mergeOntologyConcepts(snapshot: OntologySnapshot): OntologySnapshot {
  const groups = new Map<string, OntologyNode[]>();
  for (const node of snapshot.nodes) {
    const key = normalizeConceptKey(node.label);
    groups.set(key, [...(groups.get(key) ?? []), node]);
  }

  const survivorByOldId = new Map<string, string>();
  const merged: OntologyNode[] = [];

  for (const members of groups.values()) {
    let keep = members[0]!;
    for (const extra of members.slice(1)) keep = preferNode(keep, extra);
    for (const extra of members) {
      if (extra.id !== keep.id) keep = mergeNode(keep, extra);
      survivorByOldId.set(extra.id, keep.id);
    }
    merged.push(semanticCluster(keep));
  }

  const edges: OntologyEdge[] = [];
  const seen = new Set<string>();
  for (const edge of snapshot.edges) {
    const source = survivorByOldId.get(edge.source) ?? edge.source;
    const target = survivorByOldId.get(edge.target) ?? edge.target;
    if (source === target) continue;
    const key = `${source}|${target}|${edge.label}`;
    if (seen.has(key)) continue;
    seen.add(key);
    edges.push({ ...edge, source, target });
  }

  const degrees = new Map<string, number>();
  for (const edge of edges) {
    degrees.set(edge.source, (degrees.get(edge.source) ?? 0) + 1);
    degrees.set(edge.target, (degrees.get(edge.target) ?? 0) + 1);
  }

  const nodes = merged.map((node) => ({
    ...node,
    degree: degrees.get(node.id) ?? 0,
  }));

  const clusterIds = [...new Set(nodes.map((node) => node.cluster))];
  const clusters = clusterIds.map((id) => {
    const known = Object.values(CLUSTER_REMAP).find((item) => item.id === id);
    return {
      id,
      label: known?.label ?? id,
      color: known?.color ?? nodes.find((node) => node.cluster === id)?.clusterColor ?? "#64748b",
    };
  });

  return {
    ...snapshot,
    nodes,
    edges,
    clusters,
    metadata: {
      ...snapshot.metadata,
      nodeCount: nodes.length,
      edgeCount: edges.length,
    },
  };
}

/** Ontology view: vocabulary only — no leftover physical tables. */
export function conceptOnlySnapshot(snapshot: OntologySnapshot): OntologySnapshot {
  const nodes = snapshot.nodes.filter((node) => node.kind !== "table");
  const ids = new Set(nodes.map((node) => node.id));
  const edges = snapshot.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  return {
    ...snapshot,
    nodes,
    edges,
    metadata: { ...snapshot.metadata, nodeCount: nodes.length, edgeCount: edges.length },
  };
}
