"use client";

import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { MessageSquare, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRegionAccess } from "@/hooks/use-session";
import { ConversationPanel } from "./conversation-panel";
import { ReportCanvas } from "./report-canvas";
import { ReportFilters } from "./report-filters";
import { createOutlookDraft, getOutlookToken, outlookConfigured, prepareOutlookAuth } from "./outlook-draft";
import { reportReady, useAskBI } from "./use-askbi";

export function AskBI() {
  const bi = useAskBI();
  const region = useRegionAccess();
  const [question, setQuestion] = React.useState("");
  const [drawer, setDrawer] = React.useState(false);
  const [sidebar, setSidebar] = React.useState(true);
  const [rename, setRename] = React.useState(false);
  const [title, setTitle] = React.useState("");
  const [outlookBusy, setOutlookBusy] = React.useState(false);
  const [outlookReady, setOutlookReady] = React.useState(false);
  const [outlookError, setOutlookError] = React.useState("");
  const [draftLink, setDraftLink] = React.useState("");
  const reportRoot = React.useRef<HTMLDivElement>(null);
  const openedLink = React.useRef(false);
  const plan = bi.report?.state.plan ?? null;
  const busy = Boolean(bi.status) || outlookBusy;
  const exportReady = reportReady(plan, bi.results);
  React.useEffect(() => {
    if (!outlookConfigured()) return;
    let active = true;
    void prepareOutlookAuth()
      .then(() => { if (active) setOutlookReady(true); })
      .catch(cause => { if (active) setOutlookError(cause instanceof Error ? cause.message : "Outlook could not connect."); });
    return () => { active = false; };
  }, []);
  React.useEffect(() => {
    if (openedLink.current || !bi.capability?.enabled) return;
    const id = new URLSearchParams(window.location.search).get("askbiReport");
    if (!id) { openedLink.current = true; return; }
    const item = bi.saved.find(candidate => !candidate.source && candidate.id === id);
    if (item) { openedLink.current = true; void bi.open(item); }
  }, [bi]);
  async function draftInOutlook() {
    if (!bi.report || !plan || !reportRoot.current || !exportReady || outlookBusy || !outlookReady) return;
    setOutlookBusy(true); setOutlookError(""); setDraftLink("");
    try {
      const token = await getOutlookToken();
      const saved = bi.report.saved ? bi.report : await bi.command("save");
      if (!saved?.saved) throw new Error("The report could not be saved. Try Save report, then retry the Outlook draft.");
      setDraftLink(await createOutlookDraft(saved, bi.results, bi.briefing, reportRoot.current, region.label, token));
    } catch (cause) { setOutlookError(cause instanceof Error ? cause.message : "Outlook could not create the draft."); }
    finally { setOutlookBusy(false); }
  }
  const focusPanel = (id: string) => { bi.setSelected(id); setDrawer(false); document.getElementById(`askbi-panel-${id}`)?.scrollIntoView({ block: "nearest" }); };
  const chooseExample = (text: string) => { setQuestion(text); setSidebar(true); if (window.innerWidth < 1024) setDrawer(true); };
  function ask() { if (!question.trim() || busy) return; void bi.command("ask", question.trim()); setQuestion(""); }
  const chat = <ConversationPanel turns={bi.turns} question={question} setQuestion={setQuestion} selectedTitle={plan?.panels.find(panel => panel.id === bi.selected)?.title}
    status={bi.status} onAsk={ask} onStop={bi.stop} onWholeReport={() => bi.setSelected(null)} onRetry={() => { if (!outlookBusy) void bi.command("ask", "", undefined, bi.selected, true); }} onFocus={focusPanel} disabled={!bi.capability?.enabled || outlookBusy} />;

  if (bi.capabilityError || (bi.capability && !bi.capability.enabled)) return <section className="rounded-xl border border-border bg-surface-raised p-6" role="alert"><h2 className="font-semibold">AskBI is not available on this API</h2><p className="mt-2 text-sm text-muted-foreground">{bi.capabilityError || "This frontend includes AskBI, but the API feature is disabled for the active industry. Custom Report remains available."}</p><details className="mt-4 text-xs"><summary>Deployment details</summary><p className="mt-2">Frontend: askbi-v2. API requires ASK_ME_ASKBI_ENABLED=true and migration 0014_bi_reports. Restart the API; rebuild the frontend after changing its public flag.</p></details></section>;
  if (!bi.capability) return <p role="status" className="p-6 text-sm text-muted-foreground">Checking reporting capabilities…</p>;
  return <div className="space-y-5">
    <header className="flex flex-wrap items-center justify-between gap-4">
      <div className="min-w-0"><p className="text-xs font-medium text-primary">AskBI · Automotive</p><h2 className="mt-1 text-xl font-semibold tracking-tight">{plan?.title ?? "New report"}</h2><p className="mt-1 text-xs text-muted-foreground">{bi.report ? `Revision ${bi.report.revision} · ${bi.report.saved ? "Saved report" : "Draft — save to keep in your library"}` : "Explore performance with governed analytics"}</p></div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor="askbi-saved">Open saved report</label><select id="askbi-saved" className="max-w-56 rounded-lg border border-input bg-background p-2 text-sm" value="" disabled={busy} onChange={event => { const item = bi.saved[Number(event.target.value)]; if (item) void bi.open(item); }}><option value="">Open saved…</option>{bi.saved.map((item, i) => <option key={`${item.source ?? "bi"}:${item.id}`} value={i}>{item.title}{item.source ? ` · ${item.source}` : ""}</option>)}</select>
        <Button variant="secondary" disabled={!plan || busy} onClick={() => void bi.command("save")}>Save report</Button>
        <Button variant="ghost" disabled={!plan || busy} onClick={() => void bi.command("refresh")}>Refresh</Button>
        <Button variant="ghost" disabled={!bi.report?.state.previous || busy} onClick={() => void bi.command("undo")}>Undo</Button>
        <Button variant="ghost" disabled={!plan || busy} onClick={() => { setTitle(plan?.title ?? ""); setRename(!rename); }}>Rename</Button>
        <Button variant="ghost" disabled={busy} onClick={() => { bi.reset(); setQuestion(""); }}>New report</Button>
        {plan && <Button variant="secondary" disabled={!exportReady || busy} onClick={() => window.print()} title="Choose Save as PDF in the print dialog">Export PDF</Button>}
        {plan && outlookConfigured() && <Button variant="secondary" disabled={!exportReady || busy || !outlookReady} onClick={() => void draftInOutlook()}>{outlookBusy ? "Creating draft…" : outlookReady ? "Create Outlook draft" : "Connecting Outlook…"}</Button>}
        {plan && <Button variant="ghost" disabled={!exportReady || busy} onClick={() => {
          const subject = encodeURIComponent(`Ask Me · ${plan.title}`);
          const body = encodeURIComponent(`Ask Me report: ${plan.title}\nPeriod: ${plan.panels[0]?.spec.dateFrom} to ${plan.panels[0]?.spec.dateTo}\nMake: ${plan.reportFilter?.make ?? "All makes"}\nRegion filter: ${plan.reportFilter?.region ?? "All permitted regions"}\nRegion access: ${region.label}\n\nAttach the PDF exported from AskBI before sending. Recipients must be authorized for the data.`);
          window.location.href = `mailto:?subject=${subject}&body=${body}`;
        }} title="Opens your default mail app; attach the exported PDF before sending">Manual email draft</Button>}
        <Button variant="secondary" className="hidden lg:inline-flex" onClick={() => setSidebar(!sidebar)} aria-pressed={sidebar}><MessageSquare className="mr-2 size-4" />{sidebar ? "Hide chat" : "AskBI"}</Button>
        <Button variant="secondary" className="lg:hidden" onClick={() => setDrawer(true)}><MessageSquare className="mr-2 size-4" />AskBI</Button>
      </div>
    </header>
    {rename && <form className="flex gap-2" onSubmit={event => { event.preventDefault(); if (busy) return; void bi.command("rename", "", title); setRename(false); }}><label className="sr-only" htmlFor="askbi-title">Report title</label><input id="askbi-title" className="min-w-0 flex-1 rounded-lg border border-input bg-background p-2 text-sm" value={title} onChange={event => setTitle(event.target.value)} maxLength={160} disabled={busy} /><Button disabled={busy || !title.trim()}>Apply title</Button></form>}
    {bi.error && <p role="alert" className="rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{bi.error}</p>}
    {outlookError && <p role="alert" className="rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{outlookError}</p>}
    {draftLink && <p role="status" className="text-sm">Outlook draft created for your review. <a className="text-primary underline" href={draftLink} target="_blank" rel="noopener noreferrer">Open draft</a>. Review recipients before sending.</p>}
    {plan && !outlookConfigured() && <p className="text-xs text-muted-foreground">Outlook drafts with charts and PDF need a Microsoft Entra connection. Use Manual email draft and attach the exported PDF until it is configured.</p>}
    {bi.report?.warning && <p className="text-sm text-muted-foreground">{bi.report.warning}</p>}
    {plan && <ReportFilters key={JSON.stringify(plan.reportFilter ?? plan.panels[0]?.spec.dateFrom)} plan={plan} busy={Boolean(bi.status) || outlookBusy} hideRegionFilter={region.hideRegionFilter} onApply={selection => void bi.command("filter", "", undefined, undefined, false, selection)} />}
    <div className={`grid items-start gap-5 ${sidebar ? "lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_360px]" : ""}`}>
      <div className="min-w-0"><div ref={reportRoot} className="askbi-printable"><ReportCanvas plan={plan} results={bi.results} selected={bi.selected} onSelect={id => { bi.setSelected(id); setSidebar(true); }} onCommand={(...args) => void bi.command(...args)} onRetry={id => { const panel = plan?.panels.find(p => p.id === id); if (panel) void bi.retryPanel(panel); }} onExample={chooseExample} busy={Boolean(bi.status) || outlookBusy} briefing={bi.briefing} scopeLabel={region.label} /></div></div>
      {sidebar && <aside className="sticky top-4 hidden h-[calc(100dvh-23rem)] min-h-[26rem] max-h-[48rem] overflow-hidden rounded-2xl border border-border bg-surface-raised lg:block" aria-label="Report assistant">{chat}</aside>}
    </div>
    <Dialog.Root open={drawer} onOpenChange={setDrawer}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" /><Dialog.Content className="fixed inset-y-0 right-0 z-50 w-full max-w-md border-l border-border bg-background shadow-lg"><Dialog.Title className="sr-only">AskBI report assistant</Dialog.Title><Dialog.Description className="sr-only">Ask a question about this report or refine a selected chart.</Dialog.Description><Dialog.Close className="absolute right-3 top-3 z-10 rounded p-1 focus-visible:outline-ring" aria-label="Close conversation"><X className="size-4" /></Dialog.Close>{chat}</Dialog.Content></Dialog.Portal></Dialog.Root>
    <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Processing and deployment details</summary><p className="mt-2">Frontend askbi-v2 · API {bi.capability.engine} · schema {bi.capability.schemaVersion} · {bi.capability.migration}</p>{bi.saveError && <p className="mt-2">{bi.saveError}</p>}{bi.report && <p className="mt-2">Last turn: {Math.round(bi.report.state.usage.elapsedMs)} ms · {bi.report.state.usage.llmCalls} AI calls · {bi.report.state.usage.tokens} recorded tokens{bi.report.state.usage.usageComplete ? "" : " (usage incomplete)"}</p>}{bi.narrationUsage && <p>Narration: {bi.narrationUsage.llmCalls} AI calls · {bi.narrationUsage.tokens} recorded tokens</p>}{plan?.panels.map(panel => <p key={panel.id}>{panel.title}: {bi.results[panel.id]?.queryCount ?? "—"} database calls · {Math.round(bi.results[panel.id]?.elapsedMs ?? 0)} ms</p>)}</details>
  </div>;
}
