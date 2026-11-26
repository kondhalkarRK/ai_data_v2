import { formatRevenueInr } from "@/lib/display-currency";

/** Presentation only: never use rounded labels as calculation inputs. */
export function formatReportValue(value: unknown, metricFormat?: string, compact = true): string {
  if (value == null || (typeof value === "number" && !Number.isFinite(value))) return "—";
  if (typeof value !== "number") return String(value);
  if (metricFormat === "currency") return formatRevenueInr(value, compact);
  const percent = metricFormat === "percent" || metricFormat === "percentage";
  const text = new Intl.NumberFormat("en-IN", { maximumFractionDigits: compact ? 2 : 20 }).format(Math.abs(value));
  return `${value < 0 ? "−" : ""}${text}${percent ? "%" : ""}`;
}

const CATEGORY_COLORS = ["#3468c0", "#148075", "#8954b3", "#a56519", "#bf5269", "#427c9b"];
export function reportCategoryColor(label: string): string {
  let hash = 0;
  for (const letter of label) hash = (Math.imul(hash, 31) + letter.charCodeAt(0)) | 0;
  return CATEGORY_COLORS[(hash >>> 0) % CATEGORY_COLORS.length]!;
}
