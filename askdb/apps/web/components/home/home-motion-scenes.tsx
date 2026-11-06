import * as React from "react";
import { BarChart3, BookOpen, Database, FileChartColumnIncreasing, MessageSquare, ShieldCheck, Sparkles } from "lucide-react";

function Beat({ at, children, className = "" }: { at: number; children: React.ReactNode; className?: string }) {
  return <div className={`home-motion-beat ${className}`} style={{ animationDelay: `${at}ms` }}>{children}</div>;
}

function Frame({ icon, title, suffix, children }: { icon: React.ReactNode; title: string; suffix: string; children: React.ReactNode }) {
  return <><div className="mb-4 flex items-center justify-between border-b border-border pb-3"><div className="flex items-center gap-2 text-sm font-semibold"><span className="rounded-lg bg-primary/10 p-2 text-primary">{icon}</span>{title}</div><span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{suffix}</span></div>{children}</>;
}

export function AnswerMotion() {
  const regions = [{ name: "West", rate: 12 }, { name: "South", rate: 8 }, { name: "North", rate: 5 }, { name: "East", rate: 2 }];
  return <Frame icon={<MessageSquare className="size-4" />} title="AI Chat" suffix="Question → evidence">
    <Beat at={0} className="rounded-xl border border-border bg-background p-3 text-sm font-medium">Which region led sales growth last month?</Beat>
    <svg className="mt-1 h-6 w-full text-primary/45" viewBox="0 0 300 24" preserveAspectRatio="none" aria-hidden="true"><path className="home-motion-connector" d="M150 0 V9 H50 V24 M150 9 V24 M150 9 H250 V24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ animationDelay: "420ms" }} /></svg>
    <div className="mb-3 grid grid-cols-3 gap-2 text-center text-[11px] font-medium">
      {[{ name: "Schema", Icon: Database, cue: "Tables" }, { name: "Definitions", Icon: BookOpen, cue: "Metrics" }, { name: "Ontology", Icon: Sparkles, cue: "Relationships" }].map((item, index) => <Beat at={850 + index * 520} key={item.name} className="rounded-xl border border-primary/20 bg-primary/8 p-2.5"><item.Icon className="mx-auto mb-1.5 size-4 text-primary" />{item.name}<span className="mt-0.5 block text-[10px] text-muted-foreground">{item.cue}</span></Beat>)}
    </div>
    <Beat at={2650} className="flex items-center justify-between rounded-xl border border-border bg-background p-3 text-xs"><span>Governed query</span><span className="text-muted-foreground">Read-only · scoped</span></Beat>
    <div className="mt-3 min-h-[142px] rounded-xl border border-primary/25 bg-primary/6 p-3">
      <Beat at={3500}><p className="text-[10px] font-semibold uppercase tracking-widest text-primary">Illustrative answer</p><p className="mt-1 text-lg font-bold tabular-nums">West <span className="text-success">+12%</span> <span className="text-xs font-normal text-muted-foreground">sales growth</span></p></Beat>
      <div className="mt-2 flex h-12 items-end gap-2" role="img" aria-label="Example growth by region: West 12%, South 8%, North 5%, East 2%">{regions.map((region, index) => <div className="flex h-full flex-1 items-end gap-1" key={region.name}><div className="home-motion-bar w-full rounded-t bg-primary/75" style={{ height: `${region.rate / 12 * 100}%`, animationDelay: `${4100 + index * 180}ms` }} /><span className="sr-only">{region.name} {region.rate}%</span></div>)}</div>
      <Beat at={5300} className="mt-2 text-[10px] text-muted-foreground">West 12% · South 8% · North 5% · East 2% <span className="float-right font-medium text-primary">View definition and query</span></Beat>
    </div>
  </Frame>;
}

