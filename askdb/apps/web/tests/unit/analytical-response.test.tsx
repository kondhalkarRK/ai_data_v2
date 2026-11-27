import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { AnalyticalAnswer, AnalyticalDetails, AnalyticalProgressView } from "@/components/chat/analytical-answer";
import { applyChatSseEvent, consumeSseBuffer } from "@/components/chat/sse";
import { analyticalPresentation, formatAnalyticalCell } from "@/lib/analytical-response";
import { assistantView } from "@/lib/chat-new-ui";
import { analyticalMessage } from "../fixtures/analytical";
import type { ChatMessage } from "@/components/chat/types";

vi.mock("@/components/chat/result-chart", () => ({ ResultChart: () => <div>Verified chart</div> }));

it("uses one multi-step renderer for the actual result, including zero rows", () => {
  const message = analyticalMessage();
  expect(assistantView(message)).toBe("analysis");
  render(<AnalyticalAnswer message={message} />);
  expect(screen.getByRole("region", { name: "Multi-step analysis" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Step 2 Highest revenue region" })).toBeInTheDocument();
  const models = screen.getByRole("region", { name: "Revenue by model in selected region" });
  expect(within(models).getByRole("table", { name: "Revenue by model in selected region data" })).toHaveTextContent("Alpha");
  expect(within(models).getAllByText("₹2.00 Cr")[0]).toBeVisible();
});

it("never renders unverified attribution as a verified main table", () => {
  const message = analyticalMessage(true);
  const { unmount } = render(<AnalyticalAnswer message={message} />);
  expect(screen.getByText(/Partial answer/)).toBeVisible();
  expect(screen.queryByRole("table", { name: "Revenue by model in selected region data" })).not.toBeInTheDocument();
  unmount();
  render(<AnalyticalDetails message={message} />);
  expect(screen.getByRole("table", { name: "Revenue by model in selected region unverified data" })).toBeInTheDocument();
  expect(screen.getByText("revenue: Not verified")).toBeInTheDocument();
});

it("offers full precision by keyboard without changing stored raw values", async () => {
  const user = userEvent.setup();
  const message = analyticalMessage();
  render(<AnalyticalAnswer message={message} />);
  await user.click(screen.getByText("View exact values — Revenue by model in selected region"));
  expect(screen.getByRole("table", { name: "Revenue by model in selected region exact data" })).toHaveTextContent("20000000.01");
  expect(message.meta!.analyticalExecution!.steps[2]!.rows[0]!.revenue).toBe("20000000.01");
});

it("preserves zero, missing values, INR units and percentages", () => {
  const currency = { key: "amount", label: "Amount", kind: "currency" } as const;
  expect(formatAnalyticalCell(0, currency)).toBe("₹0");
  expect(formatAnalyticalCell(null, currency)).toBe("Unavailable");
  expect(formatAnalyticalCell(-10000000, currency)).toBe("-₹1.00 Cr");
  expect(formatAnalyticalCell(100000, currency)).toBe("₹1.00 Lakh");
  expect(formatAnalyticalCell(12.345, { ...currency, kind: "percent" })).toBe("12.3%");
  expect(formatAnalyticalCell(true, currency)).toBe("Unavailable");
});

it("does not show stale results after cancellation, denial or failure", () => {
  const message = analyticalMessage();
  expect(assistantView({ ...message, cancelled: true })).toBe("card");
  expect(analyticalPresentation({ ...message, meta: { ...message.meta!, responseKind: "denied" } })).toBeNull();
  expect(analyticalPresentation({ ...message, error: "Stopped" })).toBeNull();
});

it("replays Batch 2 snapshots locally without rebasing dates or making requests", () => {
  const message = analyticalMessage();
  delete message.meta!.analyticalPresentation;
  const view = analyticalPresentation(message)!;
  expect(view.legacy).toBe(true);
  expect(view.steps).toHaveLength(3);
  expect(view.steps[2]!.columns[1]!.kind).toBe("currency");
  expect(view.steps[2]!.comparisonPeriods).toEqual([]);
});

it("keeps streaming and sync/replay state equal, with transient progress cleared", () => {
  const meta = analyticalMessage().meta!;
  const events = [
    { event: "analysis_progress", data: { version: 1, planId: "p", phase: "running", total: 3, completed: 0, message: "Running 3 linked steps", steps: [] } },
    { event: "meta", data: { ...meta } }, { event: "done", data: { historyId: "run" } },
  ];
  const start: ChatMessage = { id: "a", role: "assistant" };
  const sync = events.reduce((message, event) => applyChatSseEvent(message, event.event, event.data), start);
  const wire = events.map(event => `event: ${event.event}\ndata: ${JSON.stringify(event.data)}\n\n`).join("");
  const stream = consumeSseBuffer(wire).frames.reduce((message, event) => applyChatSseEvent(message, event.event, event.data), start);
  expect(stream).toEqual(sync);
  expect(stream.analysisProgress).toBeNull();
  expect(assistantView(stream)).toBe("analysis");
  const pending = applyChatSseEvent(start, "analysis_progress", events[0]!.data);
  expect(applyChatSseEvent(pending, "cancelled", {}).analysisProgress).toBeNull();
});

it("running progress never claims that a database step has completed", () => {
  render(<AnalyticalProgressView progress={{ version: 1, planId: "p", phase: "running", completed: 0,
    total: 2, message: "Running 2 linked steps", steps: [{ id: "one", label: "Select period", status: "pending" }, { id: "two", label: "Compare", status: "pending" }] }} />);
  expect(screen.getAllByText("Waiting for results")).toHaveLength(2);
  expect(screen.queryByText("Checked")).not.toBeInTheDocument();
});
