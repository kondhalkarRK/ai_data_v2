import type { AnalyticsFix, AnalyticsSpec, AnalyticsVizKind } from "@nql/shared-types";

const ANALYSIS_PHRASE: Partial<Record<AnalyticsSpec["analysis"], string>> = {
  top_n: "Top",
  bottom_n: "Bottom",
  top_n_per_group: "Top within group:",
  ranking: "Ranked",
  contribution: "Share of",
  running_total: "Running total of",
  moving_average: "Moving average of",
  period_growth: "Period growth in",
  yoy_growth: "YoY growth in",
  growth_contribution: "Growth drivers of",
  actual_vs_target: "Actual vs target for",
  above_average: "Above-average",
  comparison: "Compare",
  trend: "Trend of",
  variance: "Above-average",
};

/** Analyses that use only the first metric. */
export const SINGLE_METRIC_ANALYSES = new Set<AnalyticsSpec["analysis"]>([
  "top_n",
  "bottom_n",
  "top_n_per_group",
  "ranking",
  "contribution",
  "running_total",
  "moving_average",
  "period_growth",
  "yoy_growth",
  "growth_contribution",
  "actual_vs_target",
  "above_average",
  "variance",
]);

export const LIMITED_ANALYSES = new Set<AnalyticsSpec["analysis"]>([
  "top_n",
  "bottom_n",
  "top_n_per_group",
  "ranking",
  "contribution",
  "growth_contribution",
  "above_average",
  "basic",
]);

export function formatQuerySentence(
  spec: AnalyticsSpec,
  labels?: {
    metrics?: Record<string, string>;
    dimensions?: Record<string, string>;
    dates?: Record<string, string>;
  },
): string {
  if (!spec.metrics.length) return "Select a metric to start an analysis.";
  const metricIds = SINGLE_METRIC_ANALYSES.has(spec.analysis) ? spec.metrics.slice(0, 1) : spec.metrics;
  const metricNames = metricIds.map((id) => labels?.metrics?.[id] ?? prettyLabel(id));
  const metricPart = metricNames.join(" + ");
  const prefix = ANALYSIS_PHRASE[spec.analysis];
  const head = prefix ? `${prefix} ${metricPart}` : metricPart;
  const dimNames = spec.dimensions.map((id) => labels?.dimensions?.[id] ?? prettyLabel(id));
  const by = dimNames.length ? ` by ${joinList(dimNames)}` : "";
  const filters = spec.filters.flatMap((f) => f.values).filter(Boolean);
  const filterPart = filters.length ? ` · ${filters.join(", ")}` : "";
  const date = formatDateRangeLabel(spec, labels?.dates);
  const datePart = date ? ` · ${date}` : "";
  const extra =
    spec.analysis === "moving_average"
      ? ` · ${spec.window ?? 3}-period window`
      : ["top_n", "bottom_n", "ranking", "top_n_per_group"].includes(spec.analysis)
        ? ` · ${spec.limit}`
        : "";
  return `${head}${by}${filterPart}${datePart}${extra}`;
}

/** Fallback labels; the API's capabilities list is the source of truth. */
export const DATE_PRESETS: Array<{ id: string; label: string }> = [
  { id: "last_7_days", label: "Last 7 days" },
  { id: "last_30_days", label: "Last 30 days" },
  { id: "last_3_months", label: "Last 3 months" },
  { id: "last_6_months", label: "Last 6 months" },
  { id: "last_12_months", label: "Last 12 months" },
  { id: "last_24_months", label: "Last 24 months" },
  { id: "this_month", label: "This month" },
  { id: "last_month", label: "Last month" },
  { id: "this_quarter", label: "This quarter" },
  { id: "last_quarter", label: "Last quarter" },
  { id: "ytd", label: "Year to date" },
  { id: "fytd", label: "Fiscal year to date" },
  { id: "last_year", label: "Last year" },
  { id: "custom", label: "Custom range" },
];

/** Presets saved by the first builder release, mapped to current ids. */
const LEGACY_PRESETS: Record<string, string | null> = {
  last_7: "last_7_days",
  last_30: "last_30_days",
  this_year: "ytd",
  today: "last_7_days",
  yesterday: "last_7_days",
  yoy: null,
  mom: null,
  qoq: null,
};

export function normalizeSpec(spec: Partial<AnalyticsSpec>, base: AnalyticsSpec): AnalyticsSpec {
  const preset = spec.datePreset ?? null;
  const datePreset = preset && preset in LEGACY_PRESETS ? LEGACY_PRESETS[preset] : preset;
  const analysis =
    spec.analysis === "breakdown" ? "basic" : spec.analysis === "variance" ? "above_average" : spec.analysis;
  return {
    ...base,
    ...spec,
    metrics: spec.metrics ?? [],
    dimensions: spec.dimensions ?? [],
    filters: spec.filters ?? [],
    analysis: analysis ?? "basic",
    datePreset,
    dateFrom: datePreset === "custom" ? (spec.dateFrom ?? null) : null,
    dateTo: datePreset === "custom" ? (spec.dateTo ?? null) : null,
    rankMethod: spec.rankMethod ?? base.rankMethod ?? "rank",
    window: spec.window ?? base.window ?? 3,
  };
}

