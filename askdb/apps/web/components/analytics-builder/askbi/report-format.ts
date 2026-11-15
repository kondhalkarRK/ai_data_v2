/** Presentation only: never use rounded labels as calculation inputs. */
export function formatReportValue(value: unknown, metricFormat?: string, compact = true): string {
  if (value == null || (typeof value === "number" && !Number.isFinite(value))) return "—";
  if (typeof value !== "number") return String(value);
  const currency = metricFormat === "currency";
  const percent = metricFormat === "percent" || metricFormat === "percentage";
  const absolute = Math.abs(value);
  const rounded = Math.round(absolute * 100) / 100;
  const unit = currency && compact ? rounded >= 10_000_000 ? { divisor: 10_000_000, label: " crore" } : rounded >= 100_000 ? { divisor: 100_000, label: " lakh" } : null : null;
  const digits = compact ? 2 : 20;
  const text = new Intl.NumberFormat("en-IN", { maximumFractionDigits: digits }).format(unit ? absolute / unit.divisor : absolute);
  return `${value < 0 ? "−" : ""}${currency ? "₹" : ""}${text}${unit?.label ?? ""}${percent ? "%" : ""}`;
}

const CATEGORY_COLORS = ["#3468c0", "#148075", "#8954b3", "#a56519", "#bf5269", "#427c9b"];
export function reportCategoryColor(label: string): string {
  let hash = 0;
  for (const letter of label) hash = (Math.imul(hash, 31) + letter.charCodeAt(0)) | 0;
  return CATEGORY_COLORS[(hash >>> 0) % CATEGORY_COLORS.length]!;
}
