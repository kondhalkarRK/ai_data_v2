import { describe, expect, it } from "vitest";

import type { ChatMessage, ResultProfile } from "@/components/chat/types";
import {
  analysisTab,
  assistantView,
  CHAT_MODE_STORAGE_KEY,
  detectAnalysisRequest,
  readStoredChatMode,
} from "@/lib/chat-new-ui";

const profile = (over: Partial<ResultProfile> = {}): ResultProfile => ({
  shape: "ranking",
  rowCount: 3,
  labelColumns: ["model"],
  measures: [{ column: "units", label: "units", kind: "number" }],
  preview: [],
  previewTruncated: false,
  chartSuitable: true,
  mayBeTruncated: false,
  ...over,
});

function dataMessage(over: Partial<ChatMessage> = {}, rowCount = 3, p = profile()): ChatMessage {
  return {
    id: "a",
    role: "assistant",
    sql: "SELECT 1",
    columns: ["model", "units"],
    rows: Array.from({ length: rowCount }, (_, i) => ({ model: `m${i}`, units: i })),
    meta: {
      rowCount,
      validationStatus: "passed",
      resultProfile: p,
    } as ChatMessage["meta"],
    ...over,
  };
}

describe("detectAnalysisRequest", () => {
  it.each([
    ["Show revenue by region as a chart", "chart"],
    ["plot units sold by month", "chart"],
    ["give me a table of claims", "table"],
    ["show the SQL for that", "sql"],
    ["detailed analysis of revenue", "narration"],
  ])("%s -> %s", (question, tab) => {
    expect(detectAnalysisRequest(question)).toBe(tab);
  });

  it.each(["Top 3 models by units sold", "Revenue by region", "What about South?", "Hey there"])(
    "plain question %s gets the compact answer",
    (question) => {
      expect(detectAnalysisRequest(question)).toBeNull();
    },
  );
});

describe("assistantView", () => {
  it("successful rows -> compact data answer", () => {
    expect(assistantView(dataMessage())).toBe("data");
  });
  it("zero rows, execution errors and DQ failures use the existing card", () => {
    expect(assistantView(dataMessage({}, 0))).toBe("card");
    const failed = dataMessage();
    failed.meta = { ...failed.meta!, executionError: "boom" };
    expect(assistantView(failed)).toBe("card");
    const dq = dataMessage();
    dq.meta = { ...dq.meta!, dqFailed: true };
    expect(assistantView(dq)).toBe("card");
  });
  it("no SQL reply is plain text; knowledge routes and failures keep the card", () => {
    const hello: ChatMessage = {
      id: "h",
      role: "assistant",
      narrative: "Hi!",
      meta: { rowCount: 0, validationStatus: "skipped" } as ChatMessage["meta"],
    };
    expect(assistantView(hello)).toBe("text");
    expect(assistantView({ ...hello, route: "knowledge" })).toBe("card");
    expect(assistantView({ ...hello, error: "x" })).toBe("card");
    expect(assistantView({ ...hello, cancelled: true })).toBe("card");
    expect(assistantView({ ...hello, clarification: "Which?" })).toBe("card");
  });
  it("still streaming -> pending", () => {
    expect(assistantView({ id: "p", role: "assistant", narrative: "" })).toBe("pending");
  });
});

describe("analysisTab", () => {
  it("chart only when the result suits it", () => {
    expect(analysisTab(dataMessage(), null)).toBe("chart");
    const single = dataMessage({}, 1, profile({ shape: "single_value", chartSuitable: false }));
    expect(analysisTab(single, null)).toBe("table");
    expect(analysisTab(single, "chart")).toBe("table");
  });
  it("respects explicit table/sql/narration requests", () => {
    expect(analysisTab(dataMessage(), "sql")).toBe("sql");
    expect(analysisTab(dataMessage(), "table")).toBe("table");
    expect(analysisTab(dataMessage(), "narration")).toBe("narration");
  });
});

describe("readStoredChatMode", () => {
  it("defaults to classic and reads a stored new", () => {
    expect(readStoredChatMode(null)).toBe("classic");
    expect(readStoredChatMode({ getItem: () => null })).toBe("classic");
    expect(readStoredChatMode({ getItem: (k) => (k === CHAT_MODE_STORAGE_KEY ? "new" : null) })).toBe(
      "new",
    );
    expect(
      readStoredChatMode({
        getItem: () => {
          throw new Error("blocked");
        },
      }),
    ).toBe("classic");
  });
});
