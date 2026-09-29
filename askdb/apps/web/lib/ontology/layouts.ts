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
import { conceptCategory } from "@/lib/ontology/kind-filter";

/** Top-level graph experiences. */
export type GalaxyMode = "knowledge" | "network" | "simple" | "ontology";

/**
 * knowledge: organic semantic clusters · influence: centrality rings ·
 * grouped: business categories side by side · rollup: top-down hierarchy ·
 * ontology: business domains (laid out by lib/ontology/ontology-map).
 */
export type GraphLayout = "knowledge" | "influence" | "grouped" | "rollup" | "ontology";

export type CentralityMetric = "degree" | "betweenness" | "pagerank";

/** x/y is the circle centre; the caption sits underneath the circle. */
export type PositionedNode = OntologyNode & {
  x: number;
  y: number;
  radius: number;
  centrality: number;
  captionWidth: number;
};

export const CAPTION_HEIGHT = 30;
const NODE_GAP = 26;

/** Each business category settles in its own neighbourhood of the canvas. */
const CLUSTER_ANCHORS: Record<string, { x: number; y: number }> = {
  Actors: { x: -320, y: -140 },
  Events: { x: 60, y: -40 },
  Outcomes: { x: 360, y: 200 },
  Attributes: { x: -200, y: 300 },
  Context: { x: -380, y: 220 },
  Other: { x: 0, y: 0 },
};

/** Knowledge roles read left to right: actor → entity record → event → outcome, attributes below. */
const KNOWLEDGE_ANCHORS: Record<string, { x: number; y: number }> = {
  Actors: { x: -620, y: -120 },
  Context: { x: -300, y: 140 },
  Events: { x: 20, y: -80 },
  Outcomes: { x: 420, y: 60 },
  Attributes: { x: 60, y: 360 },
  Other: { x: 0, y: 0 },
};

export function captionWidth(label: string): number {
  return Math.min(150, Math.max(64, label.length * 6.6 + 18));
}

