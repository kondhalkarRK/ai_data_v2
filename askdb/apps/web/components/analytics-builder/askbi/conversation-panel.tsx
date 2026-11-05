"use client";

import * as React from "react";
import type { BiTurn } from "@nql/shared-types";
import { ArrowUp, MessageSquare, Square } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ConversationPanel({ turns, selectedTitle, question, setQuestion, status, onAsk, onStop, onWholeReport, onRetry, onFocus, disabled }: {
  turns: BiTurn[]; selectedTitle?: string; question: string; setQuestion: (value: string) => void;
  status: string; onAsk: () => void; onStop: () => void; onWholeReport: () => void;
  onRetry: () => void; onFocus: (id: string) => void; disabled: boolean;
}) {
  const end = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => { end.current?.scrollIntoView?.({ block: "nearest" }); }, [turns.length]);
  const id = React.useId();
  return <div className="flex h-full min-h-0 flex-col">
    <header className="border-b border-border p-4"><h2 className="flex items-center gap-2 text-sm font-semibold"><MessageSquare className="size-4 text-primary" /> AskBI</h2><p className="mt-1 text-xs text-muted-foreground">Build and refine your report in conversation.</p></header>
    <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4" aria-label="AskBI conversation" role="log" aria-live="polite">
      {turns.length === 0 && <div className="py-4 text-sm text-muted-foreground"><p>Describe the analysis you need. I’ll use your available automotive data and approved KPI definitions.</p><p className="mt-3">You can ask for one value, a chart, or a report. Select a chart to refine it.</p></div>}
      {turns.map(turn => <div key={turn.id} className="space-y-2">
        <p className="ml-6 rounded-xl bg-primary/10 px-3 py-2 text-sm text-foreground">{turn.question}</p>
        <div className="text-sm leading-relaxed"><p className={turn.kind === "error" ? "text-destructive" : "text-foreground"}>{turn.answer}</p>
          {turn.kind === "clarification" && <p className="mt-2 text-xs text-muted-foreground">Reply below. I’ll keep your original request.</p>}
          {turn.changedPanelIds.length > 0 && <button type="button" onClick={() => { const target = turn.changedPanelIds[0]; if (target) onFocus(target); }} className="mt-2 text-xs text-primary underline">View affected analysis</button>}
          {turn.kind === "error" && turn === turns.at(-1) && <Button variant="ghost" size="sm" disabled={Boolean(status)} onClick={onRetry}>Retry request</Button>}
        </div>
      </div>)}<div ref={end} />
    </div>
    <form className="border-t border-border p-4" onSubmit={event => { event.preventDefault(); onAsk(); }}>
      <div className="mb-2 flex items-center justify-between gap-2 text-xs"><span className="truncate text-muted-foreground">{selectedTitle ? `Selected: ${selectedTitle}` : "Whole report"}</span>{selectedTitle && <button type="button" onClick={onWholeReport} className="shrink-0 text-primary">Clear selection</button>}</div>
      <label htmlFor={id} className="sr-only">Ask a report question</label>
      <textarea id={id} value={question} onChange={event => setQuestion(event.target.value)} maxLength={2000} rows={3} disabled={disabled} placeholder="Daily sales last week, by model…" className="w-full resize-y rounded-xl border border-input bg-background p-3 text-sm placeholder:text-muted-foreground focus-visible:outline-ring" />
      <div className="mt-2 flex items-center justify-between gap-2"><span className="text-[11px] text-muted-foreground">Automotive · Governed data</span>{status ? <Button type="button" variant="secondary" size="sm" onClick={onStop}><Square className="mr-1 size-3" />Stop</Button> : <Button size="sm" type="submit" disabled={disabled || !question.trim()}><ArrowUp className="mr-1 size-4" />Send</Button>}</div>
      <p role="status" className="mt-2 min-h-4 text-xs text-muted-foreground">{status}</p>
    </form>
  </div>;
}