export function formatDateRangeLabel(
  spec: Pick<AnalyticsSpec, "datePreset" | "dateFrom" | "dateTo">,
  labels?: Record<string, string>,
): string {
  if (!spec.datePreset) return "";
  if (spec.datePreset === "custom") {
    return spec.dateFrom && spec.dateTo ? `${spec.dateFrom} → ${spec.dateTo}` : "Custom range";
  }
  return (
    labels?.[spec.datePreset] ??
    DATE_PRESETS.find((item) => item.id === spec.datePreset)?.label ??
    prettyLabel(spec.datePreset)
  );
}

/** Apply a one-click fix from the validator to the spec. */
export function applyFix(spec: AnalyticsSpec, fix: AnalyticsFix): AnalyticsSpec {
  const value = fix.value ?? "";
  switch (fix.action) {
    case "add_dimension":
      if (!value || spec.dimensions.includes(value)) return spec;
      return {
        ...spec,
        dimensions: TIME_GRAINS.has(value)
          ? [value, ...spec.dimensions.filter((d) => !TIME_GRAINS.has(d))]
          : [...spec.dimensions, value],
      };
    case "remove_dimension":
      return { ...spec, dimensions: spec.dimensions.filter((d) => d !== value) };
    case "set_analysis":
      return { ...spec, analysis: value as AnalyticsSpec["analysis"] };
    case "set_metric":
      return { ...spec, metrics: [value, ...spec.metrics.filter((m) => m !== value)].slice(0, 1) };
    case "remove_filter":
      return { ...spec, filters: spec.filters.filter((f) => f.domain !== value) };
    case "clear_date":
      return { ...spec, datePreset: null, dateFrom: null, dateTo: null };
    default:
      return spec;
  }
}

function joinList(items: string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

export function prettyLabel(id: string): string {
  return id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const TIME_GRAINS = new Set(["month", "quarter", "year"]);
const TIME = new Set(["month", "quarter", "year", "date"]);

export function recommendViz(spec: AnalyticsSpec): AnalyticsVizKind {
  if (spec.viz !== "auto") return spec.viz;

  const metrics = spec.metrics.length;
  const dims = spec.dimensions.map((d) => d.toLowerCase());
  const dimCount = dims.length;
  const hasTime = dims.some((d) => TIME.has(d) || d.includes("month") || d.includes("date"));

  if (spec.analysis === "contribution") return hasTime ? "line" : "pie";
  if (["top_n", "bottom_n", "ranking", "top_n_per_group", "growth_contribution"].includes(spec.analysis)) {
    return "bar";
  }
  if (["trend", "running_total", "moving_average"].includes(spec.analysis)) return "line";
  if (["period_growth", "yoy_growth"].includes(spec.analysis)) return dimCount > 1 ? "line" : "bar";
  if (metrics === 1 && dimCount === 0) return "kpi";
  if (hasTime && dimCount <= 2) return "line";
  if (dimCount === 1) return "bar";
  if (dimCount >= 2) return "table";
  return "bar";
}

const PERCENT_COLUMN = /(_pct|_share|_rate|achievement)$/;

/** Display value for tables and tooltips; currency follows the metric format. */
export function formatCell(value: unknown, column: string, metricFormat?: string): string {
  if (value == null || value === "") return "—";
  if (typeof value !== "number") {
    const text = String(value);
    return /^\d{4}-\d{2}-\d{2}(T00:00:00)?$/.test(text) ? text.slice(0, 10) : text;
  }
  if (PERCENT_COLUMN.test(column) || column.endsWith("_pct")) return `${value.toFixed(1)}%`;
  if (column === "rank" || column === "dense_rank" || column === "row_number" || column === "year") {
    return String(value);
  }
  const currency =
    metricFormat === "currency" &&
    !/(units|orders|count|salespeople)/.test(column) &&
    Math.abs(value) >= 1000;
  if (currency) return formatInr(value);
  return Number.isInteger(value)
    ? value.toLocaleString("en-IN")
    : value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export function formatInr(value: number): string {
  const size = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (size >= 1e7) return `${sign}₹${(size / 1e7).toFixed(2)} Cr`;
  if (size >= 1e5) return `${sign}₹${(size / 1e5).toFixed(2)} L`;
  return `${sign}₹${size.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export function columnLabel(column: string): string {
  const named: Record<string, string> = {
    row_number: "#",
    rank: "Rank",
    dense_rank: "Rank",
    achievement_pct: "Achievement %",
    contribution_to_change_pct: "Share of change %",
    cumulative_share_pct: "Cumulative share %",
    above_average_pct: "Above average %",
    change_pct: "Change %",
    mom_growth_pct: "MoM growth %",
    qoq_growth_pct: "QoQ growth %",
    yoy_growth_pct: "YoY growth %",
  };
  if (named[column]) return named[column];
  return prettyLabel(column.replace(/_pct$/, " %").replace(/_name$/, ""));
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
