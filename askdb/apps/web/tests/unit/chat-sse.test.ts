import { describe, expect, it } from "vitest";

import { applyChatSseEvent, consumeSseBuffer } from "@/components/chat/sse";
import type { ChatMessage } from "@/components/chat/types";

describe("chat SSE batching", () => {
  it("applies each event type even when frames share one flush", () => {
    const raw =
      'event: progress\ndata: {"steps":[{"id":"understanding","label":"Understanding Question"}],"current":"understanding","currentLabel":"Understanding Question","completed":[]}\n\n' +
      'event: sql\ndata: {"sql":"SELECT 1","path":"template"}\n\n' +
      'event: rows\ndata: {"rows":[{"n":1}],"rowCount":1}\n\n' +
      'event: meta\ndata: {"groundedOn":["Semantic Layer"],"ambiguityFlag":false,"validationStatus":"passed","rowCount":1,"executionTimeMs":12,"sourceDatabase":"db","dataAsOf":null,"timings":{"llmGenerationMs":0,"semanticLookupMs":1,"sqlValidationMs":1,"executionMs":5,"renderMs":1},"queryMeta":{"tablesUsed":[],"metricsUsed":[],"dimensionsUsed":[],"joinPath":[],"filtersApplied":[],"dateRange":null},"insights":{"executive":"ok","analyst":"ok"},"anomalies":[],"alternateInterpretations":[]}\n\n' +
      'event: done\ndata: {"historyId":"h1","latencyMs":40,"conversationId":"c1"}\n\n';

    const { frames } = consumeSseBuffer(raw);
    expect(frames.map((f) => f.event)).toEqual([
      "progress",
      "sql",
      "rows",
      "meta",
      "done",
    ]);

    let message: ChatMessage = { id: "a1", role: "assistant", narrative: "" };
    for (const frame of frames) {
      // Simulate React batching: event name must be captured per frame.
      const eventName = frame.event;
      message = applyChatSseEvent(message, eventName, frame.data);
    }

    expect(message.sql).toContain("SELECT 1");
    expect(message.rows).toEqual([{ n: 1 }]);
    expect(message.meta?.insights.executive).toBe("ok");
    expect(message.historyId).toBe("h1");
    expect(message.latencyMs).toBe(40);
    expect(message.progress).toBeNull();
  });
});
