import type { GlossaryTerm, OntologyNode, OntologySnapshot } from "@nql/shared-types";
import { describe, expect, it } from "vitest";

import {
  buildOntologyMap,
  coreConcepts,
  layoutOntologyMap,
  searchOntology,
} from "@/lib/ontology/ontology-map";

function node(
  id: string,
  label: string,
  kind: OntologyNode["kind"],
  tables: string[] = [],
  extra: Partial<OntologyNode> = {},
): OntologyNode {
  return {
    id,
    label,
    kind,
    domain: "automotive",
    synonyms: [],
    tables,
    columns: [],
    relationships: [],
    lineage: [],
    degree: 1,
    cluster: "Actors",
    clusterColor: "#000000",
    ...extra,
  };
}

function term(partial: Partial<GlossaryTerm>): GlossaryTerm {
  return {
    definition: "",
    synonyms: [],
    category: "Product",
    calculationRules: [],
    disambiguation: [],
    relatedTerms: [],
    exampleQuestions: [],
    ...partial,
  };
}

const SNAPSHOT: OntologySnapshot = {
  nodes: [
    node("domain:automotive", "Automotive Sales", "domain"),
    node("table:fact_sales", "Sales Transactions", "table", [], { tableType: "fact" }),
    node("table:dim_carline", "Vehicle / Car Line", "table"),
    node("table:dim_dealer", "Dealer Network", "table"),
    node("table:dim_region", "Region / Geography", "table"),
    node("entity:Sales Transaction", "Sales Transaction", "entity", ["fact_sales"]),
    node("entity:Vehicle", "Vehicle", "entity", ["dim_carline"]),
    node("entity:Dealer", "Dealer", "entity", ["dim_dealer"]),
    node("entity:Region", "Region", "entity", ["dim_region"]),
    node("measure:revenue", "Revenue", "measure", ["fact_sales"]),
    node("measure:units_sold", "Units Sold", "measure", ["fact_sales"]),
  ],
  edges: [
    { id: "d1", source: "domain:automotive", target: "table:fact_sales", kind: "relationship", label: "contains" },
    { id: "r1", source: "table:fact_sales", target: "table:dim_carline", kind: "relationship", label: "Sales to Vehicle" },
    { id: "r2", source: "table:fact_sales", target: "table:dim_dealer", kind: "relationship", label: "Sales to Dealer" },
    { id: "r3", source: "table:dim_dealer", target: "table:dim_region", kind: "relationship", label: "Dealer to Region" },
    { id: "m1", source: "entity:Sales Transaction", target: "table:fact_sales", kind: "maps_to", label: "maps to" },
    { id: "m2", source: "entity:Vehicle", target: "table:dim_carline", kind: "maps_to", label: "maps to" },
    { id: "m3", source: "entity:Dealer", target: "table:dim_dealer", kind: "maps_to", label: "maps to" },
    { id: "m4", source: "entity:Region", target: "table:dim_region", kind: "maps_to", label: "maps to" },
    { id: "s1", source: "measure:revenue", target: "table:fact_sales", kind: "dependency", label: "sourced from" },
    { id: "s2", source: "measure:units_sold", target: "table:fact_sales", kind: "dependency", label: "sourced from" },
  ],
  clusters: [],
  metadata: {
    industry: "automotive",
    version: "1",
    compiledAt: "2026-01-01T00:00:00Z",
    nodeCount: 11,
    edgeCount: 10,
    buildMs: 1,
  },
};

const GLOSSARY: Record<string, GlossaryTerm> = {
  Revenue: term({ category: "Financial", mapsToMeasure: "revenue", synonyms: ["turnover"] }),
  "Car Type": term({ mapsToAttribute: "dim_carline.car_type", sqlExpression: "automotive.dim_carline.car_type" }),
  SUV: term({
    category: "Product Filter",
    mapsToAttribute: "dim_carline.car_type",
    sqlExpression: "automotive.dim_carline.car_type = 'SUV'",
    synonyms: ["SUVs"],
  }),
  Sedan: term({
    category: "Product Filter",
    mapsToAttribute: "dim_carline.car_type",
    sqlExpression: "automotive.dim_carline.car_type = 'Sedan'",
  }),
  Hatchback: term({
    category: "Product Filter",
    mapsToAttribute: "dim_carline.car_type",
    sqlExpression: "automotive.dim_carline.car_type = 'Hatchback'",
  }),
  "Electric Vehicle": term({
    mapsToDimension: "Car",
    sqlExpression: "automotive.dim_carline.engine_type = 'Electric'",
    synonyms: ["EV"],
  }),
  Brand: term({ mapsToAttribute: "dim_carline.make", sqlExpression: "automotive.dim_carline.make" }),
  "Market Share": term({ category: "Market" }),
  Profit: term({ category: "Financial", definition: "Not available: no cost data." }),
};

