"use client";

import type { BiPanel, BiPlan } from "@nql/shared-types";
import { BarChart3, ChartNoAxesCombined, MapPinned, Target, Users, Wallet } from "lucide-react";
import { ReportPanel } from "./report-panel";
import { RegionalContributions } from "./regional-contributions";
import { currentValue, isRevenueLift, liftScenario, regionalContributions, reportScopeSpec, LIFT_BASELINE_ID, LIFT_QUESTION, LIFT_REGION_BASELINE_ID } from "./revenue-lift";
import { type PanelResult, type ReportAction } from "./use-askbi";

const STARTERS = [
  { label: "CEO", question: "Sales Report for CEO", description: "Sales movement, regions and vehicle mix", icon: ChartNoAxesCombined },
  { label: "CFO", question: "Financial Sales Briefing for CFO", description: "Revenue, selling price and concentration", icon: Wallet },
  { label: "Region & dealer", question: "Region & Dealer Performance", description: "Territories, dealers and model mix", icon: MapPinned },
  { label: "Sales team", question: "Sales Team Performance", description: "People, units and leading models", icon: Users },
  { label: "Vehicle portfolio", question: "Make & Model Comparison", description: "Volume and selling price by vehicle", icon: BarChart3 },
  { label: "Revenue lift", question: LIFT_QUESTION, description: "Actual growth against a chosen lift target", icon: Target },
];

const money = (value: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value);

