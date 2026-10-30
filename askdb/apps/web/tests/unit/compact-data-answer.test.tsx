import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/chat/result-chart", () => ({
  ResultChart: () => <div data-testid="result-chart" />,
}));

import { CompactDataAnswer } from "@/components/chat/compact-data-answer";
import type { ChatMessage, ResultProfile } from "@/components/chat/types";

function message(profile: ResultProfile, rows: Array<Record<string, unknown>>): ChatMessage {
  return {
    id: "m1",
    role: "assistant",
    sql: "SELECT model, units FROM t",
    columns: Object.keys(rows[0] ?? {}),
    rows,
    followups: ["What about South?"],
    meta: {
      groundedOn: [],
      ambiguityFlag: false,
      validationStatus: "passed",
      rowCount: rows.length,
      executionTimeMs: 5,
      sourceDatabase: "db",
      dataAsOf: null,
      timings: {},
      queryMeta: { tablesUsed: [], metricsUsed: [], dimensionsUsed: [], joinPath: [], filtersApplied: [], dateRange: null },
      insights: {
        executive: "x",
        analyst: "y",
        narration: { summary: "Nexon leads with 9,100 units.", highlights: [], insight: null, focus: null },
      },
      anomalies: [],
      alternateInterpretations: [],
      resultProfile: profile,
    } as unknown as ChatMessage["meta"],
  };
}

const ranking: ResultProfile = {
  shape: "ranking",
  rowCount: 8,
  labelColumns: ["model"],
  measures: [
    { column: "units", label: "units sold", kind: "number" },
    { column: "revenue", label: "revenue", kind: "currency" },
  ],
  preview: [
    { label: "Nexon", values: [{ column: "units", text: "9,100" }, { column: "revenue", text: "₹91.0M" }] },
    { label: "Punch", values: [{ column: "units", text: "7,400" }, { column: "revenue", text: "₹52.0M" }] },
  ],
  previewTruncated: true,
  chartSuitable: true,
  mayBeTruncated: false,
};

const rankingRows = [
  { model: "Nexon", units: 9100, revenue: 91_000_000 },
  { model: "Punch", units: 7400, revenue: 52_000_000 },
];

const single: ResultProfile = {
  shape: "single_value",
  rowCount: 1,
  labelColumns: [],
  measures: [{ column: "revenue", label: "revenue", kind: "currency" }],
  preview: [{ label: null, values: [{ column: "revenue", text: "₹987.7M" }] }],
  previewTruncated: false,
  chartSuitable: false,
  mayBeTruncated: false,
};

function renderAnswer(msg: ChatMessage, requestedTab: Parameters<typeof CompactDataAnswer>[0]["requestedTab"] = null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CompactDataAnswer message={msg} requestedTab={requestedTab} onAsk={vi.fn()} onAction={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("CompactDataAnswer", () => {
  it("shows the sentence and only values from the profile, with analysis hidden", () => {
    renderAnswer(message(ranking, rankingRows));
    expect(screen.getByText("Nexon leads with 9,100 units.")).toBeInTheDocument();
    const preview = within(screen.getByTestId("result-preview"));
    expect(preview.getByText("Nexon")).toBeInTheDocument();
    expect(preview.getByText("9,100")).toBeInTheDocument();
    expect(preview.getByText(/₹52\.0M/)).toBeInTheDocument();
    expect(preview.getByText(/Showing 2 of 8/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /view analysis/i })).toBeInTheDocument();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.queryByTestId("result-chart")).not.toBeInTheDocument();
  });

  it("View Analysis reveals the existing tabs over the same rows, opening on the chart for rankings", async () => {
    const user = userEvent.setup();
    renderAnswer(message(ranking, rankingRows));
    await user.click(screen.getByRole("button", { name: /view analysis/i }));
    expect(screen.getByTestId("result-chart")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /hide analysis/i })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /table/i }));
    const table = within(screen.getByRole("table"));
    expect(table.getByText("Nexon")).toBeInTheDocument();
    expect(table.getByText("Punch")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /sql/i }));
    expect(document.body.textContent).toMatch(/SELECT\s+model,\s+units\s+FROM\s+t/);
  });

  it("an explicit request opens the analysis immediately on that tab", () => {
    renderAnswer(message(ranking, rankingRows), "sql");
    expect(document.body.textContent).toMatch(/SELECT\s+model,\s+units\s+FROM\s+t/);
    expect(screen.getByRole("button", { name: /hide analysis/i })).toBeInTheDocument();
  });

  it("single value shows the number large and never defaults to a chart", async () => {
    const user = userEvent.setup();
    renderAnswer(message(single, [{ revenue: 987_654_321 }]));
    expect(within(screen.getByTestId("result-preview")).getByText("₹987.7M")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /view analysis/i }));
    expect(screen.queryByTestId("result-chart")).not.toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("an explicit chart request on a single value falls back to the table", () => {
    renderAnswer(message(single, [{ revenue: 987_654_321 }]), "chart");
    expect(screen.queryByTestId("result-chart")).not.toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("keeps follow-ups outside the analysis so they appear once", async () => {
    const user = userEvent.setup();
    renderAnswer(message(ranking, rankingRows));
    await user.click(screen.getByRole("button", { name: /view analysis/i }));
    expect(screen.getAllByRole("button", { name: "What about South?" })).toHaveLength(1);
  });
});
