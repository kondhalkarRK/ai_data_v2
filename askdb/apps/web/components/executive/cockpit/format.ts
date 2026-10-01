/** Indian number formatting for executive read-outs (₹ Cr / L, lakh grouping). */

export function formatInr(value: number | null | undefined, digits?: number): string {
  if (value == null || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e7) {
    const crore = abs / 1e7;
    const d = digits ?? (crore >= 100 ? 0 : 1);
    return `${sign}₹${crore.toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d })} Cr`;
  }
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(digits ?? 1)} L`;
  return `${sign}₹${Math.round(abs).toLocaleString("en-IN")}`;
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

export function formatDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}