export function ReportCanvas({ plan, results, selected, onSelect, onCommand, onRetry, onExample, busy, briefing, scopeLabel = "Permitted regions", question, liftPercent, onLiftPercent }: {
  plan: BiPlan | null; results: Record<string, PanelResult>; selected: string | null;
  onSelect: (id: string) => void; onCommand: (action: ReportAction, question?: string, value?: string, target?: string) => void;
  onRetry: (id: string) => void; onExample: (question: string) => void; busy: boolean; briefing: string[]; scopeLabel?: string;
  question?: string; liftPercent: number; onLiftPercent: (value: number) => void;
}) {
  if (!plan) return <section className="rounded-2xl border border-border bg-surface-raised px-5 py-8 sm:px-8 sm:py-10" aria-label="Start a report">
    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Auto Report · AskBI</p><h2 className="mt-3 max-w-2xl text-2xl font-semibold tracking-tight sm:text-3xl">Start with a business question.</h2>
    <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">Choose a leadership question, review it in AskBI, then press Send. Reports use approved automotive measures and your permitted data.</p>
    <div className="mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{STARTERS.map(({ label, question: starter, description, icon: Icon }) => <button key={starter} type="button" onClick={() => onExample(starter)} disabled={busy} className="min-h-32 rounded-2xl border border-border bg-background p-4 text-left transition-colors hover:border-primary/55 hover:bg-primary/5 focus-visible:outline-ring"><span className="flex items-center gap-2 text-xs font-medium text-primary"><Icon className="size-4" />{label}</span><span className="mt-3 block text-sm font-semibold leading-snug">{label === "Revenue lift" ? "Revenue Lift" : starter}</span><span className="mt-1 block text-xs leading-relaxed text-muted-foreground">{description}</span></button>)}</div>
  </section>;

  const lift = isRevenueLift(plan);
  const current = lift ? currentValue(plan, results, "leader-1") : null;
  const baseline = lift ? currentValue(plan, results, LIFT_BASELINE_ID) : null;
  const scenario = liftScenario(current, baseline, liftPercent);
  const contributions = lift ? regionalContributions(plan, results) : null;
  const metricPanels = plan.panels.filter(panel => panel.kind === "kpi");
  const chartPanels = plan.panels.filter(panel => panel.kind !== "kpi");
  const hero = chartPanels.find(panel => panel.section === "Sales movement") ?? chartPanels[0];
  const supporting = chartPanels.filter(panel => panel.id !== hero?.id && (!contributions || !["leader-4", LIFT_REGION_BASELINE_ID].includes(panel.id)));
  const scope = reportScopeSpec(plan);
  const renderPanel = (panel: BiPanel, wide = false) => <div key={panel.id} id={`askbi-panel-${panel.id}`} data-askbi-pdf className={`min-w-0 scroll-mt-6 ${wide ? "xl:col-span-2" : ""}`}><fieldset disabled={busy} className="h-full min-w-0"><legend className="sr-only">{panel.title} actions</legend><ReportPanel panel={panel} state={results[panel.id]} selected={selected === panel.id} onSelect={() => onSelect(panel.id)} onRetry={() => onRetry(panel.id)} onCommand={onCommand} /></fieldset></div>;
  return <div className="askbi-report space-y-5" aria-label="AskBI report">
    {question && <div data-askbi-pdf className="rounded-xl border border-border bg-surface-raised px-4 py-3 text-sm"><span className="mr-2 text-xs font-semibold uppercase tracking-wider text-primary">Your question</span><span>{question}</span></div>}
    <header data-askbi-pdf className="border-b border-border pb-5"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Ask Me · Automotive intelligence</p><h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">{plan.title}</h2><p className="mt-2 text-sm text-muted-foreground">{scope?.dateFrom} – {scope?.dateTo} · {plan.reportFilter?.make ?? "All makes"} · {plan.reportFilter?.region ? `${plan.reportFilter.region} · ` : ""}{scopeLabel}</p></header>
    {briefing.length > 0 && !briefing[0]?.includes("unavailable") && <section data-askbi-pdf aria-label="Report takeaway" className="rounded-2xl border border-border bg-surface-raised p-4 sm:p-5"><p className="text-xs font-semibold uppercase tracking-wider text-primary">What the data says</p>{briefing.slice(0, 2).map((paragraph, index) => <p className="mt-2 max-w-4xl text-sm leading-relaxed" key={index}>{paragraph}</p>)}</section>}
    {metricPanels.length > 0 && <section aria-label="Key metrics"><div className={`grid gap-3 ${metricPanels.length > 1 ? "sm:grid-cols-2" : ""}`}>{metricPanels.map(panel => renderPanel(panel))}</div></section>}
    {lift && <section data-askbi-pdf aria-label="Revenue lift scenario" className="rounded-2xl border border-border bg-surface-raised p-4 sm:p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wider text-primary">Revenue lift scenario</p><h3 className="mt-1 text-lg font-semibold">Target: {liftPercent}% above prior period</h3><p className="mt-1 text-xs text-muted-foreground">A target comparison based on completed sales data, not a forecast.</p></div><label className="flex min-w-52 flex-col gap-2 text-xs font-medium">Target lift: {liftPercent}%<input type="range" min="5" max="30" step="5" value={liftPercent} onChange={event => onLiftPercent(Number(event.target.value))} className="w-52 accent-primary" aria-label="Revenue lift target percentage" /></label></div>
      {scenario ? <div className="mt-5 grid gap-4 border-t border-border pt-4 sm:grid-cols-3"><div><p className="text-xs text-muted-foreground">Actual lift vs prior</p><p className={`mt-1 text-xl font-semibold tabular-nums ${scenario.actualLift >= 0 ? "text-success" : "text-danger"}`}>{scenario.actualLift >= 0 ? "+" : ""}{scenario.actualLift.toFixed(1)}%</p></div><div><p className="text-xs text-muted-foreground">Target revenue</p><p className="mt-1 text-xl font-semibold tabular-nums">{money(scenario.target)}</p></div><div><p className="text-xs text-muted-foreground">{scenario.gap >= 0 ? "Above target" : "Shortfall to target"}</p><p className={`mt-1 text-xl font-semibold tabular-nums ${scenario.gap >= 0 ? "text-success" : "text-danger"}`}>{money(Math.abs(scenario.gap))}</p></div><div className="sm:col-span-3"><div className="h-3 overflow-hidden rounded-full bg-muted" role="img" aria-label={`Actual revenue ${money(scenario.current)}; target revenue ${money(scenario.target)}`}><div className="askbi-target-bar h-full rounded-full" style={{ width: `${Math.min(100, Math.max(0, scenario.current / scenario.target * 100))}%` }} /></div><div className="mt-2 flex justify-between text-xs text-muted-foreground"><span>Actual {money(scenario.current)}</span><span>Target {money(scenario.target)}</span></div></div></div> : <p className="mt-4 border-t border-border pt-4 text-sm text-muted-foreground">The lift comparison needs completed current and prior-period revenue, with a prior value above zero. Target variance is unavailable for this selection.</p>}
    </section>}
    {hero && <section aria-label="Primary analysis"><p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{lift ? "Revenue movement" : "Performance at a glance"}</p>{renderPanel(hero)}</section>}
    {(supporting.length > 0 || contributions) && <section aria-label="Supporting analysis"><p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Explore the breakdown</p><div className={`grid gap-4 ${supporting.length + (contributions ? 1 : 0) >= 2 ? "xl:grid-cols-2" : ""}`}>{contributions && <div id="askbi-panel-leader-4" key="region-contributions" className="min-w-0"><RegionalContributions data={contributions} /></div>}{supporting.map((panel, index) => renderPanel(panel, !contributions && supporting.length % 2 === 1 && index === supporting.length - 1))}</div></section>}
    {plan.assumptions.length > 0 && <p data-askbi-pdf className="border-t border-border pt-4 text-xs leading-relaxed text-muted-foreground">{plan.assumptions.join(" ")}</p>}
  </div>;
}
