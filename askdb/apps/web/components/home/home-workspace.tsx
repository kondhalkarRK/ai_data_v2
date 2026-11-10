"use client";

import * as Dialog from "@radix-ui/react-dialog";
import type { BiReport, IndustryListResponse, ReadinessResponse } from "@nql/shared-types";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BarChart3, BookOpen, Database, FileChartColumnIncreasing, MessageSquare, Play, Send, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { ConnectedDataSources } from "@/components/home/connected-data-sources";
import { HomeStory } from "@/components/home/home-story";
import type { DataTrustCenter } from "@/components/trust/types";
import { Button } from "@/components/ui/button";
import { useActiveIndustry, useRegionAccess, useSession } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";

interface SavedQuestion { id: string; title: string; question: string; createdAt: string }

const EXAMPLES = {
  automotive: ["Revenue by month", "Top models by units sold", "Units sold by region"],
  insurance: ["Premium by month", "Claims by region", "Loss ratio by product"],
} as const;

const ACTIONS = [
  { title: "Create a report", description: "Build charts and a briefing from governed measures.", icon: FileChartColumnIncreasing },
  { title: "Monitor performance", description: "Review KPIs, trends and important changes.", icon: BarChart3, href: "/dashboard" },
  { title: "Check data confidence", description: "Inspect freshness, rules and data incidents.", icon: ShieldCheck, href: "/data-quality" },
  { title: "Explore definitions", description: "See the business meaning behind your data.", icon: BookOpen, href: "/semantic" },
] as const;

