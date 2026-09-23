"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { useSearchParams } from "next/navigation";

import { type ActionKey } from "@/components/chat/action-toolbar";
import { ResponseCard } from "@/components/chat/response-card";
import { applyChatSseEvent } from "@/components/chat/sse";
import type { ChatMessage } from "@/components/chat/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui-store";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

export function ChatWorkspace() {
  const industry = useActiveIndustry();
  const searchParams = useSearchParams();
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [webRetrieval, setWebRetrieval] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const historyIdRef = useRef<string | null>(null);
  const bootstrapped = useRef(false);
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const llmModel = useUiStore((s) => s.llmModel);
  const llmTemperature = useUiStore((s) => s.llmTemperature);
  const llmTopP = useUiStore((s) => s.llmTopP);
  const llmTopK = useUiStore((s) => s.llmTopK);

  useEffect(() => {
    const seeded = searchParams.get("q");
    if (seeded && !bootstrapped.current) {
      bootstrapped.current = true;
      setQuestion(seeded);
      void runAsk(seeded);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot deep link
  }, [searchParams]);

  useEffect(() => {
    const node = scrollerRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [messages, busy]);

  async function runAsk(text: string) {
    if (!text.trim() || busy) return;
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      question: text.trim(),
    };
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      userMessage,
      { id: assistantId, role: "assistant", narrative: "" },
    ]);
    setBusy(true);
    setQuestion("");
    const controller = new AbortController();
    abortRef.current = controller;
    historyIdRef.current = null;

    try {
      const payload = {
        question: userMessage.question,
        conversationId,
        webRetrieval,
        model: llmModel || undefined,
        temperature: llmTemperature,
        topP: llmTopP,
        topK: llmTopK,
      };
      // Vercel rewrites buffer SSE, so production uses one JSON round-trip.
      const sync = await apiClient.post<{
        events: Array<{ event: string; data: Record<string, unknown> }>;
      }>("/api/v1/chat/ask-sync", payload, { industry });
      for (const frame of sync.events ?? []) {
        const eventName = frame.event;
        const data = frame.data ?? {};
        if (eventName === "stage" && data.historyId) {
          historyIdRef.current = String(data.historyId);
        }
        if (eventName === "done" && data.conversationId) {
          setConversationId(String(data.conversationId));
        }
        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId
              ? applyChatSseEvent(message, eventName, data)
              : message,
          ),
        );
      }
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId
              ? { ...message, cancelled: true, narrative: "Cancelled." }
              : message,
          ),
        );
      } else {
        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId
              ? { ...message, error: error instanceof Error ? error.message : "Chat failed" }
              : message,
          ),
        );
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await runAsk(question);
  }

  async function cancelInFlight() {
    const historyId = historyIdRef.current;
    abortRef.current?.abort();
    if (historyId) {
      try {
        await fetch(`${API_BASE_URL}/api/v1/chat/cancel/${historyId}`, {
          method: "POST",
          credentials: "include",
          headers: {
            "x-industry": industry,
            "x-csrf-token": readCookie("nql_csrf") ?? "",
          },
        });
      } catch {
        // Best-effort cancel record.
      }
    }
  }

  async function handleAction(key: ActionKey, message: ChatMessage) {
    if (key === "copy") {
      const payload = message.sql || message.narrative || "";
      await navigator.clipboard.writeText(payload);
      flash("Copied to clipboard");
      return;
    }
    if (key === "export") {
      if (!message.rows?.length || !message.columns?.length) {
        flash("Nothing to export yet");
        return;
      }
      const header = message.columns.join(",");
      const body = message.rows
        .map((row) =>
          message.columns!.map((column) => csvEscape(String(row[column] ?? ""))).join(","),
        )
        .join("\n");
      downloadText(`ask-db-${message.id}.csv`, `${header}\n${body}`);
      flash("CSV downloaded");
      return;
    }
    if (key === "save") {
      const title = (message.narrative || "Saved insight").slice(0, 80);
      const lastUser =
        [...messages].reverse().find((item) => item.role === "user")?.question ?? title;
      try {
        await apiClient.post("/api/v1/questions", {
          title,
          question: lastUser,
          sqlText: message.sql ?? null,
        });
        flash("Insight saved");
      } catch {
        flash("Save failed");
      }
    }
  }

  function flash(text: string) {
    setToast(text);
    window.setTimeout(() => setToast(null), 1800);
  }

  const lastUserQuestion =
    [...messages].reverse().find((message) => message.role === "user")?.question ?? "";

  return (
    <div className="flex h-[calc(100dvh-var(--topbar-height)-2rem)] min-h-[420px] flex-col gap-3 lg:h-[calc(100dvh-var(--topbar-height)-3rem)]">
      <div className="flex shrink-0 items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">AI Chat</h1>
          <p className="text-xs text-muted-foreground">
            Grounded NLQ · table, chart, and SQL in one place
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="gap-1.5"
          onClick={() => setPanelOpen((value) => !value)}
          aria-pressed={panelOpen}
        >
          {panelOpen ? (
            <PanelRightClose className="size-3.5" />
          ) : (
            <PanelRightOpen className="size-3.5" />
          )}
          {panelOpen ? "Hide panel" : "Show panel"}
        </Button>
      </div>

      <div
        className={cn(
          "grid min-h-0 flex-1 gap-4",
          panelOpen ? "lg:grid-cols-[minmax(0,1fr)_280px]" : "grid-cols-1",
        )}
      >
        <Card className="flex min-h-0 flex-col overflow-hidden">
          <CardContent className="flex min-h-0 flex-1 flex-col gap-0 p-0">
            <div ref={scrollerRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
              {messages.length === 0 ? (
                <div className="card-supporting border border-dashed border-border/80 px-4 py-8 text-center">
                  <p className="text-sm text-muted-foreground">
                    Try “loss ratio”, “claims by status”, “revenue by month”, “surprise me”, or a
                    what-if like “what if revenue increased 10%”.
                  </p>
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    Press Ctrl/Cmd+K to jump to glossary terms, the semantic graph, or saved
                    insights.
                  </p>
                </div>
              ) : null}
              {messages.map((message) =>
                message.role === "user" ? (
                  <div
                    key={message.id}
                    className="ml-auto max-w-[85%] rounded-[var(--radius-card)] bg-primary px-4 py-2.5 text-sm text-primary-foreground"
                  >
                    {message.question}
                  </div>
                ) : (
                  <ResponseCard
                    key={message.id}
                    message={message}
                    busy={busy}
                    onAsk={(text) => void runAsk(text)}
                    onRetry={
                      lastUserQuestion ? () => void runAsk(lastUserQuestion) : undefined
                    }
                    onAction={(key, msg) => void handleAction(key, msg)}
                  />
                ),
              )}
            </div>

            <form
              className="shrink-0 border-t border-border/60 bg-background/95 px-4 py-3 backdrop-blur"
              onSubmit={onSubmit}
            >
              <label className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={webRetrieval}
                  onChange={(event) => setWebRetrieval(event.target.checked)}
                />
                Opt-in web retrieval (allowlisted hosts only)
              </label>
              <div className="flex gap-2">
                <input
                  className="h-11 flex-1 rounded-[var(--radius-control)] border border-border bg-background px-3 text-sm outline-none ring-primary/20 focus:ring-2"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="Ask a governed analytics question"
                />
                {busy ? (
                  <Button type="button" variant="secondary" onClick={() => void cancelInFlight()}>
                    Cancel
                  </Button>
                ) : (
                  <Button type="submit" className="px-5">
                    Ask
                  </Button>
                )}
              </div>
            </form>
          </CardContent>
        </Card>

        {panelOpen ? (
          <Card className="hidden min-h-0 overflow-hidden lg:flex lg:flex-col">
            <CardContent className="min-h-0 flex-1 space-y-3 overflow-y-auto pt-4">
              <CardTitle className="text-sm">How answers stay honest</CardTitle>
              <CardDescription className="text-xs leading-relaxed">
                Grounding badges only list sources actually used. Ambiguous questions surface
                clarifications instead of a fake confidence score. SQL validation and auto-repair
                are disclosed with the result.
              </CardDescription>
              <p className="text-xs text-muted-foreground">Industry: {industry}</p>
              {conversationId ? (
                <p className="text-2xs text-muted-foreground">Conversation {conversationId}</p>
              ) : null}
              {toast ? (
                <p className="rounded-lg bg-muted/50 px-2 py-1.5 text-xs text-foreground">{toast}</p>
              ) : null}
            </CardContent>
          </Card>
        ) : null}
      </div>

      {toast && !panelOpen ? (
        <p className="fixed bottom-4 right-4 z-40 rounded-lg border border-border bg-background px-3 py-2 text-xs shadow-[var(--shadow-raised)]">
          {toast}
        </p>
      ) : null}
    </div>
  );
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function csvEscape(value: string): string {
  if (/[",\n]/.test(value)) return `"${value.replaceAll('"', '""')}"`;
  return value;
}

function downloadText(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
