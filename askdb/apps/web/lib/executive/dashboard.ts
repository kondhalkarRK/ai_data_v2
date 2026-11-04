import type { DashboardMetric } from "@nql/shared-types";

import { formatCount, formatInr, formatPct } from "@/components/executive/cockpit/format";

export const AUGMENTED_DASHBOARD_ENABLED =
  (process.env.NEXT_PUBLIC_ASK_ME_AUGMENTED_DASHBOARD_ENABLED ?? "true").toLowerCase() === "true";

export function dashboardValue(value: number | null, metric: Pick<DashboardMetric, "format">): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return metric.format === "currency" ? formatInr(value) : metric.format === "percent" ? formatPct(value) : formatCount(value);
}

export function dashboardChange(value: number, metric: Pick<DashboardMetric, "format">): string {
  return metric.format === "percent" ? `${value > 0 ? "+" : ""}${(value * 100).toFixed(2)} pp` : `${value > 0 ? "+" : ""}${dashboardValue(value, metric)}`;
}

/** Parent dimension changes clear descendants; unrelated filters remain intact. */
export function mergeDashboardFilters<T extends Record<string, string | undefined>>(current: T, patch: Record<string, string>): T {
  const next = { ...current } as Record<string, string | undefined>;
  const descendants: Record<string, string[]> = {
    zone: ["state", "city", "dealer_id", "sales_person_id"],
    state: ["city", "dealer_id", "sales_person_id"], city: ["dealer_id", "sales_person_id"],
    make: ["model"], dealer_id: ["sales_person_id"],
  };
  for (const key of Object.keys(patch)) for (const child of descendants[key] ?? []) delete next[child];
  return { ...next, ...patch } as T;
}
