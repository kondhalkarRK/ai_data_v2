import { describe, expect, it } from "vitest";

import type { AnalyticsSpec } from "@nql/shared-types";

import { formatQuerySentence, recommendViz } from "@/lib/analytics/helpers";

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

describe("formatQuerySentence", () => {
  it("describes metrics, dimensions, and filters", () => {
    const sentence = formatQuerySentence({
      ...base,
      dimensions: ["month", "region"],
      filters: [{ domain: "car_type", values: ["SUV"] }],
      analysis: "top_n",
      limit: 10,
    });
    expect(sentence).toContain("Top Revenue by Month and Region");
    expect(sentence).toContain("SUV");
    expect(sentence).toContain("10");
  });

  it("prompts when no metric is selected", () => {
    expect(formatQuerySentence({ ...base, metrics: [] })).toMatch(/Select a metric/);
  });

  it("includes a custom date range", () => {
    const sentence = formatQuerySentence({
      ...base,
      datePreset: "custom",
      dateFrom: "2026-01-01",
      dateTo: "2026-01-31",
    });
    expect(sentence).toContain("2026-01-01 → 2026-01-31");
  });
});
