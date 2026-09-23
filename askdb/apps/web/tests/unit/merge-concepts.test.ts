import type { OntologyNode, OntologySnapshot } from "@nql/shared-types";
import { describe, expect, it } from "vitest";

import { mergeOntologyConcepts, normalizeConceptKey, withoutDomainNodes } from "@/lib/ontology/merge-concepts";

function node(partial: Partial<OntologyNode> & Pick<OntologyNode, "id" | "label" | "kind">): OntologyNode {
  return {
    domain: "Sales",
    description: "",
    physicalName: partial.id,
    synonyms: [],
    tables: [],
    columns: [],
    relationships: [],
    lineage: [],
    degree: 1,
    cluster: "Entities",
    clusterColor: "#059669",
    ...partial,
  };
}

describe("mergeOntologyConcepts", () => {
  it("collapses Vehicle entity and Vehicle table into one concept", () => {
    const snapshot: OntologySnapshot = {
      nodes: [
        node({ id: "entity:vehicle", label: "Vehicle", kind: "entity", cluster: "Entities" }),
        node({
          id: "table:dim_vehicle",
          label: "Vehicle",
          kind: "table",
          cluster: "Dimensions",
          tableType: "dimension",
        }),
        node({ id: "entity:dealer", label: "Dealer", kind: "entity", cluster: "Entities" }),
      ],
      edges: [
        {
          id: "e1",
          source: "entity:dealer",
          target: "table:dim_vehicle",
          kind: "reference",
          label: "sells",
        },
        {
          id: "e2",
          source: "entity:vehicle",
          target: "table:dim_vehicle",
          kind: "maps_to",
          label: "same concept",
        },
      ],
      clusters: [],
      metadata: {
        industry: "automotive",
        version: "1",
        compiledAt: "2026-01-01T00:00:00.000Z",
        nodeCount: 3,
        edgeCount: 2,
        buildMs: 1,
      },
    };

    const merged = mergeOntologyConcepts(snapshot);
    const vehicles = merged.nodes.filter((item) => normalizeConceptKey(item.label) === "vehicle");
    expect(vehicles).toHaveLength(1);
    expect(merged.nodes.map((item) => item.label).sort()).toEqual(["Dealer", "Vehicle"]);
    expect(merged.edges.some((edge) => edge.source === edge.target)).toBe(false);
    expect(merged.nodes.find((item) => item.label === "Vehicle")?.cluster).toBe("Actors");
    expect(merged.clusters.some((cluster) => cluster.id === "Facts")).toBe(false);
  });

  it("drops the industry domain node and its edges", () => {
    const snapshot: OntologySnapshot = {
      nodes: [
        node({ id: "domain:automotive", label: "Automotive Sales", kind: "domain", cluster: "Domain" }),
        node({ id: "entity:dealer", label: "Dealer", kind: "entity" }),
      ],
      edges: [
        {
          id: "contains",
          source: "domain:automotive",
          target: "entity:dealer",
          kind: "dependency",
          label: "contains",
        },
      ],
      clusters: [
        { id: "Domain", label: "Domain", color: "#0f766e" },
        { id: "Entities", label: "Entities", color: "#059669" },
      ],
      metadata: {
        industry: "automotive",
        version: "1",
        compiledAt: "2026-01-01T00:00:00.000Z",
        nodeCount: 2,
        edgeCount: 1,
        buildMs: 1,
      },
    };
    const graph = withoutDomainNodes(snapshot);
    expect(graph.nodes.map((item) => item.label)).toEqual(["Dealer"]);
    expect(graph.edges).toHaveLength(0);
    expect(graph.clusters.some((cluster) => cluster.id === "Domain")).toBe(false);
  });
});
