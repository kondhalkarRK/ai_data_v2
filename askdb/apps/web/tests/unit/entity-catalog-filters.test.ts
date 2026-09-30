import { describe, expect, it } from "vitest";

import {
  coverageLabel,
  filterEntities,
  matchReason,
  tablesWithSchemaChanges,
  type CatalogFilter,
} from "@/lib/entity-catalog/filters";
import type { CatalogChange, EntityRow } from "@/lib/entity-catalog/types";

function row(overrides: Partial<EntityRow>): EntityRow {
  return {
    key: "make",
    label: "Make",
    group: "Vehicle",
    table: "automotive.dim_carline",
    column: "make",
    dataType: "text",
    distinctValues: 3,
    newValues: 0,
    lastUpdated: null,
    aiKnown: true,
    readiness: "ai_ready",
    readinessCounts: {},
    aliases: [],
    sampleValues: [],
    newValueNames: [],
    error: null,
    ...overrides,
  };
}

const ROWS = [
  row({ sampleValues: ["Maruti Suzuki", "Tata"], aliases: ["maruti"], newValues: 1, newValueNames: ["BYD"] }),
  row({
    key: "city",
    label: "City",
    group: "Geography",
    table: "automotive.dim_region",
    column: "city",
    sampleValues: ["Pune"],
  }),
  row({
    key: "dealer_name",
    label: "Dealer",
    group: "Dealer",
    table: "automotive.dim_dealer",
    column: "dealer_name",
    aiKnown: false,
    readiness: "needs_review",
  }),
];

function run(query: string, filters: CatalogFilter[] = [], schemaTables: string[] = []) {
  return filterEntities(ROWS, {
    query,
    filters: new Set(filters),
    schemaTables: new Set(schemaTables),
  }).map((r) => r.key);
}

describe("entity catalog filters", () => {
  it("searches entity names, values, aliases and new values", () => {
    expect(run("geograph")).toEqual(["city"]);
    expect(run("pune")).toEqual(["city"]);
    expect(run("maruti")).toEqual(["make"]);
    expect(run("byd")).toEqual(["make"]);
    const make = ROWS[0] as EntityRow;
    expect(matchReason(make, "suzuki")).toBe("value “Maruti Suzuki”");
    expect(matchReason(make, "byd")).toBe("new value “BYD”");
  });

  it("combines group chips with OR and state chips with AND", () => {
    expect(run("", ["Vehicle", "Geography"])).toEqual(["make", "city"]);
    expect(run("", ["Vehicle", "new_values"])).toEqual(["make"]);
    expect(run("", ["needs_review"])).toEqual(["dealer_name"]);
  });

  it("filters to tables with schema changes", () => {
    const changes = [
      { kind: "new_column", table: "automotive.dim_region" },
      { kind: "new_values", table: null },
    ] as CatalogChange[];
    const tables = [...tablesWithSchemaChanges(changes)];
    expect(tables).toEqual(["automotive.dim_region"]);
    expect(run("", ["schema_changes"], tables)).toEqual(["city"]);
  });

  it("formats coverage", () => {
    expect(coverageLabel(null)).toBe("—");
    expect(coverageLabel(0.9234)).toBe("92.3%");
  });
});