export function ReportMotion({ askbi }: { askbi: boolean }) {
  const weeks = [{ label: "W1", revenue: 2.1 }, { label: "W2", revenue: 2.5 }, { label: "W3", revenue: 2.8 }, { label: "W4", revenue: 3.4 }];
  const regions = [{ name: "West", revenue: 5.2 }, { name: "South", revenue: 3.1 }, { name: "North", revenue: 2.5 }];
  return <Frame icon={<FileChartColumnIncreasing className="size-4" />} title={askbi ? "Auto Report · AskBI" : "Analytics Builder preview"} suffix="Question → report">
    <Beat at={0} className="rounded-xl border border-border bg-background p-3 text-xs font-medium">Create a sales report for the CEO</Beat>
    <div className="mt-3 grid grid-cols-3 gap-2">{[{ name: "Revenue", value: "₹10.8L", prior: "vs ₹10.0L prior" }, { name: "Units sold", value: "124", prior: "example units" }, { name: "Orders", value: "98", prior: "example orders" }].map((item, index) => <Beat at={950 + index * 400} key={item.name} className="rounded-xl border border-border bg-background p-3"><p className="text-[10px] text-muted-foreground">{item.name}</p><p className="mt-1 text-base font-bold tabular-nums sm:text-xl">{item.value}</p><p className="text-[10px] text-muted-foreground">{item.prior}</p></Beat>)}</div>
    <Beat at={2250} className="mt-2 flex flex-wrap gap-2 text-[10px] text-muted-foreground"><span className="rounded-md border border-border bg-background px-2 py-1">Period: last month</span><span className="rounded-md border border-border bg-background px-2 py-1">Industry: automotive</span></Beat>
    <div className="mt-3 grid gap-2 sm:grid-cols-[1.5fr_1fr]">
      <Beat at={2450} className="rounded-xl border border-border bg-background p-3"><p className="text-xs font-semibold">Weekly revenue · ₹10.8L total</p><div className="mt-3 flex h-20 items-end gap-2 border-b border-border px-2">{weeks.map((week, index) => <div key={week.label} className="flex h-full flex-1 flex-col items-center justify-end"><div className="home-motion-bar w-full rounded-t bg-primary/75" style={{ height: `${week.revenue / 3.4 * 78}%`, animationDelay: `${2750 + index * 170}ms` }} /><span className="mt-1 text-[9px] text-muted-foreground">{week.label}</span></div>)}</div></Beat>
      <Beat at={3650} className="rounded-xl border border-border bg-background p-3"><p className="text-xs font-semibold">Regional mix · ₹10.8L</p><div className="mt-4 space-y-2">{regions.map((region, index) => <div key={region.name} className="flex items-center gap-2 text-[9px]"><span className="w-8 text-muted-foreground">{region.name}</span><span className="h-2 flex-1 rounded-full bg-muted"><span className="home-motion-bar home-motion-bar-horizontal block h-2 rounded-full bg-teal" style={{ width: `${region.revenue / 5.2 * 100}%`, animationDelay: `${3850 + index * 170}ms` }} /></span><span className="w-7 text-right">{region.revenue}</span></div>)}</div></Beat>
    </div>
    <Beat at={5250} className="mt-3 rounded-lg bg-muted/60 px-3 py-2 text-xs text-muted-foreground">Briefing: week 4 led at ₹3.4L; the four weeks total ₹10.8L.</Beat>
  </Frame>;
}

export function DecisionMotion() {
  return <Frame icon={<BarChart3 className="size-4" />} title="Executive Intelligence" suffix="Performance → evidence">
    <div className="grid gap-3 sm:grid-cols-[1.3fr_.7fr]">
      <div className="rounded-xl border border-border bg-background p-4">
        <Beat at={0}><p className="text-xs font-semibold">Illustrative revenue · current ₹10.8L</p><p className="mt-1 text-2xl font-bold tabular-nums">+8.0% <span className="text-xs font-medium text-muted-foreground">vs ₹10.0L prior</span></p></Beat>
        <svg viewBox="0 0 320 120" role="img" aria-label="Illustrative weekly revenue: 2.1, 2.5, 2.8, 3.4 lakh rupees" className="mt-3 h-28 w-full"><path className="home-motion-line" d="M8 102 L108 78 L208 60 L312 24" fill="none" stroke="hsl(var(--chart-1))" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/><path className="home-motion-area" d="M8 102 L108 78 L208 60 L312 24 L312 116 L8 116Z" fill="hsl(var(--chart-1) / .14)" /></svg>
        <Beat at={2800} className="mt-1 rounded-lg border border-primary/20 bg-primary/6 px-2 py-1 text-[10px]">Week 4: ₹3.4L · strongest observed week</Beat>
      </div>
      <Beat at={4200} className="rounded-xl border border-border bg-background p-4"><div className="flex items-center gap-2 text-xs font-semibold"><ShieldCheck className="size-4 text-primary"/>Evidence to inspect</div><div className="mt-4 space-y-2 text-[11px] text-muted-foreground"><p className="border-b border-border pb-1">Metric definition</p><p className="border-b border-border pb-1">Comparison period</p><p className="border-b border-border pb-1">Permitted scope</p><p>Data freshness</p></div></Beat>
    </div>
    <Beat at={3300} className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-border bg-background p-3 text-xs"><span className="font-semibold">Observed regional change:</span><span>West +₹0.4L</span><span>South +₹0.3L</span><span>North +₹0.1L</span></Beat>
    <Beat at={5650} className="mt-2 flex items-center gap-2 rounded-xl border border-primary/25 bg-primary/6 p-3 text-xs"><ShieldCheck className="size-4 text-primary" /><span>Changes sum to +₹0.8L. Inspect evidence before deciding; contribution is not proven causation.</span></Beat>
  </Frame>;
}
