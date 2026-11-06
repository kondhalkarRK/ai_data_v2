import type { BiPlan } from "@nql/shared-types";
import { panelScope, type PanelResult } from "./use-askbi";

export const LIFT_QUESTION = "Show revenue lift against a 10% target";
export const LIFT_BASELINE_ID = "revenue-lift-baseline";
export const LIFT_REGION_BASELINE_ID = "revenue-lift-region-baseline";

export function isRevenueLift(plan: BiPlan | null): boolean {
  return Boolean(plan?.panels.some(panel => panel.id === LIFT_BASELINE_ID && panel.spec.metrics[0] === "revenue"));
}

export function reportScopeSpec(plan: BiPlan) {
  return isRevenueLift(plan)
    ? (plan.panels.find(panel => panel.id === "leader-1") ?? plan.panels.find(panel => ![LIFT_BASELINE_ID, LIFT_REGION_BASELINE_ID].includes(panel.id)) ?? plan.panels[0])?.spec
    : plan.panels[0]?.spec;
}

export function currentValue(plan: BiPlan, results: Record<string, PanelResult>, panelId: string): number | null {
  const panel = plan.panels.find(item => item.id === panelId);
  if (!panel) return null;
  const state = results[panelId];
  if (!state?.result || state.error || state.loading || state.scope !== panelScope(panel)) return null;
  const result = state.result;
  if (!result.rows.length) return null;
  const column = String(result.meta.valueColumn ?? panel.spec.metrics[0]);
  const value = result.rows[0]?.[column];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function liftScenario(current: number | null, baseline: number | null, percent: number) {
  if (current === null || baseline === null || baseline <= 0 || !Number.isFinite(current) || !Number.isFinite(percent)) return null;
  const target = baseline * (1 + percent / 100);
  return { target, actualLift: (current - baseline) / baseline * 100, gap: current - target, baseline, current };
}

export function regionalContributions(plan: BiPlan, results: Record<string, PanelResult>) {
  const currentPanel = plan.panels.find(item => item.id === "leader-4");
  const priorPanel = plan.panels.find(item => item.id === LIFT_REGION_BASELINE_ID);
  if (!currentPanel || !priorPanel) return null;
  const currentState = results[currentPanel.id];
  const priorState = results[priorPanel.id];
  if (!currentState?.result || !priorState?.result || currentState.error || priorState.error || currentState.loading || priorState.loading || currentState.scope !== panelScope(currentPanel) || priorState.scope !== panelScope(priorPanel)) return null;
  const currentRows = currentState.result.rows;
  const priorRows = priorState.result.rows;
  if (currentState.result.meta.truncated || priorState.result.meta.truncated || currentRows.length >= currentPanel.spec.limit || priorRows.length >= priorPanel.spec.limit) return null;
  const totalCurrent = currentValue(plan, results, "leader-1");
  const totalPrior = currentValue(plan, results, LIFT_BASELINE_ID);
  if (totalCurrent === null || totalPrior === null) return null;
  const values = new Map<string, { current: number; prior: number }>();
  for (const row of currentRows) {
    const name = row.region;
    const value = row.revenue;
    if (typeof name !== "string" || typeof value !== "number" || !Number.isFinite(value)) return null;
    values.set(name, { current: value, prior: 0 });
  }
  for (const row of priorRows) {
    const name = row.region;
    const value = row.revenue;
    if (typeof name !== "string" || typeof value !== "number" || !Number.isFinite(value)) return null;
    const found = values.get(name);
    values.set(name, { current: found?.current ?? 0, prior: value });
  }
  const rows = [...values].map(([name, value]) => ({ name, ...value, delta: value.current - value.prior })).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  const total = totalCurrent - totalPrior;
  const residual = total - rows.reduce((sum, row) => sum + row.delta, 0);
  if (Math.abs(residual) > Math.max(0.01, Math.abs(total) * 1e-8)) rows.push({ name: "Other / reconciliation", current: 0, prior: 0, delta: residual });
  return { rows, total, currentFrom: currentPanel.spec.dateFrom, currentTo: currentPanel.spec.dateTo, priorFrom: priorPanel.spec.dateFrom, priorTo: priorPanel.spec.dateTo };
}
