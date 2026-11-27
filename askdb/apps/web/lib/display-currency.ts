/** Presentation only: source amounts remain in INR; no exchange-rate conversion. */
export const DISPLAY_CURRENCY = Object.freeze({
  sourceCurrency: "INR", displayCurrency: "INR", notation: "Cr/Lakh",
});
export const DISPLAY_CURRENCY_NOTE = "Amounts in INR (₹). Compact revenue labels use Cr or Lakh.";

export function formatRevenueInr(value: number | null | undefined, compact = true, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const absolute = Math.abs(value);
  const rounded = Number(absolute.toFixed(digits));
  const unit = compact && rounded >= 10_000_000
    ? { divisor: 10_000_000, label: " Cr" }
    : compact && rounded >= 100_000 ? { divisor: 100_000, label: " Lakh" } : null;
  const number = new Intl.NumberFormat("en-IN", { maximumFractionDigits: compact ? digits : 20 }).format(unit ? absolute / unit.divisor : absolute);
  return `${value < 0 ? "−" : ""}₹${number}${unit?.label ?? ""}`;
}

/** Conservative fallback for governed SQL aliases when a chart has no metric metadata. */
export function isMonetaryColumn(column: string): boolean {
  if (/(?:growth|share|percent|pct|ratio|margin|rank|count|units|qty|quantity|index)/i.test(column)) return false;
  return /(?:^|_)(?:revenue|total_sales|sales_amount|sales_value|net_sales|gross_sales|amount|price|asp|premium|cost|profit)(?:_|$)/i.test(column);
}
