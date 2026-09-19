import type { OntologyNode, OntologySnapshot } from "@nql/shared-types";
import { describe, expect, it } from "vitest";

import {
  displayName,
  journeyNodeIds,
  matchesDiscoveryQuery,
  snapshotTrustRate,
  storyVerb,
} from "@/lib/ontology/asset-context";

const revenue: OntologyNode = {
  id: "measure:revenue",
  label: "Revenue",
  kind: "measure",
  domain: "Sales",
  description: "Gross sales revenue",
  physicalName: "m_revenue",
  synonyms: ["sales dollars"],
  tables: ["fact_sales"],
  columns: [],
  relationships: [],
  lineage: [],
  degree: 6,
  cluster: "Sales",
  clusterColor: "#2563eb",
};

const dealer: OntologyNode = {
  id: "entity:dealer",
  label: "Dealer",
  kind: "entity",
  domain: "Sales",
  physicalName: "dim_dealer",
  synonyms: [],
  tables: ["dim_dealer"],
  columns: [{ name: "dealer_id", displayName: "Dealer ID", type: "int", role: "key" }],
  relationships: [],
  lineage: [],
  degree: 3,
  cluster: "Sales",
  clusterColor: "#2563eb",
};

const snapshot: OntologySnapshot = {
  nodes: [revenue, dealer],
  edges: [
    {
      id: "e1",
      source: "measure:revenue",
      target: "entity:dealer",
      kind: "reference",
      label: "by dealer",
    },
  ],
  clusters: [],
  metadata: {
    industry: "automotive",
    version: "1",
    compiledAt: "2026-01-01T00:00:00.000Z",
    nodeCount: 2,
    edgeCount: 1,
    buildMs: 1,
  },
};

describe("asset-context", () => {
  it("matches discovery queries on synonyms and columns", () => {
    expect(matchesDiscoveryQuery(revenue, "Revenue")).toBe(true);
    expect(matchesDiscoveryQuery(revenue, "sales dollars")).toBe(true);
    expect(matchesDiscoveryQuery(dealer, "dealer_id")).toBe(true);
    expect(matchesDiscoveryQuery(dealer, "premium")).toBe(false);
  });

  it("builds a revenue journey from seeds", () => {
    expect(journeyNodeIds(snapshot, ["revenue", "dealer"])).toEqual([
      "measure:revenue",
      "entity:dealer",
    ]);
  });

  it("uses physical names in technical overlay", () => {
    expect(displayName(revenue, "technical")).toBe("m_revenue");
    expect(displayName(revenue, "business")).toBe("Revenue");
  });

  it("tells a join story for references", () => {
    expect(storyVerb(snapshot.edges[0])).toBe("Joined through");
    expect(snapshotTrustRate(snapshot)).toBe(100);
  });
});
