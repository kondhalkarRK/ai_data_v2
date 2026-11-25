"use client";

import { createContext, createElement, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";

import type { ActionKey } from "@/components/chat/action-toolbar";
import { applyChatSseEvent } from "@/components/chat/sse";
import type { ChatMessage } from "@/components/chat/types";
import { myUsageKey, quotaMessage } from "@/hooks/use-my-usage";
import { useActiveIndustry, useSession } from "@/hooks/use-session";
import { API_BASE_URL, ApiError, apiClient } from "@/lib/api-client";

/**
 * Shared Chat flow for Classic and New. The existing ask-sync endpoint and SSE event
 * contract keep routing, scope, SQL, RBAC, quotas and memory in the same backend.
 */
export function useChatAsk() {
  const industry = useActiveIndustry();
  const { data: user } = useSession();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [useDocuments, setUseDocuments] = useState(false);
  const [webRetrieval, setWebRetrieval] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [restoring, setRestoring] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const historyIdRef = useRef<string | null>(null);
  const bootstrapped = useRef(false);
  // Only a conversation selection is stored here; authentication stays in HttpOnly cookies.
  // Keep this legacy key stable across display-name changes to preserve selections.
  const storageKey = `soci-chat:${user?.id ?? "anonymous"}:${industry}`;
  const question = drafts[conversationId ?? "new"] ?? "";
  const setQuestion = (text: string) => setDrafts(previous => ({ ...previous, [conversationId ?? "new"]: text }));

  const openConversation = useCallback(async (id: string) => {
    if (busy) return;
    setRestoring(true);
    setHistoryError(null);
    try {
      const saved = await apiClient.get<{
        id: string; hasMore: boolean;
        turns: Array<{ responseId: string; question: string; canRate: boolean; rating: ChatMessage["rating"]; events: Array<{ event: string; data: Record<string, unknown> }> }>;
      }>(`/api/v1/chat/conversations/${id}`, { industry });
      const restored: ChatMessage[] = [];
      for (const turn of saved.turns) {
        restored.push({ id: `question:${turn.responseId}`, role: "user", question: turn.question });
        let answer: ChatMessage = { id: turn.responseId, historyId: turn.responseId, role: "assistant", narrative: "", complete: true, rating: turn.rating, ratingDisabled: !turn.canRate };
        for (const frame of turn.events) answer = applyChatSseEvent(answer, frame.event, frame.data);
        restored.push(answer);
      }
      setMessages(restored);
      setConversationId(saved.id);
      try { window.sessionStorage.setItem(storageKey, saved.id); } catch { /* Storage optional. */ }
      if (saved.hasMore) setHistoryError("Showing the most recent 200 responses in this conversation.");
    } catch {
      setHistoryError("Could not open this conversation. Retry from Chat history.");
    } finally { setRestoring(false); }
  }, [busy, industry, storageKey]);

  useEffect(() => {
    let active: string | null = null;
    try { active = window.sessionStorage.getItem(storageKey); } catch { /* Storage optional. */ }
    if (active) void openConversation(active);
    else setRestoring(false);
    return () => { abortRef.current?.abort(); };
    // The provider remounts when the authenticated identity or access scope changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  const newConversation = () => {
    if (busy || restoring) return;
    setMessages([]);
    setConversationId(null);
    setHistoryError(null);
    try { window.sessionStorage.removeItem(storageKey); } catch { /* Storage optional. */ }
  };

  const patchAssistant = useCallback(
    (assistantId: string, update: (message: ChatMessage) => ChatMessage) =>
      setMessages((prev) => prev.map((m) => (m.id === assistantId ? update(m) : m))),
    [],
  );

  const runAsk = useCallback(
    async (text: string) => {
      const question = text.trim();
      if (!question || busy || restoring || abortRef.current) return;
      setQuestion("");
      const assistantId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "user", question, documentsEnabled: useDocuments },
        { id: assistantId, role: "assistant", narrative: "" },
      ]);
      setBusy(true);
      const controller = new AbortController();
      abortRef.current = controller;
      historyIdRef.current = null;
      try {
        const sync = await apiClient.post<{
          events: Array<{ event: string; data: Record<string, unknown> }>;
        }>("/api/v1/chat/ask-sync", { question, conversationId, webRetrieval, useDocuments }, { industry, signal: controller.signal });
        for (const frame of sync.events ?? []) {
          const data = frame.data ?? {};
          if (frame.event === "stage" && data.historyId) historyIdRef.current = String(data.historyId);
          if (frame.event === "done" && data.conversationId) {
            const nextId = String(data.conversationId);
            if (!conversationId) setDrafts(previous => ({ ...previous, [nextId]: previous.new ?? "", new: "" }));
            setConversationId(nextId);
            try { window.sessionStorage.setItem(storageKey, String(data.conversationId)); } catch { /* Storage optional. */ }
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
        void queryClient.invalidateQueries({ queryKey: ["chat-conversations"] });
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- setQuestion only clears the current draft.
    [busy, restoring, conversationId, industry, patchAssistant, queryClient, useDocuments, webRetrieval, storageKey],
  );

  useEffect(() => {
    const seeded = searchParams.get("q");
    if (seeded && !restoring && !bootstrapped.current) {
      bootstrapped.current = true;
      void runAsk(seeded);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot deep link
  }, [searchParams, restoring]);

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
        downloadText(`Scio-${message.id}.csv`, `${columns.join(",")}\n${body}`);
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

  return { user, useDocuments, setUseDocuments, webRetrieval, setWebRetrieval, industry, messages, busy, restoring, historyError, question, setQuestion, conversationId, toast, runAsk, cancelInFlight, handleAction, openConversation, newConversation };
}

const ChatContext = createContext<ReturnType<typeof useChatAsk> | null>(null);

function ChatRuntime({ children }: { children?: ReactNode }) {
  return createElement(ChatContext.Provider, { value: useChatAsk() }, children);
}

/** One live controller survives Classic/New switches; account and access changes reset it. */
export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const { data: user } = useSession();
  const industry = useActiveIndustry();
  const identity = `${user?.id}:${user?.role}:${industry}:${JSON.stringify(user?.regionAccess)}`;
  return createElement(ChatRuntime, { key: identity }, children);
}

export function useChatSession() {
  const session = useContext(ChatContext);
  if (!session) throw new Error("Chat requires ChatSessionProvider");
  return session;
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
