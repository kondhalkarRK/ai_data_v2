/**
 * New Chat experience: feature flag, stored mode and presentation decisions.
 *
 * Everything here is generic. It looks at the API's `resultProfile` (derived from the executed
 * rows) and at presentation words in the question ("chart", "table", "sql"), never at business
 * terms, so it works for any metric or dimension in the semantic model.
 */

import type { ChatMessage, ResponseTab } from "@/components/chat/types";

/** Set `ASK_ME_NEW_CHAT_UI_ENABLED=true` (mapped to NEXT_PUBLIC_ in next.config.ts). */
export const NEW_CHAT_UI_ENABLED =
  (process.env.NEXT_PUBLIC_ASK_ME_NEW_CHAT_UI_ENABLED ?? "false").toLowerCase() === "true";

export type ChatMode = "classic" | "new";
export const CHAT_MODE_STORAGE_KEY = "askMeChatMode";

export function readStoredChatMode(storage: Pick<Storage, "getItem"> | null): ChatMode {
  try {
    return storage?.getItem(CHAT_MODE_STORAGE_KEY) === "new" ? "new" : "classic";
  } catch {
    return "classic";
  }
}

const SQL_WORDS = /\b(sql|the query|generated query|query used)\b/i;
const CHART_WORDS = /\b(charts?|graphs?|plots?|visuali[sz]e|visuali[sz]ation|bar chart|line chart|pie chart)\b/i;
const TABLE_WORDS = /\b(tables?|tabular|spreadsheet|all rows|full list)\b/i;
const DETAIL_WORDS =
  /\b(detailed analysis|in detail|full analysis|deep dive|show (?:me )?(?:the )?(?:analysis|details)|view analysis)\b/i;

/**
 * Presentation intent in the question. `null` means the user asked a plain question and gets
 * the compact answer; otherwise the analysis opens straight away on the requested tab.
 */
export function detectAnalysisRequest(question: string): ResponseTab | null {
  if (SQL_WORDS.test(question)) return "sql";
  if (CHART_WORDS.test(question)) return "chart";
  if (TABLE_WORDS.test(question)) return "table";
  if (DETAIL_WORDS.test(question)) return "narration";
  return null;
}

export type AssistantView = "pending" | "data" | "text" | "card";

/**
 * Which presentation an assistant message gets:
 * - `data`: executed query with rows -> compact answer + View Analysis
 * - `text`: conversational reply without SQL (greeting, app help, scope decline)
 * - `card`: everything the existing ResponseCard already handles (failures, clarification,
 *   zero rows, quota, cancelled, documents)
 * - `pending`: still streaming; the card shows progress
 */
export function assistantView(message: ChatMessage): AssistantView {
  if (message.cancelled || message.quotaNotice || message.failure || message.error) return "card";
  if (message.clarification && !message.sql) return "card";
  const meta = message.meta;
  if (!meta) return "pending";
  const route = message.route ?? meta.route;
  if (route === "knowledge" || route === "hybrid") return "card";
  if (!message.sql) return "text";
  const usable =
    meta.rowCount > 0 &&
    !meta.executionError &&
    meta.validationStatus !== "failed" &&
    !meta.dqFailed &&
    Boolean(message.rows?.length);
  return usable ? "data" : "card";
}

/** Tab to open for a data answer: the user's explicit ask, else what suits the result. */
export function analysisTab(
  message: ChatMessage,
  requested: ResponseTab | null,
): ResponseTab {
  const chartSuitable = Boolean(message.meta?.resultProfile?.chartSuitable);
  if (requested === "chart") return chartSuitable ? "chart" : "table";
  if (requested) return requested;
  return chartSuitable ? "chart" : "table";
}
