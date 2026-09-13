"use client";

import * as React from "react";

import { ResponseCard } from "@/components/chat/response-card";
import type { ChatMessage, ChartPayload, ResponseMeta, SqlDiffLine } from "@/components/chat/types";
import { Button } from "@/components/ui/button";
import { useActiveIndustry } from "@/hooks/use-session";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function AskDashboardAi({
  suggestions,
}: {
  suggestions: Array<{ id: string; text: string; supported: boolean }>;
}) {
  const industry = useActiveIndustry();
  const [question, setQuestion] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [conversationId, setConversationId] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState<ChatMessage | null>(null);

  async function ask(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    const assistantId = crypto.randomUUID();
    setMessage({ id: assistantId, role: "assistant", narrative: "" });
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
        body: JSON.stringify({
          question: q,
          conversationId,
          webRetrieval: false,
        }),
      });
      if (!response.ok || !response.body) throw new Error(`Chat failed (${response.status})`);
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
          if (currentEvent === "done" && data.conversationId) {
            setConversationId(String(data.conversationId));
          }
          setMessage((prev) => {
            if (!prev || prev.id !== assistantId) return prev;
            if (currentEvent === "sql") {
              return {
                ...prev,
                sql: String(data.sql ?? ""),
                sqlDiff: (data.diff as SqlDiffLine[] | null | undefined) ?? null,
              };
            }
            if (currentEvent === "columns") {
              return { ...prev, columns: (data.columns as string[]) ?? [] };
            }
            if (currentEvent === "rows") {
              return { ...prev, rows: (data.rows as Array<Record<string, unknown>>) ?? [] };
            }
            if (currentEvent === "chart") {
              return { ...prev, chart: data as unknown as ChartPayload };
            }
            if (currentEvent === "meta") {
              return { ...prev, meta: data as unknown as ResponseMeta };
            }
            if (currentEvent === "token") {
              return { ...prev, narrative: `${prev.narrative ?? ""}${String(data.token ?? "")}` };
            }
            if (currentEvent === "followups") {
              return { ...prev, followups: (data.items as string[]) ?? [] };
            }
            if (currentEvent === "clarification") {
              return {
                ...prev,
                clarification: String(data.question ?? ""),
                options: (data.options as string[]) ?? [],
              };
            }
            if (currentEvent === "error") {
              return { ...prev, error: String(data.message ?? "Chat failed") };
            }
            if (currentEvent === "done") {
              return { ...prev, latencyMs: Number(data.latencyMs ?? 0) };
            }
            return prev;
          });
        }
      }
    } catch (error) {
      setMessage({
        id: assistantId,
        role: "assistant",
        error: error instanceof Error ? error.message : "Chat failed",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
      <h2 className="text-sm font-semibold tracking-tight">Ask AI about this dashboard</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Same governed NLQ experience as Chat — including trust badges, SQL, and execution timeline.
      </p>

      {suggestions.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {suggestions
            .filter((item) => item.supported)
            .map((item) => (
              <Button
                key={item.id}
                type="button"
                size="sm"
                variant="secondary"
                className="h-8 rounded-full text-xs"
                disabled={busy}
                onClick={() => void ask(item.text)}
              >
                {item.text}
              </Button>
            ))}
        </div>
      ) : null}

      <form
        className="mt-3 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void ask(question);
        }}
      >
        <input
          className="h-10 flex-1 rounded-xl border border-border bg-background px-3 text-sm outline-none ring-foreground/10 focus:ring-2"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask a domain-aware question…"
        />
        <Button type="submit" disabled={busy} className="rounded-xl">
          Ask
        </Button>
      </form>

      {message ? (
        <div className="mt-4">
          <ResponseCard
            message={message}
            busy={busy}
            onAsk={(text) => void ask(text)}
            onRetry={() => void ask(question)}
            onAction={(_key, _message) => {
              /* Embedded Ask AI: full action bar remains on main Chat. */
            }}
          />
        </div>
      ) : null}
    </div>
  );
}
