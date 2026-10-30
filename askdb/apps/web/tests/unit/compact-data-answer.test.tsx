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
    columns: Object.keys(rows[0] ?? { model: 1, units: 1 }),
    rows,
    followups: ["What about South?"],
    meta: {
      groundedOn: [],
      ambiguityFlag: false,
      validationStatus: "passed",
      rowCount: profile.rowCount,
      executionTimeMs: 5,
      sourceDatabase: "db",
      dataAsOf: null,
      timings: {},
      queryMeta: {
        tablesUsed: [],
        metricsUsed: [],
        dimensionsUsed: [],
        joinPath: [],
        filtersApplied: [],
        dateRange: null,
      },
      insights: {
        executive: "x",
        analyst: "y",
        narration: {
          summary: "Nexon leads with 9,100 units.",
          highlights: ["Nexon is ahead on units sold."],
          insight: "Focus on the leading models in the result.",
          focus: null,
        },
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
    {
      label: "Nexon",
      values: [
        { column: "units", text: "9,100" },
        { column: "revenue", text: "₹91.0M" },
      ],
    },
    {
      label: "Punch",
      values: [
        { column: "units", text: "7,400" },
        { column: "revenue", text: "₹52.0M" },
      ],
    },
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

const trend: ResultProfile = {
  shape: "time_series",
  rowCount: 6,
  labelColumns: ["month"],
  measures: [{ column: "revenue", label: "revenue", kind: "currency" }],
  preview: [
    { label: "2024-01", values: [{ column: "revenue", text: "₹10M" }] },
    { label: "2024-06", values: [{ column: "revenue", text: "₹18M" }] },
  ],
  previewTruncated: false,
  chartSuitable: true,
  mayBeTruncated: false,
};

const trendRows = [
  { month: "2024-01", revenue: 10_000_000 },
  { month: "2024-02", revenue: 12_000_000 },
  { month: "2024-03", revenue: 11_000_000 },
  { month: "2024-04", revenue: 14_000_000 },
  { month: "2024-05", revenue: 16_000_000 },
  { month: "2024-06", revenue: 18_000_000 },
];

function renderAnswer(
  msg: ChatMessage,
  requestedTab: Parameters<typeof CompactDataAnswer>[0]["requestedTab"] = null,
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CompactDataAnswer
        message={msg}
        requestedTab={requestedTab}
        onAsk={vi.fn()}
        onAction={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

describe("CompactDataAnswer conversational workspace", () => {
  it("ranking: narration, ranked list, inline chart, analysis hidden", () => {
    renderAnswer(message(ranking, rankingRows));
    expect(screen.getByText("Nexon leads with 9,100 units.")).toBeInTheDocument();
    expect(screen.getByText("Nexon is ahead on units sold.")).toBeInTheDocument();
    const visual = screen.getByTestId("inline-result-visual");
    expect(visual).toHaveAttribute("data-layout", "ranked_list");
    const preview = within(screen.getByTestId("result-preview"));
    expect(preview.getByText("Nexon")).toBeInTheDocument();
    expect(preview.getByText("9,100")).toBeInTheDocument();
    expect(preview.getByText(/₹52\.0M/)).toBeInTheDocument();
    expect(preview.getByText(/Showing 2 of 8/)).toBeInTheDocument();
    expect(screen.getByTestId("result-chart")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /view analysis/i })).toBeInTheDocument();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  });

  it("View Analysis reveals the existing tabs over the same rows", async () => {
    const user = userEvent.setup();
    renderAnswer(message(ranking, rankingRows));
    await user.click(screen.getByRole("button", { name: /view analysis/i }));
    expect(screen.getAllByTestId("result-chart").length).toBeGreaterThanOrEqual(1);
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

  it("single value → KPI card, never an inline chart", async () => {
    const user = userEvent.setup();
    renderAnswer(message(single, [{ revenue: 987_654_321 }]));
    expect(screen.getByTestId("inline-result-visual")).toHaveAttribute("data-layout", "kpi");
    expect(within(screen.getByTestId("kpi-card")).getByText("₹987.7M")).toBeInTheDocument();
    expect(screen.queryByTestId("result-chart")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /view analysis/i }));
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("time series → inline trend chart from the same rows", () => {
    renderAnswer(message(trend, trendRows));
    expect(screen.getByTestId("inline-result-visual")).toHaveAttribute("data-layout", "trend_chart");
    expect(screen.getByTestId("result-chart")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /view analysis/i })).toBeInTheDocument();
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
