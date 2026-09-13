"use client";

import * as React from "react";

import { ResponseCard } from "@/components/chat/response-card";
import { applyChatSseEvent, consumeSseBuffer } from "@/components/chat/sse";
import type { ChatMessage } from "@/components/chat/types";
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
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { frames, rest } = consumeSseBuffer(buffer);
        buffer = rest;
        for (const frame of frames) {
          const eventName = frame.event;
          const data = frame.data;
          if (eventName === "done" && data.conversationId) {
            setConversationId(String(data.conversationId));
          }
          setMessage((prev) =>
            !prev || prev.id !== assistantId
              ? prev
              : applyChatSseEvent(prev, eventName, data),
          );
        }
      }
      if (buffer.trim()) {
        const { frames } = consumeSseBuffer(`${buffer}\n\n`);
        for (const frame of frames) {
          const eventName = frame.event;
          const data = frame.data;
          if (eventName === "done" && data.conversationId) {
            setConversationId(String(data.conversationId));
          }
          setMessage((prev) =>
            !prev || prev.id !== assistantId
              ? prev
              : applyChatSseEvent(prev, eventName, data),
          );
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
