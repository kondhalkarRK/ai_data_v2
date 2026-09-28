import type { OntologyNode, OntologySnapshot } from "@nql/shared-types";
import { describe, expect, it } from "vitest";

import { buildKnowledgeGraph, knowledgeCategory, knowledgeVisibleIds } from "@/lib/ontology/knowledge-graph";

function node(
  id: string,
  label: string,
  kind: OntologyNode["kind"],
  cluster: string,
  extra: Partial<OntologyNode> = {},
): OntologyNode {
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
    ...extra,
  };
}

const SNAPSHOT: OntologySnapshot = {
  nodes: [
    node("domain", "Automotive", "domain", "Domain"),
    node("vehicle", "Vehicle", "entity", "Actors"),
    node("dealer", "Dealer", "entity", "Actors"),
    node("car-line", "Vehicle / Car Line", "table", "Context", { tableType: "dimension" }),
    node("sale", "Sales Transactions", "table", "Events", { tableType: "fact" }),
    node("sale-entity", "Sales Transaction", "entity", "Actors"),
    node("revenue", "Revenue", "measure", "Outcomes"),
    node("date", "Date", "dimension", "Attributes"),
  ],
  edges: [
    { id: "0", source: "domain", target: "vehicle", kind: "dependency", label: "contains" },
    { id: "1", source: "vehicle", target: "car-line", kind: "maps_to", label: "represented by" },
    { id: "2", source: "sale", target: "dealer", kind: "reference", label: "sold by" },
    { id: "3", source: "sale-entity", target: "vehicle", kind: "reference", label: "for product" },
    { id: "4", source: "revenue", target: "sale", kind: "maps_to", label: "measured from" },
    { id: "5", source: "date", target: "sale", kind: "maps_to", label: "describes" },
  ],
  clusters: [],
  metadata: {
    industry: "automotive",
    version: "1",
    compiledAt: "2026-01-01T00:00:00.000Z",
    nodeCount: 8,
    edgeCount: 6,
    buildMs: 1,
  },
};

describe("knowledge graph", () => {
  const graph = buildKnowledgeGraph(SNAPSHOT);
  const byLabel = (label: string) => graph.nodes.find((item) => item.label === label);

  it("keeps actor, entity, event, attribute and outcome as distinct roles", () => {
    expect(knowledgeCategory(byLabel("Vehicle")!)).toBe("actor");
    expect(knowledgeCategory(byLabel("Car Line")!)).toBe("entity");
    expect(knowledgeCategory(byLabel("Sales Transaction")!)).toBe("event");
    expect(knowledgeCategory(byLabel("Revenue")!)).toBe("outcome");
    expect(knowledgeCategory(byLabel("Date")!)).toBe("attribute");
  });

  it("drops the domain hub and only merges concepts with the same business name", () => {
    expect(graph.nodes.some((item) => item.kind === "domain")).toBe(false);
    expect(graph.nodes.filter((item) => item.label === "Sales Transaction")).toHaveLength(1);
    expect(byLabel("Vehicle")).toBeDefined();
    expect(byLabel("Car Line")).toBeDefined();
    expect(graph.metadata.nodeCount).toBe(graph.nodes.length);
  });

  it("names relationships by role", () => {
    const vehicle = byLabel("Vehicle")!;
    const carLine = byLabel("Car Line")!;
    const edge = graph.edges.find((item) => item.source === vehicle.id && item.target === carLine.id);
    expect(edge?.label).toBe("recorded as");
    const revenue = byLabel("Revenue")!;
    expect(graph.edges.find((item) => item.source === revenue.id)?.label).toBe("measured from");
  });

  it("Connected widens a role to its direct neighbours", () => {
    const outcomesOnly = knowledgeVisibleIds(graph, ["outcome"])!;
    expect([...outcomesOnly].map((id) => graph.nodes.find((item) => item.id === id)!.label)).toEqual(["Revenue"]);
    const withNeighbours = knowledgeVisibleIds(graph, ["outcome", "connected"])!;
    expect(withNeighbours.has(byLabel("Sales Transaction")!.id)).toBe(true);
    expect(knowledgeVisibleIds(graph, ["all"])).toBeNull();
  });
});
