import type { AnalyticsSpec, AnalyticsVizKind } from "@nql/shared-types";

const ANALYSIS_PHRASE: Partial<Record<AnalyticsSpec["analysis"], string>> = {
  top_n: "Top",
  bottom_n: "Bottom",
  ranking: "Ranked",
  contribution: "Contribution of",
  running_total: "Running total of",
  moving_average: "Moving average of",
  period_growth: "Growth in",
  trend: "Trend of",
  variance: "Variance of",
};

export function formatQuerySentence(
  spec: AnalyticsSpec,
  labels?: { metrics?: Record<string, string>; dimensions?: Record<string, string> },
): string {
  if (!spec.metrics.length) return "Select a metric to start an analysis.";
  const metricNames = spec.metrics.map((id) => labels?.metrics?.[id] ?? prettyLabel(id));
  const metricPart = metricNames.join(" + ");
  const prefix = ANALYSIS_PHRASE[spec.analysis];
  const head = prefix ? `${prefix} ${metricPart}` : metricPart;
  const dimNames = spec.dimensions.map((id) => labels?.dimensions?.[id] ?? prettyLabel(id));
  const by = dimNames.length ? ` by ${joinList(dimNames)}` : "";
  const filters = spec.filters
    .flatMap((f) => f.values.map((v) => v))
    .filter(Boolean);
  const filterPart = filters.length ? ` · ${filters.join(", ")}` : "";
  const limitPart =
    spec.analysis === "top_n" || spec.analysis === "bottom_n" || spec.analysis === "ranking"
      ? ` · ${spec.limit}`
      : "";
  return `${head}${by}${filterPart}${limitPart}`;
}

function joinList(items: string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

export function prettyLabel(id: string): string {
  return id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const TIME = new Set(["month", "quarter", "year", "date"]);

export function recommendViz(spec: AnalyticsSpec): AnalyticsVizKind {
  if (spec.viz !== "auto") return spec.viz;

  const metrics = spec.metrics.length;
  const dims = spec.dimensions.map((d) => d.toLowerCase());
  const dimCount = dims.length;
  const hasTime = dims.some((d) => TIME.has(d) || d.includes("month") || d.includes("date"));

  if (spec.analysis === "contribution") return "donut";
  if (spec.analysis === "top_n" || spec.analysis === "bottom_n" || spec.analysis === "ranking") {
    return "bar";
  }
  if (
    spec.analysis === "trend" ||
    spec.analysis === "running_total" ||
    spec.analysis === "moving_average" ||
    spec.analysis === "period_growth"
  ) {
    return "line";
  }
  if (metrics === 1 && dimCount === 0) return "kpi";
  if (metrics >= 2 && dimCount === 1) return "scatter";
  if (hasTime && dimCount <= 2) return spec.analysis === "running_total" ? "area" : "line";
  if (dimCount === 1) return "bar";
  if (dimCount >= 2) return "table";
  return "bar";
}

export function csvEscape(value: string): string {
  if (/[",\n]/.test(value)) return `"${value.replace(/"/g, '""')}"`;
  return value;
}

export function downloadCsv(
  filename: string,
  columns: string[],
  rows: Array<Record<string, unknown>>,
): void {
  const header = columns.join(",");
  const body = rows
    .map((row) => columns.map((column) => csvEscape(String(row[column] ?? ""))).join(","))
    .join("\n");
  const blob = new Blob([`${header}\n${body}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
