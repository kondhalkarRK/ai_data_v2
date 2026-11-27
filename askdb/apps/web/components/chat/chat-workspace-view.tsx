"use client";

import { ArrowUp, PanelRightClose, PanelRightOpen, Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ChatHistory } from "./chat-history";
import { CompactDataAnswer } from "./compact-data-answer";
import { ResponseActions } from "./response-actions";
import { ResponseCard } from "./response-card";
import { ReportPreview } from "./report-preview";
import { AnalyticalAnswer, AnalyticalProgressView } from "./analytical-answer";
import type { ChatMessage } from "./types";
import { useChatSession } from "@/hooks/use-chat-ask";
import { ChatQuotaWidget } from "@/components/governance/chat-quota-widget";
import { Button } from "@/components/ui/button";
import { chatGreeting } from "@/lib/chat-greeting";
import { assistantView, detectAnalysisRequest } from "@/lib/chat-new-ui";
import { cn } from "@/lib/utils";

/** One controller owns both layouts, including drafts and stable response identities. */
export function ChatWorkspaceView({ mode }: { mode: "classic" | "new" }) {
  const chat = useChatSession();
  const [panelOpen, setPanelOpen] = useState(true);
  const scroller = useRef<HTMLDivElement>(null);
  const empty = chat.messages.length === 0;
  const disabled = chat.busy || chat.restoring;
  const classicPanel = mode === "classic" && panelOpen && !empty;
  useEffect(() => {
    const node = scroller.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [chat.messages, chat.busy]);
  function submit(event: FormEvent) { event.preventDefault(); void chat.runAsk(chat.question); }

  return <section aria-label={`${mode === "new" ? "New" : "Classic"} Chat`} className="flex h-[calc(100dvh-var(--topbar-height)-2.5rem)] min-h-[420px] min-w-0 flex-col gap-3 lg:h-[calc(100dvh-var(--topbar-height)-3rem)]">
    <header className="flex min-h-9 shrink-0 flex-wrap items-center justify-between gap-2">
      <Button type="button" variant="ghost" size="sm" className="gap-1.5" disabled={disabled} onClick={chat.newConversation}><Plus className="size-4" /><span className="hidden sm:inline">New chat</span></Button>
      <div className="flex items-center gap-1"><ChatQuotaWidget />{mode === "new" ? <ChatHistory /> : <Button type="button" size="sm" variant="ghost" aria-pressed={panelOpen} aria-label={panelOpen ? "Hide panel" : "Show panel"} onClick={() => setPanelOpen(value => !value)}>{panelOpen ? <PanelRightClose className="size-4" /> : <PanelRightOpen className="size-4" />}</Button>}</div>
    </header>
    {chat.historyError && <p role="status" className="text-center text-xs text-muted-foreground">{chat.historyError}</p>}
    <div className={cn("grid min-h-0 flex-1 gap-4", classicPanel ? "lg:grid-cols-[minmax(0,1fr)_260px]" : "grid-cols-1")}>
      <div className={cn("mx-auto flex min-h-0 w-full min-w-0 flex-col", mode === "new" ? "max-w-[1200px]" : "max-w-[1100px]", empty && "justify-center")}>
        {empty ? <div className="mb-7 px-4 text-center" data-testid="chat-greeting"><h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{chatGreeting(chat.user?.fullName)}</h1><p className="mt-3 text-sm text-muted-foreground sm:text-base">Ask a question about your data.</p></div> : <div ref={scroller} className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden pb-6" aria-label="Conversation"><div className="mx-auto w-full min-w-0 space-y-5 px-1 sm:px-3">{chat.messages.map((message, index) => message.role === "user" ? <div key={message.id} className="ml-auto w-fit max-w-[85%] whitespace-pre-wrap break-words rounded-2xl bg-primary px-4 py-3 text-sm text-primary-foreground">{message.question}</div> : <AssistantAnswer key={message.id} message={message} question={chat.messages[index - 1]?.question ?? ""} mode={mode} />)}</div></div>}
        {chat.restoring && <p role="status" className="mb-3 text-center text-sm text-muted-foreground">Opening conversation…</p>}
        <form onSubmit={submit} className={cn("chat-composer mx-auto w-full shrink-0 rounded-3xl border border-border bg-surface-raised p-3 shadow-[var(--shadow-card)] sm:p-4", empty && "max-w-[860px]")}>
          <div className="flex items-end gap-3"><textarea aria-label="Ask a question" placeholder="Ask about your data" rows={2} className="max-h-40 min-h-14 min-w-0 flex-1 resize-y bg-transparent px-1 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-primary/30" value={chat.question} onChange={event => chat.setQuestion(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!disabled) void chat.runAsk(chat.question); } }} />{chat.busy ? <Button type="button" variant="secondary" onClick={() => void chat.cancelInFlight()}>Cancel</Button> : <Button type="submit" aria-label="Ask" disabled={chat.restoring || !chat.question.trim()} className="size-10 shrink-0 rounded-2xl p-0"><ArrowUp className="size-5" /></Button>}</div>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground" aria-label="Question options">
            <Link href="/analytics-builder" title="Open Analytics Builder to generate a report" className="rounded-full border border-border px-2.5 py-1.5 hover:bg-muted">Generate report ↗</Link>
            <label className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1.5"><input type="checkbox" checked={chat.useDocuments} disabled={chat.user?.capabilities?.ragEnabled === false} onChange={event => chat.setUseDocuments(event.target.checked)} />Unstructured data</label>
            <label className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1.5"><input type="checkbox" checked={chat.webRetrieval} onChange={event => chat.setWebRetrieval(event.target.checked)} />Web retrieval</label>
          </div>
        </form>
      </div>
      {classicPanel && <aside className="hidden overflow-auto rounded-2xl border border-border bg-surface-raised p-4 lg:block"><h2 className="text-sm font-semibold">How answers stay honest</h2><p className="mt-3 text-xs leading-relaxed text-muted-foreground">Grounding badges list sources actually used. Ambiguous questions ask for clarification. SQL validation and auto-repair are disclosed with the result.</p><p className="mt-3 text-xs text-muted-foreground">Industry: {chat.industry}</p></aside>}
    </div>
    {chat.toast && <p role="status" className="fixed bottom-4 right-4 z-40 rounded-lg border border-border bg-background px-3 py-2 text-xs shadow-[var(--shadow-raised)]">{chat.toast}</p>}
  </section>;
}

function AssistantAnswer({ message, question, mode }: { message: ChatMessage; question: string; mode: "classic" | "new" }) {
  const chat = useChatSession();
  const onAsk = (text: string) => { void chat.runAsk(text); };
  const view = assistantView(message);
  return <article className="min-w-0 space-y-2" aria-label="Assistant response">
    {message.analysisProgress ? <AnalyticalProgressView progress={message.analysisProgress} /> : view === "analysis" ? <AnalyticalAnswer message={message} chartRequested={detectAnalysisRequest(question) === "chart"} /> : view === "report" && message.report ? <ReportPreview report={message.report} /> : view === "text" ? <p className="max-w-[85ch] whitespace-pre-wrap break-words text-sm leading-relaxed">{message.narrative || "…"}</p> : mode === "new" && view === "data" ? <CompactDataAnswer message={message} requestedTab={detectAnalysisRequest(question)} busy={chat.busy} onAsk={onAsk} onAction={chat.handleAction} /> : <ResponseCard message={message} busy={chat.busy} onAsk={onAsk} onRetry={() => onAsk(question)} onAction={chat.handleAction} detailsInInfo />}
    <ResponseActions message={message} onAsk={onAsk} busy={chat.busy} />
  </article>;
}
