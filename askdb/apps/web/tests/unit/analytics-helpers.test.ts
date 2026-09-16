import { describe, expect, it } from "vitest";

import type { AnalyticsSpec } from "@nql/shared-types";

import { recommendViz } from "@/lib/analytics/helpers";

const base: AnalyticsSpec = {
  metrics: ["revenue"],
  dimensions: [],
  filters: [],
  analysis: "basic",
  limit: 25,
  orderDirection: "desc",
  viz: "auto",
};

describe("analytics recommendViz", () => {
  it("suggests kpi for metric-only", () => {
    expect(recommendViz(base)).toBe("kpi");
  });

  it("suggests line for time trends", () => {
    expect(recommendViz({ ...base, dimensions: ["month"], analysis: "trend" })).toBe("line");
  });

  it("respects explicit viz override", () => {
    expect(recommendViz({ ...base, viz: "table" })).toBe("table");
  });
});