function nodeBaseRadius(node: OntologyNode): number {
  const category = conceptCategory(node);
  if (category === "events") return 30;
  if (category === "entities") return 25;
  if (category === "kpis") return 21;
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

type SimNode = SimulationNodeDatum & {
  id: string;
  cluster: string;
  radius: number;
  halfWidth: number;
};

function footprint(node: { radius: number; captionWidth: number }) {
  const halfWidth = Math.max(node.radius, node.captionWidth / 2);
  return { halfWidth, top: node.radius, bottom: node.radius + CAPTION_HEIGHT };
}

/** Push apart any node boxes (circle + caption) that still touch after the simulation. */
export function resolveOverlaps(nodes: PositionedNode[], iterations = 60): PositionedNode[] {
  const out = nodes.map((node) => ({ ...node }));
  for (let pass = 0; pass < iterations; pass += 1) {
    let moved = false;
    for (let i = 0; i < out.length; i += 1) {
      for (let j = i + 1; j < out.length; j += 1) {
        const a = out[i]!;
        const b = out[j]!;
        const fa = footprint(a);
        const fb = footprint(b);
        const overlapX = fa.halfWidth + fb.halfWidth + NODE_GAP - Math.abs(a.x - b.x);
        const aTop = a.y - fa.top;
        const aBottom = a.y + fa.bottom;
        const bTop = b.y - fb.top;
        const bBottom = b.y + fb.bottom;
        const overlapY = Math.min(aBottom, bBottom) + NODE_GAP - Math.max(aTop, bTop);
        if (overlapX <= 0 || overlapY <= 0) continue;
        moved = true;
        if (overlapX < overlapY) {
          const push = overlapX / 2 + 0.5;
          const dir = a.x <= b.x ? -1 : 1;
          a.x += dir * push;
          b.x -= dir * push;
        } else {
          const push = overlapY / 2 + 0.5;
          const dir = a.y <= b.y ? -1 : 1;
          a.y += dir * push;
          b.y -= dir * push;
        }
      }
    }
    if (!moved) break;
  }
  return out;
}

function runForce(
  snapshot: OntologySnapshot,
  options: {
    centrality: Map<string, number>;
    sizeByCentrality: number;
    clusterPull: number;
    charge: number;
    linkDistance: number;
    linkStrength: number;
    anchors?: Record<string, { x: number; y: number }>;
  },
): PositionedNode[] {
  const spread = Math.max(1, Math.sqrt(snapshot.nodes.length / 14));
  const anchors = options.anchors ?? CLUSTER_ANCHORS;
  const anchor = (cluster: string) => {
    const base = anchors[cluster] ?? anchors.Other!;
    return { x: base.x * spread, y: base.y * spread };
  };

  const nodes: SimNode[] = snapshot.nodes.map((node, index) => {
    const score = options.centrality.get(node.id) ?? 0;
    const radius = nodeBaseRadius(node) + score * options.sizeByCentrality;
    const home = anchor(node.cluster);
    const angle = (index / Math.max(1, snapshot.nodes.length)) * Math.PI * 2;
    return {
      id: node.id,
      cluster: node.cluster,
      radius,
      halfWidth: Math.max(radius, captionWidth(node.label) / 2),
      x: home.x + Math.cos(angle) * 80,
      y: home.y + Math.sin(angle) * 80,
    };
  });

  const ids = new Set(nodes.map((node) => node.id));
  const links = snapshot.edges
    .filter((edge) => ids.has(edge.source) && ids.has(edge.target))
    .map((edge) => ({ source: edge.source, target: edge.target }));

  const simulation = forceSimulation(nodes)
    .force(
      "link",
      forceLink(links)
        .id((d) => (d as SimNode).id)
        .distance(options.linkDistance)
        .strength(options.linkStrength),
    )
    .force("charge", forceManyBody().strength(options.charge).distanceMax(900))
    .force(
      "collide",
      forceCollide<SimNode>()
        .radius((d) => Math.max(d.halfWidth, d.radius + CAPTION_HEIGHT / 2) + NODE_GAP)
        .iterations(4),
    )
    .force("center", forceCenter(0, 0))
    .force("x", forceX<SimNode>((d) => anchor(d.cluster).x).strength(options.clusterPull))
    .force("y", forceY<SimNode>((d) => anchor(d.cluster).y).strength(options.clusterPull))
    .stop();

  const ticks = Math.min(600, 200 + nodes.length * 8);
  for (let i = 0; i < ticks; i += 1) simulation.tick();

  const byId = new Map(snapshot.nodes.map((node) => [node.id, node]));
  return resolveOverlaps(
    nodes.map((sim) => {
      const source = byId.get(sim.id)!;
      return {
        ...source,
        x: sim.x ?? 0,
        y: sim.y ?? 0,
        radius: sim.radius,
        centrality: options.centrality.get(sim.id) ?? 0,
        captionWidth: captionWidth(source.label),
      };
    }),
  );
}

/**
 * Roll-up view: each concept sits one row below the things it belongs to.
 * Region → Dealer → Sale → Revenue reads top to bottom.
 */
export function layoutHierarchy(
  snapshot: OntologySnapshot,
  centrality: Map<string, number>,
): PositionedNode[] {
  const parents = new Map<string, string[]>();
  for (const node of snapshot.nodes) parents.set(node.id, []);
  for (const edge of snapshot.edges) {
    if (parents.has(edge.source) && parents.has(edge.target)) parents.get(edge.source)!.push(edge.target);
  }

  const rank = new Map<string, number>();
  const visiting = new Set<string>();
  const rankOf = (id: string): number => {
    const known = rank.get(id);
    if (known !== undefined) return known;
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const ups = parents.get(id) ?? [];
    const value = ups.length ? Math.max(...ups.map(rankOf)) + 1 : 0;
    visiting.delete(id);
    rank.set(id, value);
    return value;
  };
  for (const node of snapshot.nodes) rankOf(node.id);

  const rows = new Map<number, OntologyNode[]>();
  for (const node of snapshot.nodes) {
    const r = rank.get(node.id) ?? 0;
    rows.set(r, [...(rows.get(r) ?? []), node]);
  }

  const columnWidth = Math.max(170, ...snapshot.nodes.map((node) => captionWidth(node.label) + 36));
  const rowHeight = 190;
  const xById = new Map<string, number>();
  const placed: PositionedNode[] = [];

  for (const r of [...rows.keys()].sort((a, b) => a - b)) {
    const members = rows.get(r)!;
    const barycenter = (node: OntologyNode) => {
      const xs = (parents.get(node.id) ?? []).map((id) => xById.get(id)).filter((x) => x !== undefined);
      return xs.length ? xs.reduce((sum, x) => sum + x!, 0) / xs.length : 0;
    };
    const ordered =
      r === 0
        ? [...members].sort((a, b) => b.degree - a.degree || a.label.localeCompare(b.label))
        : [...members].sort((a, b) => barycenter(a) - barycenter(b));
    const offset = ((ordered.length - 1) * columnWidth) / 2;
    ordered.forEach((node, index) => {
      const x = index * columnWidth - offset;
      xById.set(node.id, x);
      const score = centrality.get(node.id) ?? 0;
      placed.push({
        ...node,
        x,
        y: r * rowHeight,
        radius: nodeBaseRadius(node) + score * 6,
        centrality: score,
        captionWidth: captionWidth(node.label),
      });
    });
  }
  return placed;
}

const RING_GAP = 210;
const RING_CAPACITY = [1, 6, 12, 18, 24, 30];

/**
 * Influence rings: the most central concept sits in the middle and every ring outwards is less
 * central. Within a ring, concepts of the same role sit together so colours form sectors.
 */
export function layoutInfluence(snapshot: OntologySnapshot, centrality: Map<string, number>): PositionedNode[] {
  const ranked = [...snapshot.nodes].sort(
    (a, b) => (centrality.get(b.id) ?? 0) - (centrality.get(a.id) ?? 0) || a.label.localeCompare(b.label),
  );
  const rings: OntologyNode[][] = [];
  let cursor = 0;
  for (let ring = 0; cursor < ranked.length; ring += 1) {
    const capacity = RING_CAPACITY[ring] ?? RING_CAPACITY[RING_CAPACITY.length - 1]! + ring * 6;
    rings.push(ranked.slice(cursor, cursor + capacity));
    cursor += capacity;
  }

  const placed: PositionedNode[] = [];
  let previousRadius = 0;
  rings.forEach((members, ring) => {
    const ordered = [...members].sort((a, b) => a.cluster.localeCompare(b.cluster));
    const sized = ordered.map((node) => {
      const score = centrality.get(node.id) ?? 0;
      return { node, score, radius: 18 + score * 34, caption: captionWidth(node.label) };
    });
    const slot = Math.max(...sized.map((item) => Math.max(item.radius * 2, item.caption))) + NODE_GAP;
    const radius =
      ring === 0 ? 0 : Math.max(previousRadius + RING_GAP, (sized.length * slot) / (2 * Math.PI));
    previousRadius = radius;
    const offset = ring * 0.37;
    sized.forEach((item, index) => {
      const angle = -Math.PI / 2 + offset + (index / Math.max(1, sized.length)) * Math.PI * 2;
      placed.push({
        ...item.node,
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
        radius: item.radius,
        centrality: item.score,
        captionWidth: item.caption,
      });
    });
  });
  return placed;
}

/** Distinct ring radii of an influence layout, for drawing the guide circles. */
export function influenceRingRadii(nodes: PositionedNode[]): number[] {
  return [...new Set(nodes.map((node) => Math.round(Math.hypot(node.x, node.y))))].filter((r) => r > 0);
}

export function layoutGalaxy(
  snapshot: OntologySnapshot,
  layout: GraphLayout,
  metric: CentralityMetric = "degree",
): PositionedNode[] {
  if (layout === "influence") return layoutInfluence(snapshot, computeCentrality(snapshot, metric));
  const centrality = computeCentrality(snapshot, "degree");
  if (layout === "rollup") return layoutHierarchy(snapshot, centrality);
  if (layout === "knowledge") {
    return runForce(snapshot, {
      centrality,
      sizeByCentrality: 16,
      clusterPull: 0.11,
      charge: -900,
      linkDistance: 170,
      linkStrength: 0.25,
      anchors: KNOWLEDGE_ANCHORS,
    });
  }
  return runForce(snapshot, {
    centrality,
    sizeByCentrality: 8,
    clusterPull: 0.06,
    charge: -1100,
    linkDistance: 210,
    linkStrength: 0.3,
  });
}

export type EdgeVisualKind = "relationship" | "measure" | "describes";

export function edgeVisualKind(
  edge: OntologyEdge,
  nodes: Map<string, OntologyNode>,
): EdgeVisualKind {
  const source = nodes.get(edge.source);
  if (!source) return "relationship";
  const category = conceptCategory(source);
  if (category === "kpis") return "measure";
  if (category === "breakdowns") return "describes";
  return "relationship";
}
