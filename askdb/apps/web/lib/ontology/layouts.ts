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
import dagre from "dagre";

import {
  betweennessCentrality,
  degreeCentrality,
  pageRank,
  type GraphLink,
} from "@/lib/ontology/graph-metrics";

export type GalaxyMode =
  | "network"
  | "centrality"
  | "hierarchy"
  | "lineage"
  | "constellation";

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

const CLUSTER_ANCHORS: Record<string, { x: number; y: number }> = {
  Domain: { x: 0, y: -420 },
  Facts: { x: -380, y: -40 },
  Dimensions: { x: 380, y: -40 },
  Entities: { x: -320, y: 360 },
  Measures: { x: 320, y: 360 },
  Metrics: { x: 0, y: 520 },
  Other: { x: 0, y: 80 },
};

function nodeBaseRadius(node: OntologyNode): number {
  if (node.kind === "domain") return 34;
  if (node.tableType === "fact" || (node.kind === "table" && node.id.includes("fact"))) return 28;
  if (node.kind === "entity") return 24;
  if (node.kind === "table") return 22;
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
    centrality?: Map<string, number>;
    constellation?: boolean;
  } = {},
): PositionedNode[] {
  const centrality = options.centrality ?? degreeCentrality(
    snapshot.nodes.map((n) => n.id),
    linksOf(snapshot),
  );

  const nodes: SimNode[] = snapshot.nodes.map((node, index) => {
    const score = centrality.get(node.id) ?? 0;
    const radius = nodeBaseRadius(node) + score * 18;
    const anchor = CLUSTER_ANCHORS[node.cluster] ?? CLUSTER_ANCHORS.Other!;
    const angle = (index / Math.max(1, snapshot.nodes.length)) * Math.PI * 2;
    return {
      id: node.id,
      kind: node.kind,
      cluster: node.cluster,
      radius,
      x: anchor.x + Math.cos(angle) * 40,
      y: anchor.y + Math.sin(angle) * 40,
    };
  });

  const idToNode = new Map(nodes.map((node) => [node.id, node]));
  const links = snapshot.edges
    .filter((edge) => idToNode.has(edge.source) && idToNode.has(edge.target))
    .map((edge) => ({
      source: edge.source,
      target: edge.target,
      distance: options.constellation ? 140 : 110,
    }));

  const simulation = forceSimulation(nodes)
    .force(
      "link",
      forceLink(links)
        .id((d) => (d as SimNode).id)
        .distance((d) => (d as { distance: number }).distance)
        .strength(options.strength ?? 0.45),
    )
    .force("charge", forceManyBody().strength(options.constellation ? -420 : -280))
    .force("collide", forceCollide<SimNode>().radius((d) => d.radius + 18).iterations(2))
    .force("center", forceCenter(0, 0))
    .force(
      "x",
      forceX<SimNode>((d) => (CLUSTER_ANCHORS[d.cluster] ?? CLUSTER_ANCHORS.Other!).x).strength(
        options.clusterPull ?? 0.12,
      ),
    )
    .force(
      "y",
      forceY<SimNode>((d) => (CLUSTER_ANCHORS[d.cluster] ?? CLUSTER_ANCHORS.Other!).y).strength(
        options.clusterPull ?? 0.12,
      ),
    )
    .stop();

  const ticks = Math.min(320, 40 + nodes.length * 4);
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

function layoutHierarchy(snapshot: OntologySnapshot, centrality: Map<string, number>): PositionedNode[] {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "TB", nodesep: 56, ranksep: 100, marginx: 48, marginy: 48 });

  for (const node of snapshot.nodes) {
    const radius = nodeBaseRadius(node) + (centrality.get(node.id) ?? 0) * 14;
    graph.setNode(node.id, { width: radius * 2 + 48, height: radius * 2 + 28 });
  }
  for (const edge of snapshot.edges) {
    if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
      graph.setEdge(edge.source, edge.target);
    }
  }
  dagre.layout(graph);

  return snapshot.nodes.map((node) => {
    const pos = graph.node(node.id) as { x: number; y: number };
    const radius = nodeBaseRadius(node) + (centrality.get(node.id) ?? 0) * 14;
    return {
      ...node,
      x: (pos?.x ?? 0) - 480,
      y: (pos?.y ?? 0) - 120,
      radius,
      centrality: centrality.get(node.id) ?? 0,
    };
  });
}

function layoutLineage(snapshot: OntologySnapshot, centrality: Map<string, number>): PositionedNode[] {
  const rank = new Map<string, number>();
  for (const node of snapshot.nodes) {
    if (node.kind === "domain") rank.set(node.id, 0);
    else if (node.kind === "entity") rank.set(node.id, 1);
    else if (node.tableType === "fact" || node.id.includes("fact")) rank.set(node.id, 2);
    else if (node.kind === "table" || node.kind === "dimension") rank.set(node.id, 3);
    else rank.set(node.id, 4);
  }

  const buckets = new Map<number, OntologyNode[]>();
  for (const node of snapshot.nodes) {
    const level = rank.get(node.id) ?? 4;
    buckets.set(level, [...(buckets.get(level) ?? []), node]);
  }

  const positioned: PositionedNode[] = [];
  for (const [level, nodes] of [...buckets.entries()].sort((a, b) => a[0] - b[0])) {
    nodes.forEach((node, index) => {
      const score = centrality.get(node.id) ?? 0;
      const radius = nodeBaseRadius(node) + score * 14;
      const spread = Math.max(160, nodes.length * 70);
      positioned.push({
        ...node,
        x: -spread / 2 + (index + 0.5) * (spread / Math.max(1, nodes.length)),
        y: level * 180 - 200,
        radius,
        centrality: score,
      });
    });
  }
  return positioned;
}

export function layoutGalaxy(
  snapshot: OntologySnapshot,
  mode: GalaxyMode,
  metric: CentralityMetric = "degree",
): PositionedNode[] {
  const centrality = computeCentrality(snapshot, metric);
  if (mode === "hierarchy") return layoutHierarchy(snapshot, centrality);
  if (mode === "lineage") return layoutLineage(snapshot, centrality);
  if (mode === "centrality") {
    return runForce(snapshot, { centrality, strength: 0.35, clusterPull: 0.06 });
  }
  if (mode === "constellation") {
    return runForce(snapshot, {
      centrality,
      strength: 0.25,
      clusterPull: 0.18,
      constellation: true,
    });
  }
  return runForce(snapshot, { centrality, strength: 0.42, clusterPull: 0.14 });
}

export function edgeVisualKind(
  edge: OntologyEdge,
  nodes: Map<string, OntologyNode>,
): "primary_key" | "foreign_key" | "semantic" | "ai_inferred" | "lineage" {
  if (edge.kind === "dependency") return "lineage";
  if (edge.kind === "maps_to") return "ai_inferred";
  if (edge.kind === "reference" || edge.fromColumn || edge.toColumn) return "foreign_key";
  const source = nodes.get(edge.source);
  if (source?.primaryKey && edge.fromColumn === source.primaryKey) return "primary_key";
  return "semantic";
}
