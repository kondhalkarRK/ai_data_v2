"use client";

import type { IndustryListResponse, ReadinessResponse } from "@nql/shared-types";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import { BrandWordmark } from "@/components/brand/wordmark";
import { Button } from "@/components/ui/button";
import { useActiveIndustry, useRegionAccess, useSession } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";
import styles from "./home-workspace.module.css";

const EXAMPLES = {
  automotive: ["Revenue by month", "Top models by units sold", "Units sold by region"],
  insurance: ["Premium by month", "Claims by region", "Loss ratio by product"],
} as const;

function subscribeToClock(callback: () => void) {
  const timer = window.setInterval(callback, 60_000);
  return () => window.clearInterval(timer);
}
function localGreeting() {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

export function HomeWorkspace() {
  const router = useRouter();
  const industry = useActiveIndustry();
  const region = useRegionAccess();
  const { data: user } = useSession();
  const greeting = React.useSyncExternalStore(subscribeToClock, localGreeting, () => "Welcome");
  const [question, setQuestion] = React.useState("");
  const [detailsOpen, setDetailsOpen] = React.useState(false);
  const industries = useQuery({ queryKey: ["industries"], queryFn: () => apiClient.get<IndustryListResponse>("/api/v1/industries"), staleTime: 60_000 });
  const readiness = useQuery({ queryKey: ["readiness"], queryFn: () => apiClient.get<ReadinessResponse>("/ready"), refetchInterval: 30_000, staleTime: 0 });
  const pack = industries.data?.industries.find(item => item.id === industry);
  const activeName = industry === "automotive" ? "Automotive" : "Insurance";
  const databaseState = industries.isPending ? "Checking…" : industries.isError || !pack ? "Unavailable" : pack.databaseAvailable ? "Connected" : "Disconnected";
  const apiState = readiness.isPending ? "Checking…" : readiness.isError ? "Unavailable" : readiness.data?.status === "ready" ? "Ready" : readiness.data?.status === "degraded" ? "Degraded" : "Not ready";
  const refreshing = industries.isFetching || readiness.isFetching;
  const checkedAt = !readiness.isError && readiness.data?.checkedAt ? new Date(readiness.data.checkedAt) : null;
  const checked = checkedAt && Number.isFinite(checkedAt.valueOf()) ? checkedAt.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }) : null;
  const name = user?.fullName?.trim().split(/\s+/)[0] || user?.username || "there";

  function ask() {
    const trimmed = question.trim();
    if (trimmed) router.push(`/chat?q=${encodeURIComponent(trimmed)}`);
  }

  return <main className="mx-auto w-full max-w-5xl min-w-0 pb-12 pt-2 sm:pt-5">
    <header className="space-y-5">
      <div><h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{greeting}, {name}</h1><p className="mt-2 text-sm text-muted-foreground">What would you like to explore today?</p></div>
      <div aria-label="Current data context" className="flex flex-wrap items-center gap-2 text-xs">
        <StatusChip label="PostgreSQL" state={databaseState} healthy={!industries.isError && pack?.databaseAvailable === true} open={detailsOpen} onClick={() => setDetailsOpen(value => !value)} />
        <StatusChip label={activeName} state="Active" healthy={false} open={detailsOpen} onClick={() => setDetailsOpen(value => !value)} />
        <StatusChip label="API" state={apiState} healthy={!readiness.isError && readiness.data?.status === "ready"} open={detailsOpen} onClick={() => setDetailsOpen(value => !value)} />
        <button type="button" aria-label="Refresh connections" disabled={refreshing} onClick={() => { void industries.refetch(); void readiness.refetch(); }} className="rounded-full p-2 text-muted-foreground hover:bg-surface-raised hover:text-foreground focus-visible:outline-2 focus-visible:outline-primary disabled:opacity-50"><RefreshCw className={`size-3.5 ${refreshing ? "motion-safe:animate-spin" : ""}`} aria-hidden="true" /></button>
        <span className="text-muted-foreground" role="status">{refreshing ? "Checking connections…" : checked ? `Last checked ${checked}` : "Last check unavailable"}</span>
      </div>
      {detailsOpen && <section id="home-connection-details" aria-label="Connection details" className="rounded-xl border border-border bg-surface-raised p-4 text-sm">
        <div className="flex items-center justify-between gap-3"><h2 className="font-medium">Connection details</h2><button type="button" onClick={() => setDetailsOpen(false)} className="text-xs text-primary hover:underline">Hide details</button></div>
        <dl className="mt-3 grid gap-3 sm:grid-cols-3"><div><dt className="text-xs text-muted-foreground">Active analytics database</dt><dd className="mt-1">PostgreSQL · {databaseState}</dd></div><div><dt className="text-xs text-muted-foreground">Permission scope</dt><dd className="mt-1">{region.hideRegionFilter && !region.unrestricted ? "Restricted regions" : region.label}</dd></div><div><dt className="text-xs text-muted-foreground">Semantic pack</dt><dd className="mt-1">{industries.isError || !pack ? "Unavailable" : pack.semanticPackLoaded ? "Loaded" : "Not loaded"}</dd></div></dl>
        <p className="mt-3 text-xs text-muted-foreground">Connection status reflects the latest checks. Data freshness and quality are available in Data Trust.</p>
      </section>}
    </header>

    <section aria-labelledby="home-ask-heading" className="mx-auto flex max-w-3xl flex-col items-center pb-6 pt-8 text-center sm:pt-12">
      <div className={styles.brandIntro}>
        <BrandWordmark size="hero" className={styles.wordmark} />
        <p className={styles.tagline}>Your data. Explained.</p>
      </div>
      <div className={styles.visual} aria-hidden="true">
        <div className={styles.halo} />
        <svg viewBox="0 0 480 180" className={styles.art} fill="none">
          <path d="M56 130H424M56 85H424M56 40H424" stroke="currentColor" opacity=".07" />
          <path className={styles.connector} d="M64 125L140 98L214 112L286 62L358 76L416 32" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          {[64, 140, 214, 286, 358, 416].map((x, i) => <g key={x} className={styles.point} style={{ animationDelay: `${i * 120}ms` }}><circle cx={x} cy={[125, 98, 112, 62, 76, 32][i]} r="10" fill="currentColor" opacity=".1" /><circle cx={x} cy={[125, 98, 112, 62, 76, 32][i]} r="3.5" fill="currentColor" /></g>)}
          {[52, 78, 64, 114, 100, 144].map((height, i) => <rect key={i} className={styles.bar} style={{ animationDelay: `${i * 100}ms` }} x={52 + i * 70} y={166 - height} width="25" height={height} rx="5" fill="currentColor" opacity=".08" />)}
        </svg>
      </div>
      <h2 id="home-ask-heading" className="mt-6 text-3xl font-semibold tracking-tight sm:text-4xl">Ask anything about your data</h2>
      <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted-foreground">From a quick question to your next insight. Explore your {activeName.toLowerCase()} data in your own words.</p>
      <form onSubmit={event => { event.preventDefault(); ask(); }} className="mt-7 flex w-full flex-col gap-3 rounded-2xl border border-border bg-surface-raised p-3 shadow-[var(--shadow-card)] sm:flex-row sm:items-center sm:p-2">
        <label htmlFor="home-question" className="sr-only">Ask a question about your data</label>
        <input id="home-question" value={question} onChange={event => setQuestion(event.target.value)} placeholder={industry === "automotive" ? "How are sales performing across regions?" : "How are claims performing across regions?"} className="h-12 min-w-0 flex-1 rounded-xl bg-transparent px-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-primary/40" />
        <Button type="submit" disabled={!question.trim()} className="h-12 rounded-xl px-6">Ask <ArrowUpRight aria-hidden="true" /></Button>
      </form>
      <div className="mt-4 flex flex-wrap justify-center gap-2">{EXAMPLES[industry].map(example => <button key={example} type="button" onClick={() => setQuestion(example)} className="rounded-full border border-border px-3 py-2 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-surface-raised hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">{example}</button>)}</div>
      <p className="mt-6 text-xs text-muted-foreground">Your questions stay within your permitted data access.</p>
    </section>
  </main>;
}

function StatusChip({ label, state, healthy, open, onClick }: { label: string; state: string; healthy: boolean; open: boolean; onClick: () => void }) {
  return <button type="button" aria-expanded={open} aria-controls="home-connection-details" onClick={onClick} className="inline-flex items-center gap-2 rounded-full border border-border bg-surface-raised px-3 py-2 text-xs transition-colors hover:border-primary/40 focus-visible:outline-2 focus-visible:outline-primary"><span aria-hidden="true" className={`size-1.5 rounded-full ${healthy ? "bg-success" : state === "Disconnected" || state === "Not ready" || state === "Unavailable" ? "bg-danger" : state === "Active" ? "bg-primary" : "bg-muted-foreground"}`} /><span>{label} <span className="text-muted-foreground">· {state}</span></span></button>;
}
