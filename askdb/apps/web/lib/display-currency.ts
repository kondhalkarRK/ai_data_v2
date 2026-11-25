/** Approved presentation rate. Source values and calculations remain in INR. */
export const DISPLAY_FX = Object.freeze({
  sourceCurrency: "INR",
  displayCurrency: "USD",
  inrPerUsd: 95,
  configuredOn: "2026-11-24",
  source: "User-approved fixed display rate",
});

export const DISPLAY_FX_NOTE = `USD display · ₹${DISPLAY_FX.inrPerUsd} = US$1 · configured ${DISPLAY_FX.configuredOn} · user-approved fixed rate, not a live market rate. Source calculations remain in INR.`;

export function formatRevenueUsd(value: number | null | undefined, compact = true, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    notation: compact ? "compact" : "standard",
    minimumFractionDigits: compact ? 0 : 2,
    maximumFractionDigits: digits,
  }).format(value / DISPLAY_FX.inrPerUsd);
}

/** Conservative fallback for governed SQL aliases when a chart has no metric metadata. */
export function isMonetaryColumn(column: string): boolean {
  if (/(?:growth|share|percent|pct|ratio|margin|rank|count|units|qty|quantity|index)/i.test(column)) return false;
  return /(?:^|_)(?:revenue|total_sales|sales_amount|sales_value|net_sales|gross_sales|amount|price|asp|premium|cost|profit)(?:_|$)/i.test(column);
}
