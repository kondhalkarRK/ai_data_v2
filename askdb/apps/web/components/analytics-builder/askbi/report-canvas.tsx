"use client";

import type { BiPlan } from "@nql/shared-types";
import { BarChart3 } from "lucide-react";
import { WorkspacePanel } from "@/components/analytics-builder/analytics-workspace";
import { Button } from "@/components/ui/button";
import { panelScope, rendererScope, type PanelResult, type ReportAction } from "./use-askbi";

export function ReportCanvas({ plan, results, selected, onSelect, onCommand, onRetry, onExample, busy, briefing, scopeLabel = "Permitted regions" }: {
  plan: BiPlan | null; results: Record<string, PanelResult>; selected: string | null;
  onSelect: (id: string) => void; onCommand: (action: ReportAction, question?: string, value?: string, target?: string) => void;
  onRetry: (id: string) => void; onExample: (question: string) => void; busy: boolean; briefing: string[]; scopeLabel?: string;
}) {
  if (!plan) return <section className="flex min-h-[34rem] flex-col justify-center rounded-2xl border border-dashed border-border bg-surface-raised px-6 py-12 md:px-10" aria-label="Start a report">
    <BarChart3 className="mb-5 size-8 text-primary" /><h2 className="text-2xl font-semibold tracking-tight">Start with a business question.</h2>
    <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted-foreground">Choose a leadership briefing or ask your own question. Each report uses approved automotive measures and can be refined in conversation.</p>
    <div className="mt-8 grid gap-3 sm:grid-cols-2">{[
      ["CEO", "Sales Report for CEO"],
      ["CFO", "Financial Sales Briefing for CFO"],
      ["Region & dealer", "Region & Dealer Performance"],
      ["Sales team", "Sales Team Performance"],
      ["Vehicle portfolio", "Make & Model Comparison"],
      ["Momentum", "Sales Momentum & Emerging Models"],
    ].map(([label, question]) => <button key={question} onClick={() => { if (question) onExample(question); }} disabled={busy} className="rounded-xl border border-border p-4 text-left hover:bg-muted/40 focus-visible:outline-ring"><span className="text-xs text-muted-foreground">{label}</span><span className="mt-1 block text-sm font-medium">{question}</span></button>)}</div>
  </section>;
  const groups = [...new Set(plan.panels.map(panel => panel.section || "Analysis"))];
  return <div className="space-y-6" aria-label="AskBI report">
    <div data-askbi-pdf className="border-b border-border pb-5"><p className="text-xs font-semibold uppercase tracking-widest text-primary">Ask Me · Automotive report</p><h2 className="mt-2 text-2xl font-semibold tracking-tight">{plan.title}</h2><p className="mt-1 text-sm text-muted-foreground">{plan.panels[0]?.spec.dateFrom} to {plan.panels[0]?.spec.dateTo} · {plan.reportFilter?.make ?? "All makes"} · {plan.reportFilter?.region ? `${plan.reportFilter.region} · ` : ""}{scopeLabel}</p></div>
    {plan.assumptions.length > 0 && <div data-askbi-pdf className="rounded-lg border border-border px-4 py-3 text-xs text-muted-foreground">{plan.assumptions.map(item => <p key={item}>{item}</p>)}</div>}
    {briefing.length > 0 && <section data-askbi-pdf className="border-l-2 border-primary/50 py-1 pl-4" aria-label="Evidence briefing"><h3 className="text-sm font-semibold">Evidence briefing</h3>{briefing.map((paragraph, i) => <p className="mt-2 text-sm leading-relaxed text-muted-foreground" key={i}>{paragraph}</p>)}</section>}
    {groups.map(group => <section key={group} aria-label={group}><h3 data-askbi-pdf={group === "Key metrics" ? undefined : ""} className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{group}</h3>
      <div className={`grid gap-4 ${plan.panels.filter(p => (p.section || "Analysis") === group).length > 1 ? group === "Key metrics" ? "md:grid-cols-2" : "xl:grid-cols-2" : ""}`}>
        {plan.panels.filter(p => (p.section || "Analysis") === group).map(panel => {
          const result = results[panel.id];
          const current = result?.scope === panelScope(panel);
          const rendererState = result ? { ...result, scope: current ? rendererScope(panel) : "previous-scope" } : undefined;
          const lastOddBreakdown = group === "Performance breakdown" && plan.panels.filter(p => (p.section || "Analysis") === group).length % 2 === 0 && panel.id === plan.panels.filter(p => (p.section || "Analysis") === group).at(-1)?.id;
          const firstBreakdown = group === "Performance breakdown" && panel.id === plan.panels.find(p => p.section === "Performance breakdown")?.id;
          return <div key={panel.id} id={`askbi-panel-${panel.id}`} data-askbi-pdf className={`min-w-0 scroll-mt-6 ${firstBreakdown || lastOddBreakdown ? "xl:col-span-2" : ""}`}>
            <fieldset disabled={busy} className="min-w-0"><legend className="sr-only">{panel.title} actions</legend>
              <WorkspacePanel panel={panel} state={rendererState} selected={selected === panel.id} onSelect={() => onSelect(panel.id)} onRetry={() => onRetry(panel.id)}
                onEdit={update => onCommand("visualize", "", update.spec?.viz, panel.id)} onRemove={() => onCommand("remove", "", undefined, panel.id)} />
              <div className="mt-1 flex items-center justify-between px-2 text-[11px] text-muted-foreground"><span>{panel.grain ? `${panel.grain} grain · ` : ""}{result?.loadedAt ? `Loaded ${new Date(result.loadedAt).toLocaleTimeString()}` : ""}</span><span><Button variant="ghost" size="sm" onClick={() => onCommand("move_up", "", undefined, panel.id)} aria-label={`Move ${panel.title} up`}>↑</Button><Button variant="ghost" size="sm" onClick={() => onCommand("move_down", "", undefined, panel.id)} aria-label={`Move ${panel.title} down`}>↓</Button></span></div>
            </fieldset>
          </div>;
        })}
      </div>
    </section>)}
  </div>;
}
