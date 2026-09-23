import type { OntologyEdge, OntologyNode, OntologySnapshot } from "@nql/shared-types";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type SimulationNodeDatum,
} from "d3-force";

import {
  betweennessCentrality,
  degreeCentrality,
  pageRank,
  type GraphLink,
} from "@/lib/ontology/graph-metrics";

/** Three knowledge-graph identities — not warehouse / lineage maps. */
export type GalaxyMode = "semantic" | "network" | "ontology";

export type CentralityMetric = "degree" | "betweenness" | "pagerank";

export type PositionedNode = OntologyNode & {
  x: number;
  y: number;
  radius: number;
  centrality: number;
};

type SimNode = SimulationNodeDatum & {
  id: string;
  kind: OntologyNode["kind"];
  cluster: string;
  radius: number;
};

/** Soft clouds around the canvas — never Facts/Dimensions corners. */
const CLUSTER_ANCHORS: Record<string, { x: number; y: number }> = {
  Domain: { x: 0, y: 0 },
  Actors: { x: -280, y: -220 },
  Events: { x: 260, y: -200 },
  Context: { x: 300, y: 180 },
  Outcomes: { x: -40, y: 300 },
  Attributes: { x: -300, y: 160 },
  Other: { x: 40, y: 40 },
};

function nodeBaseRadius(node: OntologyNode): number {
  if (node.kind === "domain") return 36;
  if (node.kind === "entity") return 26;
  if (node.kind === "measure") return 22;
  return 18;
}

function linksOf(snapshot: OntologySnapshot): GraphLink[] {
  return snapshot.edges.map((edge) => ({ source: edge.source, target: edge.target }));
}

export function computeCentrality(
  snapshot: OntologySnapshot,
  metric: CentralityMetric,
): Map<string, number> {
  const ids = snapshot.nodes.map((node) => node.id);
  const links = linksOf(snapshot);
  if (metric === "betweenness") return betweennessCentrality(ids, links);
  if (metric === "pagerank") return pageRank(ids, links);
  return degreeCentrality(ids, links);
}

function runForce(
  snapshot: OntologySnapshot,
  options: {
    strength?: number;
    clusterPull?: number;
    charge?: number;
    centrality?: Map<string, number>;
    linkDistance?: number;
  } = {},
): PositionedNode[] {
  const centrality =
    options.centrality ??
    degreeCentrality(
      snapshot.nodes.map((n) => n.id),
      linksOf(snapshot),
    );

  const nodes: SimNode[] = snapshot.nodes.map((node, index) => {
    const score = centrality.get(node.id) ?? 0;
    const radius = nodeBaseRadius(node) + score * 22;
    const anchor = CLUSTER_ANCHORS[node.cluster] ?? CLUSTER_ANCHORS.Other!;
    const angle = (index / Math.max(1, snapshot.nodes.length)) * Math.PI * 2;
    return {
      id: node.id,
      kind: node.kind,
      cluster: node.cluster,
      radius,
      x: (anchor.x || 0) + Math.cos(angle) * 90,
      y: (anchor.y || 0) + Math.sin(angle) * 90,
    };
  });

  const idToNode = new Map(nodes.map((node) => [node.id, node]));
  const links = snapshot.edges
    .filter((edge) => idToNode.has(edge.source) && idToNode.has(edge.target))
    .map((edge) => ({
      source: edge.source,
      target: edge.target,
      distance: options.linkDistance ?? 150,
    }));

  const simulation = forceSimulation(nodes)
    .force(
      "link",
      forceLink(links)
        .id((d) => (d as SimNode).id)
        .distance((d) => (d as { distance: number }).distance)
        .strength(options.strength ?? 0.38),
    )
    .force("charge", forceManyBody().strength(options.charge ?? -380))
    .force("collide", forceCollide<SimNode>().radius((d) => d.radius + 22).iterations(3))
    .force("center", forceCenter(0, 0))
    .force(
      "x",
      forceX<SimNode>((d) => (CLUSTER_ANCHORS[d.cluster] ?? CLUSTER_ANCHORS.Other!).x).strength(
        options.clusterPull ?? 0.04,
      ),
    )
    .force(
      "y",
      forceY<SimNode>((d) => (CLUSTER_ANCHORS[d.cluster] ?? CLUSTER_ANCHORS.Other!).y).strength(
        options.clusterPull ?? 0.04,
      ),
    )
    .stop();

  const ticks = Math.min(360, 50 + nodes.length * 5);
  for (let i = 0; i < ticks; i += 1) simulation.tick();

  const byId = new Map(snapshot.nodes.map((node) => [node.id, node]));
  return nodes.map((sim) => {
    const source = byId.get(sim.id)!;
    return {
      ...source,
      x: sim.x ?? 0,
      y: sim.y ?? 0,
      radius: sim.radius,
      centrality: centrality.get(sim.id) ?? 0,
    };
  });
}

/** Taxonomy fan — parent concepts with children, not concentric warehouse rings. */
function layoutOntology(snapshot: OntologySnapshot, centrality: Map<string, number>): PositionedNode[] {
  const domain = snapshot.nodes.find((node) => node.kind === "domain");
  const families = new Map<string, OntologyNode[]>();
  for (const node of snapshot.nodes) {
    if (node.kind === "domain") continue;
    const key = node.cluster || "Other";
    families.set(key, [...(families.get(key) ?? []), node]);
  }

  const keys = [...families.keys()];
  const placed: PositionedNode[] = [];
  if (domain) {
    placed.push({
      ...domain,
      x: 0,
      y: 0,
      radius: 42,
      centrality: centrality.get(domain.id) ?? 1,
    });
  }

  keys.forEach((key, familyIndex) => {
    const members = families.get(key) ?? [];
    const sweep = (Math.PI * 1.55) / Math.max(1, keys.length);
    const origin = -Math.PI / 2 + familyIndex * sweep + sweep / 2;
    members.forEach((node, index) => {
      const depth = node.kind === "entity" ? 1 : node.kind === "measure" ? 2 : 3;
      const along = (index - (members.length - 1) / 2) * 0.22;
      const radius = 160 + depth * 150;
      const score = centrality.get(node.id) ?? 0;
      placed.push({
        ...node,
        x: Math.cos(origin + along) * radius,
        y: Math.sin(origin + along) * radius,
        radius: nodeBaseRadius(node) + score * 14,
        centrality: score,
      });
    });
  });
  return placed;
}

export function layoutGalaxy(
  snapshot: OntologySnapshot,
  mode: GalaxyMode,
  metric: CentralityMetric = "degree",
): PositionedNode[] {
  const centrality = computeCentrality(snapshot, metric);
  if (mode === "ontology") return layoutOntology(snapshot, centrality);
  if (mode === "network") {
    return runForce(snapshot, {
      centrality,
      strength: 0.55,
      clusterPull: 0.015,
      charge: -520,
      linkDistance: 130,
    });
  }
  return runForce(snapshot, {
    centrality,
    strength: 0.32,
    clusterPull: 0.05,
    charge: -400,
    linkDistance: 165,
  });
}

export function edgeVisualKind(
  edge: OntologyEdge,
  nodes: Map<string, OntologyNode>,
): "primary_key" | "foreign_key" | "semantic" | "ai_inferred" | "lineage" {
  if (edge.kind === "dependency") return "lineage";
  if (edge.kind === "maps_to") return "ai_inferred";
  if (edge.kind === "reference") return "semantic";
  const source = nodes.get(edge.source);
  if (source?.primaryKey && edge.fromColumn === source.primaryKey) return "primary_key";
  if (edge.fromColumn || edge.toColumn) return "foreign_key";
  return "semantic";
}