function when(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? null : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function HomeWorkspace() {
  const router = useRouter();
  const industry = useActiveIndustry();
  const region = useRegionAccess();
  const { data: user } = useSession();
  const askbiConfigured = industry === "automotive" && (process.env.NEXT_PUBLIC_ASK_ME_ASKBI_ENABLED ?? "false").toLowerCase() === "true";
  const [question, setQuestion] = React.useState("");
  const [tourOpen, setTourOpen] = React.useState(false);
  const [sourcesOpen, setSourcesOpen] = React.useState(false);

  const industries = useQuery({ queryKey: ["industries"], queryFn: () => apiClient.get<IndustryListResponse>("/api/v1/industries"), staleTime: 60_000 });
  const readiness = useQuery({ queryKey: ["readiness"], queryFn: () => apiClient.get<ReadinessResponse>("/ready"), refetchInterval: 30_000, staleTime: 0 });
  const trust = useQuery({ queryKey: ["data-trust-center-summary", industry], queryFn: () => apiClient.get<DataTrustCenter>("/api/v1/trust/center", { industry }), staleTime: 60_000 });
  const biCapability = useQuery({ queryKey: ["askbi-capability", industry], queryFn: () => apiClient.get<{ enabled: boolean; engine: string; schemaVersion: number }>("/api/v1/analytics/bi/capabilities", { industry }), enabled: askbiConfigured, staleTime: 60_000 });
  const askbi = askbiConfigured && biCapability.data?.enabled === true && biCapability.data.engine === "askbi-v2" && biCapability.data.schemaVersion === 2;
  const saved = useQuery({ queryKey: ["saved-questions", industry], queryFn: () => apiClient.get<SavedQuestion[]>("/api/v1/questions", { industry }), enabled: Boolean(user?.id), staleTime: 60_000 });
  const reports = useQuery({ queryKey: ["home-askbi-reports", user?.id, industry], queryFn: () => apiClient.get<BiReport[]>("/api/v1/analytics/bi/reports", { industry: "automotive" }), enabled: Boolean(user?.id) && askbi, staleTime: 60_000 });

  const pack = industries.data?.industries.find(item => item.id === industry);
  const activeName = pack?.label ?? (industry === "automotive" ? "Automotive" : "Insurance");
  const sourceState = industries.isPending ? "Checking connection" : industries.isError || !pack ? "Connection unknown" : pack.databaseAvailable ? "Database reachable" : "Database unreachable";
  const sourceTone = pack?.databaseAvailable ? "text-success" : industries.isPending || industries.isError || !pack ? "text-muted-foreground" : "text-danger";
  const freshness = when(trust.data?.dataAsOf);
  const checked = when(readiness.data?.checkedAt);
  const name = user?.fullName?.trim().split(/\s+/)[0] || user?.username || "there";
  const reportHref = askbi ? "/analytics-builder?mode=auto" : "/analytics-builder";

  function ask() {
    const trimmed = question.trim();
    if (trimmed) router.push(`/chat?q=${encodeURIComponent(trimmed)}`);
  }

  return <main className="w-full min-w-0 space-y-5 pb-8">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="text-xs font-semibold uppercase tracking-[.16em] text-primary">Your workspace</p><h1 className="mt-1 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">Good to see you, {name}</h1><p className="mt-1 text-sm text-muted-foreground">Ask, build and follow up from one place.</p></div>
      <Button variant="secondary" className="h-9" onClick={() => setTourOpen(true)}><Play aria-hidden="true" /> See how Ask Me works</Button>
    </header>

    <section aria-label="Current data context" className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-border bg-surface-raised px-4 py-3 text-xs shadow-[var(--shadow-card)]">
      <span className="inline-flex items-center gap-2 font-semibold text-foreground"><Database className="size-4 text-primary" aria-hidden="true" />{activeName}</span>
      <span className="text-muted-foreground">Scope: <strong className="font-medium text-foreground">{region.hideRegionFilter && !region.unrestricted ? "Restricted regions" : region.label}</strong></span>
      <span className="text-muted-foreground">Data as of: <strong className="font-medium text-foreground">{trust.isPending ? "Checking…" : trust.isError ? "Unavailable" : freshness ?? "Not reported"}</strong></span>
      <span className={`inline-flex items-center gap-1.5 font-medium ${sourceTone}`}><span className="size-1.5 rounded-full bg-current" aria-hidden="true" />{sourceState}</span>
    </section>

    <section className="rounded-2xl border border-border bg-surface-raised p-5 shadow-[var(--shadow-card)] sm:p-6" aria-labelledby="home-ask-heading">
      <div className="mb-4 flex items-start gap-3"><span className="rounded-xl bg-primary/10 p-2.5 text-primary"><MessageSquare className="size-5" aria-hidden="true" /></span><div><h2 id="home-ask-heading" className="text-lg font-semibold tracking-tight">What would you like to know about your data?</h2><p className="mt-0.5 text-sm text-muted-foreground">Ask a question using the current {activeName.toLowerCase()} data context.</p></div></div>
      <form onSubmit={event => { event.preventDefault(); ask(); }} className="flex flex-col gap-2 sm:flex-row"><label htmlFor="home-question" className="sr-only">Ask a question about your data</label><input id="home-question" value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask a question about your data…" className="h-11 min-w-0 flex-1 rounded-xl border border-border bg-background px-3.5 text-sm text-foreground outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-primary/35" /><Button type="submit" disabled={!question.trim()} className="h-11 px-5"><Send aria-hidden="true" /> Ask your data</Button></form>
      <div className="mt-3 flex flex-wrap items-center gap-2"><span className="text-xs text-muted-foreground">Try asking</span>{EXAMPLES[industry].map(example => <button key={example} type="button" onClick={() => setQuestion(example)} className="rounded-full border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">{example}</button>)}</div>
    </section>

    <section aria-labelledby="home-actions-heading"><h2 id="home-actions-heading" className="mb-3 text-sm font-semibold">Start with a task</h2><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{ACTIONS.map((action, index) => { const Icon = action.icon; const href = "href" in action ? action.href : reportHref; const description = index === 0 && !askbi ? "Explore and build charts with Analytics Builder." : action.description; return <Link key={action.title} href={href} className="group flex min-h-32 flex-col rounded-xl border border-border bg-surface-raised p-4 shadow-[var(--shadow-card)] transition-[border-color,transform] hover:-translate-y-0.5 hover:border-primary/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"><span className="mb-3 flex items-center justify-between"><span className="rounded-lg bg-primary/10 p-2 text-primary"><Icon className="size-4" aria-hidden="true" /></span><ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" aria-hidden="true" /></span><strong className="text-sm font-semibold">{action.title}</strong><span className="mt-1 text-xs leading-relaxed text-muted-foreground">{description}</span></Link>; })}</div></section>

    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.55fr)_minmax(280px,.85fr)]">
      <RecentWork saved={saved} reports={reports} askbi={askbi} reportHref={reportHref} />
      <section aria-labelledby="home-health-heading" className="rounded-xl border border-border bg-surface-raised p-5 shadow-[var(--shadow-card)]"><div className="mb-4 flex items-center justify-between gap-2"><h2 id="home-health-heading" className="font-semibold">Data health</h2><Link href="/data-quality" className="text-xs font-medium text-primary hover:underline">Open Data Trust</Link></div><div className="space-y-3 text-xs"><HealthRow label="Connection" value={sourceState} tone={sourceTone} /><HealthRow label="Readiness" value={readiness.isPending ? "Checking…" : readiness.isError ? "Probe unavailable" : readiness.data?.status === "ready" ? "Ready" : readiness.data?.status === "degraded" ? "Degraded" : "Not ready"} /><HealthRow label="Last checked" value={readiness.isPending ? "Checking…" : checked ?? "Not reported"} /><HealthRow label="Trust incidents" value={trust.isPending ? "Checking…" : trust.isError ? "Unavailable" : trust.data ? String(trust.data.hero.activeIncidents) : "Not reported"} /></div><p className="mt-4 border-t border-border pt-3 text-[11px] text-muted-foreground">Connection readiness and data trust are separate checks.</p><button type="button" onClick={() => setSourcesOpen(value => !value)} aria-expanded={sourcesOpen} className="mt-3 text-xs font-medium text-primary hover:underline focus-visible:outline-2 focus-visible:outline-primary">{sourcesOpen ? "Hide source details" : "View source details"}</button>{sourcesOpen && <div className="mt-4 border-t border-border pt-4"><ConnectedDataSources /></div>}</section>
    </div>

    <Dialog.Root open={tourOpen} onOpenChange={setTourOpen}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-black/65" /><Dialog.Content className="fixed inset-3 z-50 overflow-y-auto rounded-2xl border border-border bg-background p-3 shadow-[var(--shadow-raised)] outline-none sm:inset-6 sm:p-5" aria-describedby="home-tour-description"><div className="mb-3 flex items-start justify-between gap-3"><div><Dialog.Title className="text-lg font-semibold">See how Ask Me works</Dialog.Title><Dialog.Description id="home-tour-description" className="text-xs text-muted-foreground">Three illustrative scenes. Example figures are not live results.</Dialog.Description></div><Dialog.Close asChild><Button variant="ghost" size="icon" aria-label="Close product tour"><X /></Button></Dialog.Close></div><HomeStory /></Dialog.Content></Dialog.Portal></Dialog.Root>
  </main>;
}

function HealthRow({ label, value, tone = "text-foreground" }: { label: string; value: string; tone?: string }) {
  return <p className="flex items-start justify-between gap-3"><span className="text-muted-foreground">{label}</span><span className={`text-right font-medium ${tone}`}>{value}</span></p>;
}

function RecentWork({ saved, reports, askbi, reportHref }: {
  saved: ReturnType<typeof useQuery<SavedQuestion[]>>;
  reports: ReturnType<typeof useQuery<BiReport[]>>;
  askbi: boolean;
  reportHref: string;
}) {
  return <section aria-labelledby="home-continue-heading" className="min-w-0 rounded-xl border border-border bg-surface-raised p-5 shadow-[var(--shadow-card)]"><div className="mb-4 flex items-center justify-between gap-2"><div><h2 id="home-continue-heading" className="font-semibold">Continue your work</h2><p className="text-xs text-muted-foreground">Your saved questions{askbi ? " and reports" : ""} for this data context.</p></div><Link href="/saved-questions" className="text-xs font-medium text-primary hover:underline">View saved questions</Link></div>
    <div className="grid gap-4 sm:grid-cols-2">
      <div><h3 className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground"><BookOpen className="size-3.5" aria-hidden="true" /> Saved questions</h3>{saved.isPending ? <p role="status" className="text-xs text-muted-foreground">Loading saved questions…</p> : saved.isError ? <p role="alert" className="text-xs text-danger">Saved questions are unavailable. <Link href="/saved-questions" className="underline">Open library</Link></p> : saved.data?.length ? <ul className="space-y-1">{saved.data.slice(0, 3).map(item => <li key={item.id}><Link href={`/chat?q=${encodeURIComponent(item.question)}`} className="block rounded-lg border border-border/70 bg-background/65 px-3 py-2.5 hover:border-primary/35 focus-visible:outline-2 focus-visible:outline-primary"><span className="block truncate text-sm font-medium">{item.title}</span><span className="mt-0.5 block truncate text-xs text-muted-foreground">{item.question}</span>{when(item.createdAt) && <span className="mt-1 block text-[11px] text-muted-foreground">Saved {when(item.createdAt)}</span>}</Link></li>)}</ul> : <p className="text-xs text-muted-foreground">No saved questions yet. <Link href="/chat" className="font-medium text-primary hover:underline">Ask your first question</Link>.</p>}</div>
      <div><h3 className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground"><FileChartColumnIncreasing className="size-3.5" aria-hidden="true" /> {askbi ? "Saved reports" : "Reports"}</h3>{!askbi ? <p className="text-xs text-muted-foreground">Open Analytics Builder to create or continue a report. <Link href={reportHref} className="font-medium text-primary hover:underline">Open builder</Link>.</p> : reports.isPending ? <p role="status" className="text-xs text-muted-foreground">Loading reports…</p> : reports.isError ? <p role="alert" className="text-xs text-danger">Saved reports are unavailable. <Link href={reportHref} className="underline">Open Auto Report</Link></p> : reports.data?.length ? <ul className="space-y-1">{reports.data.slice(0, 3).map(item => <li key={item.id}><Link href={`/analytics-builder?mode=auto&askbiReport=${encodeURIComponent(item.id)}`} className="flex items-center justify-between gap-2 rounded-lg border border-border/70 bg-background/65 px-3 py-2.5 text-sm font-medium hover:border-primary/35 focus-visible:outline-2 focus-visible:outline-primary"><span className="truncate">{item.title}</span><ArrowRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" /></Link></li>)}</ul> : <p className="text-xs text-muted-foreground">No saved reports yet. <Link href={reportHref} className="font-medium text-primary hover:underline">Create a report</Link>.</p>}</div>
    </div>
  </section>;
}
