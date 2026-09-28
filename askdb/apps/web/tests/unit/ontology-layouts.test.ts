import type { OntologyNode, OntologySnapshot } from "@nql/shared-types";
import { describe, expect, it } from "vitest";

import { curveBetween, labelBox, placeEdgeLabels, pointOnCurve } from "@/lib/ontology/edge-geometry";
import { CAPTION_HEIGHT, influenceRingRadii, layoutGalaxy } from "@/lib/ontology/layouts";

function node(id: string, label: string, kind: OntologyNode["kind"], cluster: string): OntologyNode {
  return {
    id,
    label,
    kind,
    domain: "Automotive",
    description: "",
    synonyms: [],
    tables: [],
    columns: [],
    relationships: [],
    lineage: [],
    degree: 1,
    cluster,
    clusterColor: "#059669",
  };
}

const SNAPSHOT: OntologySnapshot = {
  nodes: [
    node("region", "Region", "entity", "Actors"),
    node("dealer", "Dealer", "entity", "Actors"),
    node("sale", "Sales Transaction", "table", "Events"),
    node("vehicle", "Vehicle", "entity", "Actors"),
    node("revenue", "Revenue", "measure", "Outcomes"),
    node("units", "Units Sold", "measure", "Outcomes"),
    node("date", "Date", "dimension", "Attributes"),
  ],
  edges: [
    { id: "1", source: "dealer", target: "region", kind: "reference", label: "located in" },
    { id: "2", source: "sale", target: "dealer", kind: "reference", label: "sold by" },
    { id: "3", source: "sale", target: "vehicle", kind: "reference", label: "for product" },
    { id: "4", source: "revenue", target: "sale", kind: "maps_to", label: "measured from" },
    { id: "5", source: "units", target: "sale", kind: "maps_to", label: "measured from" },
    { id: "6", source: "date", target: "sale", kind: "maps_to", label: "describes" },
  ],
  clusters: [],
  metadata: {
    industry: "automotive",
    version: "1",
    compiledAt: "2026-01-01T00:00:00.000Z",
    nodeCount: 7,
    edgeCount: 6,
    buildMs: 1,
  },
};

function boxesOverlap(
  a: { x: number; y: number; radius: number; captionWidth: number },
  b: { x: number; y: number; radius: number; captionWidth: number },
) {
  const halfA = Math.max(a.radius, a.captionWidth / 2);
  const halfB = Math.max(b.radius, b.captionWidth / 2);
  const overlapX = halfA + halfB - Math.abs(a.x - b.x);
  const overlapY =
    Math.min(a.y + a.radius + CAPTION_HEIGHT, b.y + b.radius + CAPTION_HEIGHT) -
    Math.max(a.y - a.radius, b.y - b.radius);
  return overlapX > 0 && overlapY > 0;
}

describe("graph layouts", () => {
  it.each(["knowledge", "grouped", "influence"] as const)("%s layout leaves no overlapping nodes or captions", (layout) => {
    const nodes = layoutGalaxy(SNAPSHOT, layout);
    expect(nodes).toHaveLength(SNAPSHOT.nodes.length);
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        expect(boxesOverlap(nodes[i]!, nodes[j]!)).toBe(false);
      }
    }
  });

  it("is deterministic so the graph does not jump between renders", () => {
    const a = layoutGalaxy(SNAPSHOT, "knowledge").map((item) => [item.id, Math.round(item.x), Math.round(item.y)]);
    const b = layoutGalaxy(SNAPSHOT, "knowledge").map((item) => [item.id, Math.round(item.x), Math.round(item.y)]);
    expect(a).toEqual(b);
  });

  it("influence puts the most connected concept at the centre and less central ones on outer rings", () => {
    const nodes = layoutGalaxy(SNAPSHOT, "influence", "degree");
    const distance = (id: string) => {
      const item = nodes.find((entry) => entry.id === id)!;
      return Math.hypot(item.x, item.y);
    };
    expect(distance("sale")).toBe(0);
    expect(distance("region")).toBeGreaterThan(0);
    expect(influenceRingRadii(nodes).length).toBeGreaterThanOrEqual(1);
  });

  it("rollup puts the containing concept above what rolls up into it", () => {
    const nodes = layoutGalaxy(SNAPSHOT, "rollup");
    const y = (id: string) => nodes.find((item) => item.id === id)!.y;
    expect(y("region")).toBeLessThan(y("dealer"));
    expect(y("dealer")).toBeLessThan(y("sale"));
    expect(y("sale")).toBeLessThan(y("revenue"));
    expect(y("revenue")).toBe(y("units"));
  });
});

describe("edge geometry", () => {
  it("trims curves to each circle's rim", () => {
    const curve = curveBetween({ x: 0, y: 0 }, { x: 200, y: 0 }, 20, 30, 0);
    expect(curve.start.x).toBeCloseTo(20);
    expect(curve.end.x).toBeCloseTo(170);
    expect(pointOnCurve(curve, 0.5)).toEqual({ x: 97.5, y: 0 });
  });

  it("moves parallel labels apart instead of stacking them", () => {
    const edges = [
      { id: "a", label: "sold by", source: { x: 0, y: 0 }, target: { x: 300, y: 0 }, sourceRadius: 20, targetRadius: 20, curvature: 0.16 },
      { id: "b", label: "located in", source: { x: 0, y: 4 }, target: { x: 300, y: 4 }, sourceRadius: 20, targetRadius: 20, curvature: 0.16 },
    ];
    const placement = placeEdgeLabels(edges, []);
    const boxFor = (index: 0 | 1) => {
      const edge = edges[index]!;
      const place = placement.get(edge.id)!;
      const curve = curveBetween(edge.source, edge.target, edge.sourceRadius, edge.targetRadius, place.curvature);
      return labelBox(edge.label, pointOnCurve(curve, place.labelT));
    };
    const a = boxFor(0);
    const b = boxFor(1);
    const overlaps =
      Math.min(a.x + a.width, b.x + b.width) > Math.max(a.x, b.x) &&
      Math.min(a.y + a.height, b.y + b.height) > Math.max(a.y, b.y);
    expect(overlaps).toBe(false);
  });
});
