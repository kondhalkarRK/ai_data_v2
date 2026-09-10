"use client";

import { FormEvent, useRef, useState } from "react";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { useActiveIndustry } from "@/hooks/use-session";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  question?: string;
  historyId?: string;
  sql?: string;
  rows?: Array<Record<string, unknown>>;
  columns?: string[];
  narrative?: string;
  trustScore?: number;
  path?: string;
  clarification?: string;
  options?: string[];
  followups?: string[];
  citations?: Array<{ title: string; snippet: string; locator: string; untrusted?: boolean }>;
  cancelled?: boolean;
  error?: string;
}

export default function ChatPage() {
  const industry = useActiveIndustry();
  const [question, setQuestion] = useState("Show loss ratio by month");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [webRetrieval, setWebRetrieval] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const historyIdRef = useRef<string | null>(null);

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
                return { ...message, sql: String(data.sql ?? ""), path: String(data.path ?? "") };
              }
              if (currentEvent === "columns") {
                return { ...message, columns: (data.columns as string[]) ?? [] };
              }
              if (currentEvent === "rows") {
                return { ...message, rows: (data.rows as Array<Record<string, unknown>>) ?? [] };
              }
              if (currentEvent === "token") {
                return {
                  ...message,
                  narrative: `${message.narrative ?? ""}${String(data.token ?? "")}`,
                };
              }
              if (currentEvent === "trust") {
                return { ...message, trustScore: Number(data.score ?? 0) };
              }
              if (currentEvent === "clarification") {
                return {
                  ...message,
                  clarification: String(data.question ?? data.message ?? ""),
                  options: (data.options as string[]) ?? [],
                };
              }
              if (currentEvent === "followups") {
                return { ...message, followups: (data.items as string[]) ?? (data.followups as string[]) ?? [] };
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
              return message;
            }),
          );
        }
      }
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId ? { ...message, cancelled: true, narrative: "Cancelled." } : message,
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

  const lastUserQuestion =
    [...messages].reverse().find((message) => message.role === "user")?.question ?? "";

  return (
    <>
      <PageHeader
        title="AI Chat"
        description="Natural-language questions over governed SQL. Supports cancel, retry, follow-ups, and clarifications."
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="min-h-[420px]">
          <CardContent className="flex h-full flex-col gap-3 pt-4">
            <div className="flex-1 space-y-3 overflow-auto">
              {messages.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Try “loss ratio”, “claims by status”, “revenue by month”, “surprise me”, or a
                  what-if like “what if revenue increased 10%”.
                </p>
              ) : null}
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={
                    message.role === "user"
                      ? "rounded-md bg-primary/10 px-3 py-2 text-sm"
                      : "rounded-md border border-border px-3 py-2 text-sm"
                  }
                >
                  {message.question ? <p>{message.question}</p> : null}
                  {message.path ? (
                    <p className="mb-1 text-2xs uppercase tracking-wide text-muted-foreground">
                      {message.path}
                    </p>
                  ) : null}
                  {message.clarification ? (
                    <p className="text-amber-700 dark:text-amber-300">{message.clarification}</p>
                  ) : null}
                  {message.options?.length ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {message.options.map((option) => (
                        <Button
                          key={option}
                          type="button"
                          size="sm"
                          variant="secondary"
                          disabled={busy}
                          onClick={() => void runAsk(option)}
                        >
                          {option}
                        </Button>
                      ))}
                    </div>
                  ) : null}
                  {message.narrative ? <p className="whitespace-pre-wrap">{message.narrative}</p> : null}
                  {message.trustScore != null ? (
                    <p className="mt-1 text-2xs text-muted-foreground">
                      Trust score {message.trustScore}
                    </p>
                  ) : null}
                  {message.cancelled ? <p className="text-muted-foreground">Request cancelled.</p> : null}
                  {message.error ? <p className="text-danger">{message.error}</p> : null}
                  {message.sql ? (
                    <pre className="mt-2 overflow-auto rounded bg-muted/50 p-2 font-mono text-2xs">
                      {message.sql}
                    </pre>
                  ) : null}
                  {message.citations?.length ? (
                    <ul className="mt-2 space-y-1 text-2xs text-muted-foreground">
                      {message.citations.map((citation, index) => (
                        <li key={`${citation.locator}-${index}`}>
                          [{citation.locator}] {citation.title}
                          {citation.untrusted ? " (untrusted web)" : ""}: {citation.snippet}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {message.rows && message.columns ? (
                    <div className="mt-2 overflow-auto">
                      <table className="min-w-full text-left text-2xs">
                        <thead>
                          <tr>
                            {message.columns.map((column) => (
                              <th key={column} className="px-2 py-1 text-muted-foreground">
                                {column}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {message.rows.slice(0, 8).map((row, index) => (
                            <tr key={index} className="border-t border-border/60">
                              {message.columns?.map((column) => (
                                <td key={column} className="px-2 py-1 font-mono">
                                  {String(row[column] ?? "—")}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                  {message.followups?.length ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {message.followups.map((item) => (
                        <Button
                          key={item}
                          type="button"
                          size="sm"
                          variant="secondary"
                          disabled={busy}
                          onClick={() => void runAsk(item)}
                        >
                          {item}
                        </Button>
                      ))}
                    </div>
                  ) : null}
                  {message.role === "assistant" && message.question == null && lastUserQuestion ? (
                    <div className="mt-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => void runAsk(lastUserQuestion)}
                      >
                        Retry
                      </Button>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
            <form className="flex flex-col gap-2" onSubmit={onSubmit}>
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
                  className="h-10 flex-1 rounded-md border border-border bg-background px-3 text-sm"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="Ask a governed analytics question"
                />
                {busy ? (
                  <Button type="button" variant="secondary" onClick={() => void cancelInFlight()}>
                    Cancel
                  </Button>
                ) : (
                  <Button type="submit">Ask</Button>
                )}
              </div>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-2 pt-4">
            <CardTitle className="text-sm">SQL drawer</CardTitle>
            <CardDescription>
              Generated SQL is validated by read-only guardrails before execution. Numbers always
              come from PostgreSQL.
            </CardDescription>
            <p className="text-xs text-muted-foreground">Industry: {industry}</p>
            {conversationId ? (
              <p className="text-2xs text-muted-foreground">Conversation {conversationId}</p>
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
