"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";

import type { ActionKey } from "@/components/chat/action-toolbar";
import { applyChatSseEvent } from "@/components/chat/sse";
import type { ChatMessage } from "@/components/chat/types";
import { myUsageKey, quotaMessage } from "@/hooks/use-my-usage";
import { useActiveIndustry } from "@/hooks/use-session";
import { API_BASE_URL, ApiError, apiClient } from "@/lib/api-client";

/**
 * Ask flow for the New Chat view. It calls the same `/api/v1/chat/ask-sync` endpoint and folds
 * the same SSE events with `applyChatSseEvent` as the Classic workspace, so the backend
 * (routing, scope, NLQ, SQL, RBAC, quotas, memory) is shared. Classic keeps its own copy of
 * this flow and is intentionally untouched.
 */
export function useChatAsk() {
  const industry = useActiveIndustry();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const historyIdRef = useRef<string | null>(null);
  const bootstrapped = useRef(false);

  const patchAssistant = useCallback(
    (assistantId: string, update: (message: ChatMessage) => ChatMessage) =>
      setMessages((prev) => prev.map((m) => (m.id === assistantId ? update(m) : m))),
    [],
  );

  const runAsk = useCallback(
    async (text: string) => {
      const question = text.trim();
      if (!question || busy) return;
      const assistantId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "user", question },
        { id: assistantId, role: "assistant", narrative: "" },
      ]);
      setBusy(true);
      const controller = new AbortController();
      abortRef.current = controller;
      historyIdRef.current = null;
      try {
        const sync = await apiClient.post<{
          events: Array<{ event: string; data: Record<string, unknown> }>;
        }>("/api/v1/chat/ask-sync", { question, conversationId, webRetrieval: false }, { industry });
        for (const frame of sync.events ?? []) {
          const data = frame.data ?? {};
          if (frame.event === "stage" && data.historyId) historyIdRef.current = String(data.historyId);
          if (frame.event === "done" && data.conversationId) {
            setConversationId(String(data.conversationId));
          }
          patchAssistant(assistantId, (m) => applyChatSseEvent(m, frame.event, data));
        }
      } catch (error) {
        if ((error as Error).name === "AbortError") {
          patchAssistant(assistantId, (m) => ({ ...m, cancelled: true, narrative: "Cancelled." }));
        } else if (error instanceof ApiError && error.code === "quota_exceeded") {
          patchAssistant(assistantId, (m) => ({ ...m, quotaNotice: quotaMessage(error.details) }));
        } else {
          patchAssistant(assistantId, (m) => ({
            ...m,
            error: "The answer service did not respond in time.",
          }));
        }
      } finally {
        setBusy(false);
        abortRef.current = null;
        void queryClient.invalidateQueries({ queryKey: myUsageKey });
      }
    },
    [busy, conversationId, industry, patchAssistant, queryClient],
  );

  useEffect(() => {
    const seeded = searchParams.get("q");
    if (seeded && !bootstrapped.current) {
      bootstrapped.current = true;
      void runAsk(seeded);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot deep link
  }, [searchParams]);

  const cancelInFlight = useCallback(async () => {
    const historyId = historyIdRef.current;
    abortRef.current?.abort();
    if (!historyId) return;
    try {
      await fetch(`${API_BASE_URL}/api/v1/chat/cancel/${historyId}`, {
        method: "POST",
        credentials: "include",
        headers: { "x-industry": industry, "x-csrf-token": readCookie("nql_csrf") ?? "" },
      });
    } catch {
      // Best-effort cancel record.
    }
  }, [industry]);

  const flash = useCallback((text: string) => {
    setToast(text);
    window.setTimeout(() => setToast(null), 1800);
  }, []);

  const handleAction = useCallback(
    async (key: ActionKey, message: ChatMessage) => {
      if (key === "copy") {
        await navigator.clipboard.writeText(message.sql || message.narrative || "");
        flash("Copied to clipboard");
      } else if (key === "export") {
        if (!message.rows?.length || !message.columns?.length) return flash("Nothing to export yet");
        const columns = message.columns;
        const body = message.rows
          .map((row) => columns.map((c) => csvEscape(String(row[c] ?? ""))).join(","))
          .join("\n");
        downloadText(`ask-db-${message.id}.csv`, `${columns.join(",")}\n${body}`);
        flash("CSV downloaded");
      } else if (key === "save") {
        const title = (message.narrative || "Saved insight").slice(0, 80);
        const lastUser = [...messages].reverse().find((m) => m.role === "user")?.question ?? title;
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
    },
    [flash, messages],
  );

  return { industry, messages, busy, conversationId, toast, runAsk, cancelInFlight, handleAction };
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function csvEscape(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

function downloadText(filename: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