describe("ontology map model", () => {
  const map = buildOntologyMap(SNAPSHOT, GLOSSARY);
  const byLabel = new Map(map.graph.nodes.map((item) => [item.label, item]));
  const edge = (from: string, to: string) =>
    map.graph.edges.find(
      (item) => item.source === byLabel.get(from)?.id && item.target === byLabel.get(to)?.id,
    );

  it("shows business concepts, not physical tables or the industry hub", () => {
    expect(map.graph.nodes.some((item) => item.kind === "table" || item.kind === "domain")).toBe(false);
    expect(byLabel.has("Sales Transaction")).toBe(true);
    expect(byLabel.has("Vehicle")).toBe(true);
  });

  it("adds glossary terms as concepts linked to what they classify", () => {
    expect(edge("SUV", "Car Type")?.label).toBe("is a kind of");
    expect(edge("Car Type", "Vehicle")?.label).toBe("describes");
    expect(edge("Brand", "Vehicle")?.label).toBe("describes");
    expect(edge("Electric Vehicle", "Vehicle")?.label).toBe("is a kind of");
    expect(edge("Market Share", "Revenue")?.label).toBe("calculated from");
  });

  it("merges glossary terms that already exist and skips data the model does not have", () => {
    expect(map.graph.nodes.filter((item) => item.label === "Revenue")).toHaveLength(1);
    expect(byLabel.get("Revenue")?.synonyms).toContain("turnover");
    expect(byLabel.has("Profit")).toBe(false);
  });

  it("places every concept in a business domain and flags links across domains", () => {
    expect(byLabel.get("SUV")?.cluster).toBe("vehicle");
    expect(byLabel.get("Revenue")?.cluster).toBe("sales");
    expect(byLabel.get("Dealer")?.cluster).toBe("dealer");
    expect(byLabel.get("Region")?.cluster).toBe("geography");
    expect(map.domains.map((domain) => domain.id)).not.toContain("other");
    const salesToVehicle = edge("Sales Transaction", "Vehicle")!;
    expect(map.crossEdges.has(salesToVehicle.id)).toBe(true);
    expect(map.crossEdges.has(edge("SUV", "Car Type")!.id)).toBe(false);
    expect(map.bridges[0]!.count).toBeGreaterThan(0);
  });

  it("ranks business entities above classifiers with many sub-types", () => {
    const cores = coreConcepts(map.graph, 3).map((id) => map.graph.nodes.find((item) => item.id === id)!.label);
    expect(cores).toContain("Sales Transaction");
    expect(cores).toContain("Vehicle");
    expect(cores).not.toContain("Car Type");
  });

  it("search highlights the match and the route to the core concepts", () => {
    const cores = coreConcepts(map.graph, 4);
    const result = searchOntology(map.graph, "SUV", cores)!;
    const related = [...result.related].map((id) => map.graph.nodes.find((item) => item.id === id)!.label);
    expect([...result.matches]).toEqual([byLabel.get("SUV")!.id]);
    expect(related).toEqual(expect.arrayContaining(["Car Type", "Vehicle", "Sales Transaction"]));
  });

  it("short searches match whole words only", () => {
    const result = searchOntology(map.graph, "EV", [])!;
    expect([...result.matches]).toEqual([byLabel.get("Electric Vehicle")!.id]);
    expect(searchOntology(map.graph, "  ", [])).toBeNull();
  });

  it.each(["force", "centrality", "hierarchy"] as const)("lays out every concept (%s)", (style) => {
    const placed = layoutOntologyMap(map, style);
    expect(placed).toHaveLength(map.graph.nodes.length);
    expect(placed.every((item) => Number.isFinite(item.x) && Number.isFinite(item.y))).toBe(true);
  });

  it("centrality mode makes core concepts bigger than leaf concepts", () => {
    const placed = new Map(layoutOntologyMap(map, "centrality").map((item) => [item.label, item]));
    expect(placed.get("Sales Transaction")!.radius).toBeGreaterThan(placed.get("Hatchback")!.radius);
  });
});
