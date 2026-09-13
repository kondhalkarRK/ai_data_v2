"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { type ActionKey } from "@/components/chat/action-toolbar";
import { ResponseCard } from "@/components/chat/response-card";
import type { ChatMessage, ResponseMeta, ChartPayload, SqlDiffLine } from "@/components/chat/types";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

export function ChatWorkspace() {
  const industry = useActiveIndustry();
  const searchParams = useSearchParams();
  const [question, setQuestion] = useState("Show loss ratio by month");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [webRetrieval, setWebRetrieval] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const historyIdRef = useRef<string | null>(null);
  const bootstrapped = useRef(false);

  useEffect(() => {
    const seeded = searchParams.get("q");
    if (seeded && !bootstrapped.current) {
      bootstrapped.current = true;
      setQuestion(seeded);
      void runAsk(seeded);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot deep link
  }, [searchParams]);

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
      const response = await fetch(`${API_BASE_URL}/api/v1/chat/ask`, {
        method: "POST",
        credentials: "include",
        signal: controller.signal,
        headers: {
          "content-type": "application/json",
          "x-industry": industry,
          "x-csrf-token": readCookie("nql_csrf") ?? "",
        },
        body: JSON.stringify({
          question: userMessage.question,
          conversationId,
          webRetrieval,
        }),
      });
      if (!response.ok || !response.body) {
        throw new Error(`Chat failed (${response.status})`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "message";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const lines = part.split("\n");
          let dataLine = "";
          for (const line of lines) {
            if (line.startsWith("event:")) currentEvent = line.slice(6).trim();
            if (line.startsWith("data:")) dataLine += line.slice(5).trim();
          }
          if (!dataLine) continue;
          const data = JSON.parse(dataLine) as Record<string, unknown>;
          if (currentEvent === "stage" && data.historyId) {
            historyIdRef.current = String(data.historyId);
          }
          if (currentEvent === "done" && data.conversationId) {
            setConversationId(String(data.conversationId));
          }
          setMessages((prev) =>
            prev.map((message) => {
              if (message.id !== assistantId) return message;
              if (currentEvent === "stage" && data.historyId) {
                return { ...message, historyId: String(data.historyId), path: String(data.stage ?? "") };
              }
              if (currentEvent === "sql") {
                return {
                  ...message,
                  sql: String(data.sql ?? ""),
                  path: String(data.path ?? ""),
                  priorSql: data.priorSql ? String(data.priorSql) : undefined,
                  sqlDiff: (data.diff as SqlDiffLine[] | null | undefined) ?? null,
                };
              }
              if (currentEvent === "columns") {
                return { ...message, columns: (data.columns as string[]) ?? [] };
              }
              if (currentEvent === "rows") {
                return { ...message, rows: (data.rows as Array<Record<string, unknown>>) ?? [] };
              }
              if (currentEvent === "chart") {
                return { ...message, chart: data as unknown as ChartPayload };
              }
              if (currentEvent === "meta") {
                return { ...message, meta: data as unknown as ResponseMeta };
              }
              if (currentEvent === "token") {
                return {
                  ...message,
                  narrative: `${message.narrative ?? ""}${String(data.token ?? "")}`,
                };
              }
              if (currentEvent === "clarification") {
                return {
                  ...message,
                  clarification: String(data.question ?? data.message ?? ""),
                  options: (data.options as string[]) ?? [],
                };
              }
              if (currentEvent === "followups") {
                return {
                  ...message,
                  followups: (data.items as string[]) ?? (data.followups as string[]) ?? [],
                };
              }
              if (currentEvent === "citation") {
                const citation = {
                  title: String(data.title ?? ""),
                  snippet: String(data.snippet ?? ""),
                  locator: String(data.locator ?? ""),
                  untrusted: Boolean(data.untrusted),
                };
                return {
                  ...message,
                  citations: [...(message.citations ?? []), citation],
                };
              }
              if (currentEvent === "cancelled") {
                return { ...message, cancelled: true, narrative: "Cancelled." };
              }
              if (currentEvent === "error") {
                return { ...message, error: String(data.message ?? "Chat failed") };
              }
              if (currentEvent === "done") {
                return {
                  ...message,
                  latencyMs: Number(data.latencyMs ?? message.latencyMs ?? 0),
                  historyId: String(data.historyId ?? message.historyId ?? ""),
                };
              }
              return message;
            }),
          );
        }
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
      downloadText(`nql-insight-${message.id}.csv`, `${header}\n${body}`);
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
    <>
      <PageHeader
        title="AI Chat"
        description="Enterprise NLQ with honest grounding, execution timelines, and governed SQL — not a confidence theatre."
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <Card className="min-h-[520px] border-border/70 shadow-sm">
          <CardContent className="flex h-full flex-col gap-3 pt-4">
            <div className="flex-1 space-y-4 overflow-auto pr-1">
              {messages.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-border/70 bg-muted/20 px-4 py-8 text-center">
                  <p className="text-sm text-muted-foreground">
                    Try “loss ratio”, “claims by status”, “revenue by month”, “surprise me”, or a
                    what-if like “what if revenue increased 10%”.
                  </p>
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    Press Ctrl/Cmd+K to jump to glossary terms, the semantic graph, or saved insights.
                  </p>
                </div>
              ) : null}
              {messages.map((message) =>
                message.role === "user" ? (
                  <div
                    key={message.id}
                    className="ml-auto max-w-[85%] rounded-2xl bg-foreground px-4 py-2.5 text-sm text-background"
                  >
                    {message.question}
                  </div>
                ) : (
                  <ResponseCard
                    key={message.id}
                    message={message}
                    busy={busy}
                    onAsk={(text) => void runAsk(text)}
                    onRetry={lastUserQuestion ? () => void runAsk(lastUserQuestion) : undefined}
                    onAction={(key, msg) => void handleAction(key, msg)}
                  />
                ),
              )}
            </div>
            <form className="flex flex-col gap-2 border-t border-border/60 pt-3" onSubmit={onSubmit}>
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={webRetrieval}
                  onChange={(event) => setWebRetrieval(event.target.checked)}
                />
                Opt-in web retrieval (allowlisted hosts only)
              </label>
              <div className="flex gap-2">
                <input
                  className="h-11 flex-1 rounded-xl border border-border bg-background px-3 text-sm shadow-sm outline-none ring-foreground/10 focus:ring-2"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="Ask a governed analytics question"
                />
                {busy ? (
                  <Button type="button" variant="secondary" onClick={() => void cancelInFlight()}>
                    Cancel
                  </Button>
                ) : (
                  <Button type="submit" className="rounded-xl px-5">
                    Ask
                  </Button>
                )}
              </div>
            </form>
          </CardContent>
        </Card>
        <Card className="border-border/70 shadow-sm">
          <CardContent className="space-y-3 pt-4">
            <CardTitle className="text-sm">How answers stay honest</CardTitle>
            <CardDescription className="text-xs leading-relaxed">
              Grounding badges only list sources actually used. Ambiguous questions surface
              clarifications instead of a fake confidence score. SQL validation and auto-repair are
              disclosed in the response header.
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
      </div>
    </>
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
