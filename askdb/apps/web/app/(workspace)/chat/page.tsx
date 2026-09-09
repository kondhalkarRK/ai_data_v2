"use client";

import { FormEvent, useState } from "react";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { useActiveIndustry } from "@/hooks/use-session";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  question?: string;
  sql?: string;
  rows?: Array<Record<string, unknown>>;
  columns?: string[];
  narrative?: string;
  trustScore?: number;
  error?: string;
}

export default function ChatPage() {
  const industry = useActiveIndustry();
  const [question, setQuestion] = useState("Show loss ratio by month");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || busy) return;
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      question: question.trim(),
    };
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [...prev, userMessage, { id: assistantId, role: "assistant", narrative: "" }]);
    setBusy(true);
    setQuestion("");

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/chat/ask`, {
        method: "POST",
        credentials: "include",
        headers: {
          "content-type": "application/json",
          "x-industry": industry,
          "x-csrf-token": readCookie("nql_csrf") ?? "",
        },
        body: JSON.stringify({ question: userMessage.question }),
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
          setMessages((prev) =>
            prev.map((message) => {
              if (message.id !== assistantId) return message;
              if (currentEvent === "sql") return { ...message, sql: String(data.sql ?? "") };
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
              if (currentEvent === "error") {
                return { ...message, error: String(data.message ?? "Chat failed") };
              }
              return message;
            }),
          );
        }
      }
    } catch (error) {
      setMessages((prev) =>
        prev.map((message) =>
          message.id === assistantId
            ? { ...message, error: error instanceof Error ? error.message : "Chat failed" }
            : message,
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="AI Chat"
        description="Natural-language questions over governed SQL. First SSE frame arrives before the LLM."
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="min-h-[420px]">
          <CardContent className="flex h-full flex-col gap-3 pt-4">
            <div className="flex-1 space-y-3 overflow-auto">
              {messages.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Try “loss ratio”, “claims by status”, “revenue by month”, or “top models”.
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
                  {message.narrative ? <p className="whitespace-pre-wrap">{message.narrative}</p> : null}
                  {message.trustScore != null ? (
                    <p className="mt-1 text-2xs text-muted-foreground">
                      Trust score {message.trustScore}
                    </p>
                  ) : null}
                  {message.error ? <p className="text-danger">{message.error}</p> : null}
                  {message.sql ? (
                    <pre className="mt-2 overflow-auto rounded bg-muted/50 p-2 font-mono text-2xs">
                      {message.sql}
                    </pre>
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
                </div>
              ))}
            </div>
            <form className="flex gap-2" onSubmit={onSubmit}>
              <input
                className="h-10 flex-1 rounded-md border border-border bg-background px-3 text-sm"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Ask a governed analytics question"
              />
              <Button type="submit" disabled={busy}>
                {busy ? "Running…" : "Ask"}
              </Button>
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
