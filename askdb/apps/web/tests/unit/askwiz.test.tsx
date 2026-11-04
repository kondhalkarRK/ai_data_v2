import type { AskWizBoard, AskWizResults } from "@nql/shared-types";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AskWiz } from "@/components/analytics-builder/askwiz";
import { BuilderModes } from "@/components/analytics-builder/builder-modes";
import { apiClient } from "@/lib/api-client";

const session = vi.hoisted(() => ({ industry: "automotive", user: { id: "u1", role: "user", regionAccess: { zones: ["West"] } } }));
vi.mock("@/hooks/use-session", () => ({ useActiveIndustry: () => session.industry, useSession: () => ({ data: session.user }), useRegionAccess: () => ({ label: "West", zones: ["West"] }) }));
vi.mock("@/components/analytics-builder/analytics-builder-shell", () => ({ AnalyticsBuilderShell: () => <label>Existing Custom<input aria-label="Custom draft" /></label> }));
vi.mock("@/components/chat/result-chart", () => ({ ResultChart: ({ initialType }: { initialType: string }) => <div>Chart type: {initialType}</div> }));

const board: AskWizBoard = { id: "b1", title: "Weekly sales", revision: 1, saved: false, canUndo: false, message: "Governed recipe applied", llmCalls: 0, tokens: 0, definition: { version: 1, recipe: "weekly", start: "2026-10-26", end: "2026-11-01", priorStart: "2026-10-19", priorEnd: "2026-10-25", timezone: "Asia/Kolkata", filters: {}, charts: [{ id: "c1", title: "Daily revenue", metric: "revenue", dimension: "day", viz: "line" }] } };
const result = { title: "Revenue", columns: ["sales_day", "revenue"], rows: [{ sales_day: "2026-10-26", revenue: 120 }], sql: "SELECT governed_revenue", chart: { x: "sales_day", y: "revenue", type: "line", series: [], points: [{ sales_day: "2026-10-26", revenue: 120 }] }, recommendedViz: "line" as const, insights: { executive: "Revenue is ₹120.", analyst: "Computed from governed sales." }, meta: { dataAsOf: "2026-11-01", notes: [] } };
const results: AskWizResults = { boardId: "b1", revision: 1, charts: [{ chartId: "c1", result, error: null, cacheHit: false }], kpis: [], elapsedMs: 12, queryCount: 6, cacheHits: 0, computedAt: "2026-11-04T10:00:00Z" };

function setup(ui = <AskWiz />) {
  vi.spyOn(apiClient, "get").mockImplementation(async (path) => (path.endsWith("templates") ? { templates: [{ id: "weekly" }] } : []) as never);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}
afterEach(() => { vi.restoreAllMocks(); session.industry = "automotive"; });

describe("automotive AskWiz", () => {
  it("preserves Custom draft when toggling and does not expose Auto in insurance", async () => {
    const user = userEvent.setup();
    const view = setup(<BuilderModes pack={{} as never} />);
    expect(screen.getByRole("button", { name: "Custom" })).toHaveAttribute("aria-pressed", "true");
    await user.type(screen.getByLabelText("Custom draft"), "Keep my selection");
    await user.click(screen.getByRole("button", { name: "Auto · AskWiz" }));
    await user.click(screen.getByRole("button", { name: "Custom" }));
    expect(screen.getByLabelText("Custom draft")).toHaveValue("Keep my selection");
    session.industry = "insurance";
    view.rerender(<BuilderModes pack={{} as never} />);
    expect(screen.queryByRole("button", { name: "Auto · AskWiz" })).not.toBeInTheDocument();
    expect(screen.getByText("Existing Custom")).toBeInTheDocument();
  });

  it("renders charts before narration and uses separate ordinary API requests", async () => {
    const user = userEvent.setup();
    let finish!: (value: unknown) => void;
    const post = vi.spyOn(apiClient, "post").mockResolvedValueOnce(board).mockResolvedValueOnce(results).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    setup();
    await user.click(await screen.findByRole("button", { name: "Last week, explained" }));
    await screen.findByText("Chart type: line");
    expect(screen.getByText(/Composing narration/)).toBeInTheDocument();
    expect(post).toHaveBeenNthCalledWith(1, "/api/v1/analytics/auto/boards", expect.objectContaining({ recipe: "weekly" }), expect.objectContaining({ industry: "automotive" }));
    await act(async () => finish({ revision: 1, paragraphs: ["Revenue is ₹120."], aiUsed: true, llmCalls: 1, tokens: 20, limitation: null }));
    await screen.findByText("AI-curated briefing");
  });

  it("shows clarification without replacing the board or running queries", async () => {
    const user = userEvent.setup();
    const post = vi.spyOn(apiClient, "post").mockRejectedValue(new Error("Which exact dates do you mean?"));
    setup();
    await user.type(screen.getByLabelText("What would you like to understand?"), "Sales for second week");
    await user.click(screen.getByRole("button", { name: "Create dashboard" }));
    await screen.findByText(/Which exact dates/);
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("keeps successful charts usable when narration fails", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "post").mockResolvedValueOnce(board).mockResolvedValueOnce(results).mockRejectedValueOnce(new Error("Provider failed"));
    setup();
    await user.click(await screen.findByRole("button", { name: "Last week, explained" }));
    await screen.findByText(/AI narration could not be loaded/);
    expect(screen.getByText("Chart type: line")).toBeInTheDocument();
    await user.click(screen.getByText("Inspect data & evidence"));
    expect(screen.getByText("Underlying governed SQL")).toBeInTheDocument();
  });

  it("keeps previous chart results visibly labelled if an edited revision fails", async () => {
    const user = userEvent.setup();
    const post = vi.spyOn(apiClient, "post").mockResolvedValueOnce(board).mockResolvedValueOnce(results).mockResolvedValueOnce({ revision: 1, paragraphs: [], aiUsed: false, llmCalls: 0, tokens: 0 });
    setup();
    await user.click(await screen.findByRole("button", { name: "Last week, explained" }));
    await screen.findByText("Chart type: line");
    post.mockResolvedValueOnce({ ...board, revision: 2, canUndo: true }).mockRejectedValueOnce(new Error("Warehouse unavailable"));
    await user.type(screen.getByLabelText("Refine this dashboard"), "Apply last week to whole dashboard");
    await user.click(screen.getByRole("button", { name: "Update dashboard" }));
    await screen.findByText(/Warehouse unavailable/);
    expect(screen.getByText(/Previous results · computed/)).toBeInTheDocument();
    expect(screen.getByText("Chart type: line")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Update dashboard" })).toBeDisabled());
  });
});
