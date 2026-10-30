/**
 * New Chat experience: feature flag, stored mode and presentation decisions.
 *
 * Everything here is generic. It looks at the API's `resultProfile` (derived from the executed
 * rows) and at presentation words in the question ("chart", "table", "sql"), never at business
 * terms, so it works for any metric or dimension in the semantic model.
 */

import type { ChatMessage, ResponseTab, ResultProfile } from "@/components/chat/types";
import type { ChartKind } from "@/components/chat/result-chart";

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

/**
 * How to embed visuals under a successful data answer. Driven only by `resultProfile`
 * (and row count), never by business question text.
 */
export type InlineLayout =
  | "kpi"
  | "kpi_group"
  | "trend_chart"
  | "comparison_chart"
  | "ranked_list"
  | "table_preview"
  | "summary_only";

export type InlinePresentation = {
  layout: InlineLayout;
  /** Embed ResultChart when true (same rows as View Analysis). */
  showChart: boolean;
  chartKind: ChartKind;
  /** Side-by-side chart + list/KPI on wide screens when both are useful. */
  sideBySide: boolean;
};

const INLINE_CHART_ROW_CAP = 48;

export function inlinePresentation(profile: ResultProfile | null | undefined): InlinePresentation {
  if (!profile || profile.shape === "empty" || profile.rowCount === 0) {
    return { layout: "summary_only", showChart: false, chartKind: "bar", sideBySide: false };
  }

  const measures = profile.measures.length;
  const large = profile.rowCount > 12 || profile.mayBeTruncated;

  if (profile.shape === "single_value") {
    return {
      layout: measures > 1 ? "kpi_group" : "kpi",
      showChart: false,
      chartKind: "bar",
      sideBySide: false,
    };
  }

  if (profile.shape === "time_series" && profile.chartSuitable) {
    return {
      layout: "trend_chart",
      showChart: true,
      chartKind: "line",
      sideBySide: false,
    };
  }

  if (profile.shape === "comparison" && profile.chartSuitable) {
    return {
      layout: "comparison_chart",
      showChart: !large || profile.rowCount <= INLINE_CHART_ROW_CAP,
      chartKind: "bar",
      sideBySide: !large && profile.rowCount <= 8,
    };
  }

  if (profile.shape === "ranking") {
    return {
      layout: "ranked_list",
      showChart: Boolean(profile.chartSuitable) && profile.rowCount <= 12,
      chartKind: "bar",
      sideBySide: Boolean(profile.chartSuitable) && profile.rowCount <= 8,
    };
  }

  if (profile.shape === "breakdown" && profile.chartSuitable) {
    const few = profile.rowCount <= 8;
    return {
      layout: few ? "comparison_chart" : large ? "table_preview" : "comparison_chart",
      showChart: profile.rowCount <= INLINE_CHART_ROW_CAP && !large,
      chartKind: few && profile.rowCount <= 6 ? "pie" : "bar",
      sideBySide: few,
    };
  }

  if (profile.shape === "table" || !profile.measures.length) {
    return { layout: "table_preview", showChart: false, chartKind: "bar", sideBySide: false };
  }

  return {
    layout: large ? "table_preview" : "ranked_list",
    showChart: false,
    chartKind: "bar",
    sideBySide: false,
  };
}
