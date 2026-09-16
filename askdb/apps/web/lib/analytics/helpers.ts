import type { AnalyticsSpec, AnalyticsVizKind } from "@nql/shared-types";

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
