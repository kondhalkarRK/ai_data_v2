import { describe, expect, it } from "vitest";

import type { AnalyticsSpec } from "@nql/shared-types";

import {
  applyFix,
  formatCell,
  formatQuerySentence,
  normalizeSpec,
  recommendViz,
} from "@/lib/analytics/helpers";

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

  it("uses bars for single-series growth", () => {
    expect(recommendViz({ ...base, dimensions: ["month"], analysis: "yoy_growth" })).toBe("bar");
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

  it("names relative presets and the moving-average window", () => {
    const sentence = formatQuerySentence({
      ...base,
      dimensions: ["month"],
      analysis: "moving_average",
      window: 6,
      datePreset: "last_12_months",
    });
    expect(sentence).toContain("Last 12 months");
    expect(sentence).toContain("6-period window");
  });
});

describe("applyFix", () => {
  it("adds a time grain first and replaces any other grain", () => {
    const next = applyFix({ ...base, dimensions: ["salesperson", "year"] }, {
      label: "Add Month",
      action: "add_dimension",
      value: "month",
    });
    expect(next.dimensions).toEqual(["month", "salesperson"]);
  });

  it("switches metric and analysis, and clears dates", () => {
    expect(applyFix(base, { label: "", action: "set_metric", value: "units_sold" }).metrics).toEqual([
      "units_sold",
    ]);
    expect(applyFix(base, { label: "", action: "set_analysis", value: "top_n_per_group" }).analysis).toBe(
      "top_n_per_group",
    );
    const cleared = applyFix({ ...base, datePreset: "custom", dateFrom: "2026-01-01" }, {
      label: "",
      action: "clear_date",
    });
    expect(cleared.datePreset).toBeNull();
    expect(cleared.dateFrom).toBeNull();
  });
});

describe("normalizeSpec", () => {
  it("maps first-release presets and analyses", () => {
    const next = normalizeSpec({ ...base, analysis: "breakdown", datePreset: "last_30", dateFrom: "2020-01-01" }, base);
    expect(next.analysis).toBe("basic");
    expect(next.datePreset).toBe("last_30_days");
    expect(next.dateFrom).toBeNull();
    expect(normalizeSpec({ ...base, datePreset: "yoy" }, base).datePreset).toBeNull();
  });
});

describe("formatCell", () => {
  it("formats rupees, percentages and dates", () => {
    expect(formatCell(25_000_000, "revenue", "currency")).toBe("₹2.50 Cr");
    expect(formatCell(12.345, "yoy_growth_pct")).toBe("12.3%");
    expect(formatCell("2026-03-01", "month")).toBe("2026-03-01");
    expect(formatCell(null, "revenue")).toBe("—");
  });
});
