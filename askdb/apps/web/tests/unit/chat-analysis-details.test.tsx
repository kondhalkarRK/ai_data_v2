import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { ChatMessage } from "@/components/chat/types";

vi.mock("@/hooks/use-session", () => ({ useActiveIndustry: () => "automotive", useSession: () => ({ data: { id: "owner" } }) }));
vi.mock("@/hooks/use-trust-snapshot", () => ({ useTrustSnapshot: () => ({ data: { available: true, score: 86, label: "Good", formulaNote: "Configured quality checks", components: [{ id: "fresh", label: "Freshness", score: 90, weight: 0.5 }] } }) }));
vi.mock("@/components/chat/result-chart", () => ({ ResultChart: () => <div>Chart preview</div> }));

import { ResponseCard } from "@/components/chat/response-card";
import { CompactDataAnswer } from "@/components/chat/compact-data-answer";
import { ResponseActions } from "@/components/chat/response-actions";

const message: ChatMessage = {
  id: "answer", role: "assistant", complete: true, ratingDisabled: true,
  sql: "SELECT SUM(order_qty) AS units FROM fact_sales", columns: ["units"], rows: [{ units: 93 }],
  meta: {
    groundedOn: ["Semantic Layer", "Business Glossary"], ambiguityFlag: false,
    validationStatus: "passed", rowCount: 1, executionTimeMs: 5, sourceDatabase: "Automotive", dataAsOf: null,
    timings: { llmGenerationMs: 0, semanticLookupMs: 0, sqlValidationMs: 0, executionMs: 5, renderMs: 0 }, queryMeta: { tablesUsed: ["fact_sales"], metricsUsed: ["units"], dimensionsUsed: [], joinPath: [], filtersApplied: [], dateRange: null },
    insights: { executive: "93 units", analyst: "Verified result" }, anomalies: [], alternateInterpretations: [],
    confidence: { level: "high", label: "High confidence", score: 0.9, reasons: ["Approved measure"] },
    queryPlan: { formula: "SUM(order_qty)", metric: "units" },
  },
};

it.each(["classic", "new"] as const)("%s keeps tabs clear and all supporting details behind the info icon", async mode => {
  const user = userEvent.setup();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>
    {mode === "new" ? <CompactDataAnswer message={message} requestedTab={null} onAsk={vi.fn()} onAction={vi.fn()} /> : <ResponseCard message={message} onAsk={vi.fn()} onAction={vi.fn()} detailsInInfo />}
    <ResponseActions message={message} />
  </QueryClientProvider>);
  if (mode === "new") await user.click(screen.getByRole("button", { name: "View Analysis" }));
  for (const name of ["Table", "Chart", "Narration", "SQL"]) expect(screen.getByRole("tab", { name })).toBeInTheDocument();
  expect(screen.queryByText("High confidence")).not.toBeInTheDocument();
  expect(screen.queryByText("Grounded on")).not.toBeInTheDocument();
  expect(screen.queryByText(/Dataset Trust/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Thumbs up" })).not.toBeInTheDocument();
  const trigger = screen.getByRole("button", { name: "How Scio handled this" });
  await user.click(trigger);
  const panel = within(screen.getByRole("dialog", { name: "How Scio handled this" }));
  expect(panel.getByText("High confidence")).toBeInTheDocument();
  expect(panel.getByText("Approved measure")).toBeInTheDocument();
  expect(panel.getByText("Grounded on")).toBeInTheDocument();
  for (const source of ["Semantic Layer", "Business Glossary", "KPI Definition", "LLM", "Schema", "Data Quality Check"]) expect(panel.getByText(source)).toBeInTheDocument();
  expect(panel.getByText(/SUM\(order_qty\)/)).toBeInTheDocument();
  await user.click(panel.getByRole("button", { name: /Dataset Trust/ }));
  expect(panel.getByText("Configured quality checks")).toBeInTheDocument();
  expect(panel.getByText("Freshness")).toBeInTheDocument();
  await user.click(panel.getByText("View SQL"));
  expect(panel.getByText("View SQL").parentElement).toHaveAttribute("open");
  await user.keyboard("{Escape}");
  expect(trigger).toHaveFocus();
  expect(screen.getByRole("table")).toHaveTextContent("93");
});
