import { describe, expect, it } from "vitest";

import {
  categoryLabelForCluster,
  conceptCategory,
  CONCEPT_CATEGORIES,
  isFactNode,
  nodeMatchesKindFilter,
  nodeMatchesKindFilters,
  type OntologyKindFilter,
} from "@/lib/ontology/kind-filter";

describe("ontology concept categories", () => {
  const measure = { id: "m_revenue", kind: "measure" as const, tableType: undefined };
  const dimension = { id: "d_date", kind: "dimension" as const, tableType: undefined };
  const entity = { id: "e_customer", kind: "entity" as const, tableType: undefined };
  const fact = { id: "t_fact_sales", kind: "table" as const, tableType: "fact" };
  const dimTable = { id: "t_dim_dealer", kind: "table" as const, tableType: "dimension" };

  it("detects fact tables", () => {
    expect(isFactNode(fact)).toBe(true);
    expect(isFactNode(dimTable)).toBe(false);
    expect(isFactNode({ id: "x_fact_y", kind: "table", tableType: undefined })).toBe(true);
  });

  it("puts every concept in exactly one business category", () => {
    expect(conceptCategory(fact)).toBe("events");
    expect(conceptCategory(measure)).toBe("kpis");
    expect(conceptCategory(dimension)).toBe("breakdowns");
    expect(conceptCategory(entity)).toBe("entities");
    expect(conceptCategory(dimTable)).toBe("entities");
  });

  it("uses distinct business labels and no governance category", () => {
    const labels = CONCEPT_CATEGORIES.map((item) => item.label);
    expect(new Set(labels).size).toBe(labels.length);
    expect(labels.join(" ").toLowerCase()).not.toContain("governance");
    expect(categoryLabelForCluster("Actors")).toBe("Business Entities");
    expect(categoryLabelForCluster("Outcomes")).toBe("KPIs");
  });

  it("matches category filters", () => {
    const cases: Array<[OntologyKindFilter, boolean, boolean, boolean, boolean]> = [
      ["all", true, true, true, true],
      ["kpis", true, false, false, false],
      ["breakdowns", false, true, false, false],
      ["entities", false, false, true, false],
      ["events", false, false, false, true],
    ];
    for (const [filter, m, d, e, f] of cases) {
      expect(nodeMatchesKindFilter(measure, filter)).toBe(m);
      expect(nodeMatchesKindFilter(dimension, filter)).toBe(d);
      expect(nodeMatchesKindFilter(entity, filter)).toBe(e);
      expect(nodeMatchesKindFilter(fact, filter)).toBe(f);
    }
  });

  it("matches any selected category and treats all as a clear", () => {
    expect(nodeMatchesKindFilters(measure, ["all"])).toBe(true);
    expect(nodeMatchesKindFilters(measure, [])).toBe(true);
    expect(nodeMatchesKindFilters(measure, ["entities", "kpis"])).toBe(true);
    expect(nodeMatchesKindFilters(dimension, ["entities", "kpis"])).toBe(false);
  });
});
