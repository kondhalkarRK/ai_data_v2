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
  const datePart = formatDateRangeLabel(spec) ? ` · ${formatDateRangeLabel(spec)}` : "";
  const limitPart =
    spec.analysis === "top_n" || spec.analysis === "bottom_n" || spec.analysis === "ranking"
      ? ` · ${spec.limit}`
      : "";
  return `${head}${by}${filterPart}${datePart}${limitPart}`;
}

export type DatePresetId =
  | "custom"
  | "today"
  | "yesterday"
  | "last_7"
  | "last_30"
  | "this_month"
  | "last_month"
  | "this_quarter"
  | "last_quarter"
  | "this_year"
  | "last_year"
  | "yoy"
  | "mom"
  | "qoq";

export const DATE_PRESETS: Array<{ id: DatePresetId; label: string }> = [
  { id: "custom", label: "Custom Range" },
  { id: "today", label: "Today" },
  { id: "yesterday", label: "Yesterday" },
  { id: "last_7", label: "Last 7 Days" },
  { id: "last_30", label: "Last 30 Days" },
  { id: "this_month", label: "This Month" },
  { id: "last_month", label: "Last Month" },
  { id: "this_quarter", label: "This Quarter" },
  { id: "last_quarter", label: "Last Quarter" },
  { id: "this_year", label: "This Year" },
  { id: "last_year", label: "Last Year" },
  { id: "yoy", label: "Year-over-Year (YoY)" },
  { id: "mom", label: "Month-over-Month (MoM)" },
  { id: "qoq", label: "Quarter-over-Quarter (QoQ)" },
];

function iso(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function startOfQuarter(d: Date): Date {
  const q = Math.floor(d.getMonth() / 3) * 3;
  return new Date(d.getFullYear(), q, 1);
}

export function resolveDatePreset(
  preset: DatePresetId,
  custom?: { from?: string | null; to?: string | null },
): { from: string | null; to: string | null; timeGrain?: string | null; analysis?: AnalyticsSpec["analysis"] } {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  if (preset === "custom") {
    return { from: custom?.from ?? null, to: custom?.to ?? null };
  }
  if (preset === "yoy") return { from: null, to: null, timeGrain: "year", analysis: "period_growth" };
  if (preset === "mom") return { from: null, to: null, timeGrain: "month", analysis: "period_growth" };
  if (preset === "qoq") return { from: null, to: null, timeGrain: "quarter", analysis: "period_growth" };
  if (preset === "today") return { from: iso(today), to: iso(today) };
  if (preset === "yesterday") {
    const y = new Date(today);
    y.setDate(y.getDate() - 1);
    return { from: iso(y), to: iso(y) };
  }
  if (preset === "last_7") {
    const start = new Date(today);
    start.setDate(start.getDate() - 6);
    return { from: iso(start), to: iso(today) };
  }
  if (preset === "last_30") {
    const start = new Date(today);
    start.setDate(start.getDate() - 29);
    return { from: iso(start), to: iso(today) };
  }
  if (preset === "this_month") return { from: iso(startOfMonth(today)), to: iso(today) };
  if (preset === "last_month") {
    const start = startOfMonth(new Date(today.getFullYear(), today.getMonth() - 1, 1));
    const end = new Date(today.getFullYear(), today.getMonth(), 0);
    return { from: iso(start), to: iso(end) };
  }
  if (preset === "this_quarter") return { from: iso(startOfQuarter(today)), to: iso(today) };
  if (preset === "last_quarter") {
    const start = startOfQuarter(new Date(today.getFullYear(), today.getMonth() - 3, 1));
    const end = new Date(start.getFullYear(), start.getMonth() + 3, 0);
    return { from: iso(start), to: iso(end) };
  }
  if (preset === "this_year") return { from: iso(new Date(today.getFullYear(), 0, 1)), to: iso(today) };
  if (preset === "last_year") {
    return {
      from: iso(new Date(today.getFullYear() - 1, 0, 1)),
      to: iso(new Date(today.getFullYear() - 1, 11, 31)),
    };
  }
  return { from: null, to: null };
}

export function formatDateRangeLabel(spec: Pick<AnalyticsSpec, "datePreset" | "dateFrom" | "dateTo">): string {
  const preset = DATE_PRESETS.find((item) => item.id === spec.datePreset);
  if (!spec.datePreset) return "";
  if (spec.datePreset === "custom" && spec.dateFrom && spec.dateTo) {
    return `${spec.dateFrom} → ${spec.dateTo}`;
  }
  return preset?.label ?? "";
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
