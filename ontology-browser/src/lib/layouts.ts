/**
 * Layout algorithms: Force · Centrality · Hierarchy
 */
import dagre from "dagre";
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
import type { Edge, Node } from "@xyflow/react";
import type { LayoutMode, OntologyNodeData } from "./types";

export type RFNode = Node<OntologyNodeData>;
export type RFEdge = Edge;

interface SimNode extends SimulationNodeDatum {
  id: string;
  degree: number;
  cluster: string;
}

function radiusFor(n: OntologyNodeData, centralityBoost = false): number {
  const base =
    n.kind === "domain" ? 28 : n.kind === "entity" ? 22 : n.kind === "table" ? 20 : 16;
  const boost = centralityBoost ? n.degree * 2.8 : n.degree * 1.4;
  return Math.max(14, Math.min(48, base + boost));
}

const CLUSTER_SLOT: Record<string, { x: number; y: number }> = {
  Domain: { x: 0, y: -40 },
  Facts: { x: -220, y: 40 },
  Dimensions: { x: 220, y: 40 },
  Entities: { x: -260, y: 260 },
  Measures: { x: 260, y: 260 },
  Metrics: { x: 0, y: 320 },
  Other: { x: 0, y: 120 },
};

export function layoutHierarchy(nodes: RFNode[], edges: RFEdge[]): RFNode[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", nodesep: 56, ranksep: 100, marginx: 48, marginy: 48 });

  for (const n of nodes) {
    const r = radiusFor(n.data);
    g.setNode(n.id, { width: r * 2 + 64, height: r * 2 + 36 });
  }
  for (const e of edges) g.setEdge(e.source, e.target);
  dagre.layout(g);

  return nodes.map((n) => {
    const pos = g.node(n.id);
    const r = radiusFor(n.data);
    return {
      ...n,
      position: {
        x: (pos?.x ?? 0) - (r + 32),
        y: (pos?.y ?? 0) - (r + 18),
      },
    };
  });
}

export function layoutForce(
  nodes: RFNode[],
  edges: RFEdge[],
  opts?: { centrality?: boolean },
): RFNode[] {
  const centrality = Boolean(opts?.centrality);
  const simNodes: SimNode[] = nodes.map((n, i) => {
    const slot = CLUSTER_SLOT[n.data.cluster] ?? CLUSTER_SLOT.Other;
    const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2;
    return {
      id: n.id,
      degree: n.data.degree,
      cluster: n.data.cluster,
      x: slot.x + Math.cos(angle) * 40,
      y: slot.y + Math.sin(angle) * 40,
    };
  });
  const index = new Map(simNodes.map((n, i) => [n.id, i]));
  const links = edges
    .map((e) => {
      const s = index.get(e.source);
      const t = index.get(e.target);
      if (s == null || t == null) return null;
      return { source: s, target: t };
    })
    .filter(Boolean) as { source: number; target: number }[];

  const simulation = forceSimulation(simNodes)
    .force(
      "link",
      forceLink(links)
        .distance(centrality ? 110 : 130)
        .strength(0.28),
    )
    .force("charge", forceManyBody().strength(centrality ? -520 : -380))
    .force("center", forceCenter(0, 0))
    .force(
      "x",
      forceX<SimNode>((d) => (CLUSTER_SLOT[d.cluster] ?? CLUSTER_SLOT.Other).x).strength(0.18),
    )
    .force(
      "y",
      forceY<SimNode>((d) => (CLUSTER_SLOT[d.cluster] ?? CLUSTER_SLOT.Other).y).strength(0.18),
    )
    .force(
      "collide",
      forceCollide<SimNode>().radius((d) => {
        const node = nodes.find((n) => n.id === d.id)!;
        return radiusFor(node.data, centrality) + 14;
      }),
    )
    .stop();

  const ticks = Math.min(420, 90 + nodes.length * 2);
  for (let i = 0; i < ticks; i += 1) simulation.tick();

  const byId = new Map(simNodes.map((n) => [n.id, n]));
  return nodes.map((n) => {
    const s = byId.get(n.id);
    const r = radiusFor(n.data, centrality);
    return {
      ...n,
      position: { x: (s?.x ?? 0) - r, y: (s?.y ?? 0) - r },
    };
  });
}

export function layoutCentrality(nodes: RFNode[], edges: RFEdge[]): RFNode[] {
  return layoutForce(nodes, edges, { centrality: true });
}

export function applyLayout(
  mode: LayoutMode,
  nodes: RFNode[],
  edges: RFEdge[],
): RFNode[] {
  switch (mode) {
    case "hierarchy":
      return layoutHierarchy(nodes, edges);
    case "centrality":
      return layoutCentrality(nodes, edges);
    case "force":
    default:
      return layoutForce(nodes, edges);
  }
}

export function toReactFlowElements(graph: {
  nodes: OntologyNodeData[];
  edges: {
    id: string;
    source: string;
    target: string;
    label: string;
    kind: string;
  }[];
}): { nodes: RFNode[]; edges: RFEdge[] } {
  const nodes: RFNode[] = graph.nodes.map((n) => ({
    id: n.id,
    type: "ontology",
    position: { x: 0, y: 0 },
    data: n,
    draggable: true,
  }));

  const edges: RFEdge[] = graph.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.kind === "relationship" ? e.label : undefined,
    type: "default",
    animated: false,
    data: e,
    style: {
      stroke: "#94a3b8",
      strokeWidth: e.kind === "dependency" ? 1 : 1.4,
      opacity: e.kind === "dependency" ? 0.28 : 0.55,
    },
  }));

  return { nodes, edges };
}

/** Approximate convex hull for cluster zone SVG paths. */
export function convexHull(
  points: { x: number; y: number }[],
): { x: number; y: number }[] {
  if (points.length < 3) return points;
  const pts = [...points].sort((a, b) => (a.x === b.x ? a.y - b.y : a.x - b.x));
  const cross = (
    o: { x: number; y: number },
    a: { x: number; y: number },
    b: { x: number; y: number },
  ) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const lower: { x: number; y: number }[] = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
      lower.pop();
    }
    lower.push(p);
  }
  const upper: { x: number; y: number }[] = [];
  for (let i = pts.length - 1; i >= 0; i -= 1) {
    const p = pts[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
      upper.pop();
    }
    upper.push(p);
  }
  upper.pop();
  lower.pop();
  return lower.concat(upper);
}
