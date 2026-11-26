import { formatRevenueInr } from "@/lib/display-currency";

/** Source amounts are INR; this legacy function name is retained for callers. */

export function formatInr(value: number | null | undefined, digits?: number): string {
  if (typeof formatRevenueInr === "function") {
    return formatRevenueInr(value, true, digits ?? 2);
  }

  // Defensive fallback for stale/dev HMR module graphs. Keep the source value in INR
  // and present it using the approved display-currency rate.
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    minimumFractionDigits: 0,
    maximumFractionDigits: digits ?? 2,
  }).format(value / 95);
}

export function formatCount(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return Math.round(value).toLocaleString("en-IN");
}

export function formatCompact(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e7) return `${(value / 1e7).toFixed(abs >= 1e9 ? 0 : 1)} Cr`;
  if (abs >= 1e5) return `${(value / 1e5).toFixed(1)} L`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(1)}k`;
  return `${Math.round(value)}`;
}

export function formatPct(value: number | null | undefined, signed = false, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  const pct = value * 100;
  return `${signed && pct > 0 ? "+" : ""}${pct.toFixed(digits)}%`;
}

export function formatPts(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const pts = value * 100;
  return `${pts > 0 ? "+" : ""}${pts.toFixed(1)} pts`;
}

export function formatMonth(iso: string, withYear = true): string {
  const [year, month] = iso.split("-").map(Number);
  const date = new Date(year ?? 2000, (month ?? 1) - 1, 1);
  return date.toLocaleString("en-IN", withYear ? { month: "short", year: "2-digit" } : { month: "short" });
}

/** e.g. "Sep 2026 — MTD" for in-progress months on the revenue trend chart. */
export function formatTrendMonthLabel(iso: string, partial = false): string {
  const [year, month] = iso.split("-").map(Number);
  const date = new Date(year ?? 2000, (month ?? 1) - 1, 1);
  const base = date.toLocaleString("en-IN", { month: "short", year: "numeric" });
  return partial ? `${base} — MTD` : base;
}

export function formatDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}
