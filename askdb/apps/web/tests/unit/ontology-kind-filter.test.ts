import { describe, expect, it } from "vitest";

import {
  isFactNode,
  nodeMatchesKindFilter,
  nodeMatchesKindFilters,
  type OntologyKindFilter,
} from "@/lib/ontology/kind-filter";

describe("ontology kind filter", () => {
  const measure = { id: "m_revenue", kind: "measure" as const, tableType: undefined, degree: 2 };
  const dimension = { id: "d_region", kind: "dimension" as const, tableType: undefined, degree: 1 };
  const entity = { id: "e_customer", kind: "entity" as const, tableType: undefined, degree: 3 };
  const fact = { id: "t_fact_sales", kind: "table" as const, tableType: "fact", degree: 5 };
  const dimTable = { id: "t_dim_date", kind: "table" as const, tableType: "dimension", degree: 2 };
  const isolated = { id: "orphan", kind: "entity" as const, tableType: undefined, degree: 0 };

  it("detects fact tables", () => {
    expect(isFactNode(fact)).toBe(true);
    expect(isFactNode(dimTable)).toBe(false);
    expect(isFactNode({ id: "x_fact_y", kind: "table", tableType: undefined })).toBe(true);
  });

  it("matches entity type filters", () => {
    const cases: Array<[OntologyKindFilter, boolean, boolean, boolean, boolean]> = [
      ["all", true, true, true, true],
      ["measure", true, false, false, false],
      ["dimension", false, true, false, false],
      ["entity", false, false, true, false],
      ["fact", false, false, false, true],
    ];
    for (const [filter, m, d, e, f] of cases) {
      expect(nodeMatchesKindFilter(measure, filter)).toBe(m);
      expect(nodeMatchesKindFilter(dimension, filter)).toBe(d);
      expect(nodeMatchesKindFilter(entity, filter)).toBe(e);
      expect(nodeMatchesKindFilter(fact, filter)).toBe(f);
    }
  });

  it("keeps connected nodes for relationship filter", () => {
    expect(nodeMatchesKindFilter(entity, "relationship")).toBe(true);
    expect(nodeMatchesKindFilter(isolated, "relationship")).toBe(false);
  });

  it("matches any selected category and treats all as a clear", () => {
    expect(nodeMatchesKindFilters(measure, ["all"])).toBe(true);
    expect(nodeMatchesKindFilters(measure, ["entity", "measure"])).toBe(true);
    expect(nodeMatchesKindFilters(dimension, ["entity", "measure"])).toBe(false);
    expect(nodeMatchesKindFilters(isolated, ["relationship"])).toBe(false);
  });
});
