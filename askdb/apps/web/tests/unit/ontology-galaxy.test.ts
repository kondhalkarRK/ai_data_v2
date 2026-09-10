import { describe, expect, it } from "vitest";

import { betweennessCentrality, degreeCentrality, hopNeighborhood, pageRank } from "@/lib/ontology/graph-metrics";
import { convexHull, expandHull, hullToPath } from "@/lib/ontology/hull";

describe("ontology graph metrics", () => {
  const ids = ["a", "b", "c", "d"];
  const links = [
    { source: "a", target: "b", id: "e1" },
    { source: "b", target: "c", id: "e2" },
    { source: "c", target: "d", id: "e3" },
    { source: "a", target: "c", id: "e4" },
  ];

  it("normalizes degree centrality", () => {
    const scores = degreeCentrality(ids, links);
    expect(Math.max(...scores.values())).toBe(1);
    expect(scores.get("c")).toBeGreaterThan(scores.get("d")!);
  });

  it("computes betweenness and pagerank", () => {
    expect(betweennessCentrality(ids, links).get("c")).toBeGreaterThan(0);
    expect(pageRank(ids, links).get("c")).toBeGreaterThan(0);
  });

  it("builds hop neighborhoods with edge ids", () => {
    const one = hopNeighborhood("a", links, 1);
    expect(one.nodes.has("b")).toBe(true);
    expect(one.nodes.has("d")).toBe(false);
    expect(one.edges.has("e1")).toBe(true);
    const two = hopNeighborhood("a", links, 2);
    expect(two.nodes.has("d")).toBe(true);
  });
});

describe("convex hull zones", () => {
  it("builds a closed path around points", () => {
    const hull = expandHull(
      convexHull([
        { x: 0, y: 0 },
        { x: 10, y: 0 },
        { x: 10, y: 10 },
        { x: 0, y: 10 },
        { x: 5, y: 5 },
      ]),
      4,
    );
    expect(hull.length).toBe(4);
    expect(hullToPath(hull)).toContain("Z");
  });
});
