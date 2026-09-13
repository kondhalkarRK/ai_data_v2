/** Apply one chat SSE event onto an assistant ChatMessage (pure). */

import type {
  ChatMessage,
  ChartPayload,
  FailurePayload,
  ProgressState,
  ResponseMeta,
  SqlDiffLine,
} from "@/components/chat/types";

export function applyChatSseEvent(
  message: ChatMessage,
  eventName: string,
  data: Record<string, unknown>,
): ChatMessage {
  switch (eventName) {
    case "progress":
      return { ...message, progress: data as unknown as ProgressState };
    case "stage":
      return {
        ...message,
        ...(data.historyId ? { historyId: String(data.historyId) } : {}),
        path: String(data.stage ?? message.path ?? ""),
      };
    case "sql":
      return {
        ...message,
        sql: String(data.sql ?? ""),
        path: String(data.path ?? message.path ?? ""),
        priorSql: data.priorSql ? String(data.priorSql) : undefined,
        sqlDiff: (data.diff as SqlDiffLine[] | null | undefined) ?? null,
      };
    case "columns":
      return { ...message, columns: (data.columns as string[]) ?? [] };
    case "rows":
      return { ...message, rows: (data.rows as Array<Record<string, unknown>>) ?? [] };
    case "chart":
      return { ...message, chart: data as unknown as ChartPayload };
    case "meta":
      return { ...message, meta: data as unknown as ResponseMeta, progress: null };
    case "token":
      return {
        ...message,
        narrative: `${message.narrative ?? ""}${String(data.token ?? "")}`,
      };
    case "clarification":
      return {
        ...message,
        clarification: String(data.question ?? data.message ?? ""),
        options: (data.options as string[]) ?? [],
        progress: null,
      };
    case "followups":
      return {
        ...message,
        followups: (data.items as string[]) ?? (data.followups as string[]) ?? [],
      };
    case "citation": {
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
    case "cancelled":
      return { ...message, cancelled: true, narrative: "Cancelled.", progress: null };
    case "error": {
      const failure: FailurePayload = {
        category: data.category ? String(data.category) : undefined,
        title: data.title ? String(data.title) : undefined,
        reason: data.reason ? String(data.reason) : undefined,
        retryable: data.retryable !== false,
        message: data.message ? String(data.message) : undefined,
        sql: data.sql ? String(data.sql) : undefined,
      };
      return {
        ...message,
        error: String(data.message ?? data.reason ?? "Chat failed"),
        failure,
        progress: null,
        sql: failure.sql || message.sql,
      };
    }
    case "done":
      return {
        ...message,
        latencyMs: Number(data.latencyMs ?? message.latencyMs ?? 0),
        historyId: String(data.historyId ?? message.historyId ?? ""),
        progress: null,
      };
    default:
      return message;
  }
}

/** Parse SSE frames from a buffer chunk; returns leftover incomplete frame. */
export function consumeSseBuffer(buffer: string): {
  frames: Array<{ event: string; data: Record<string, unknown> }>;
  rest: string;
} {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  const frames: Array<{ event: string; data: Record<string, unknown> }> = [];
  for (const part of parts) {
    if (!part.trim() || part.trim().startsWith(":")) continue;
    const lines = part.split(/\r?\n/);
    let eventName = "message";
    let dataLine = "";
    for (const line of lines) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      if (line.startsWith("data:")) dataLine += line.slice(5).trim();
    }
    if (!dataLine) continue;
    try {
      frames.push({
        event: eventName,
        data: JSON.parse(dataLine) as Record<string, unknown>,
      });
    } catch {
      // Skip malformed frames rather than aborting the whole stream.
    }
  }
  return { frames, rest };
}
