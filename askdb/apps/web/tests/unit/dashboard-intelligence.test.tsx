import type { DashboardAugmentation, DashboardExplanation } from "@nql/shared-types";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DashboardIntelligence, useDashboardActions } from "@/components/executive/dashboard-intelligence";
import { ApiError, apiClient } from "@/lib/api-client";
import { dashboardChange, mergeDashboardFilters } from "@/lib/executive/dashboard";
import { useRetainedQueryData } from "@/hooks/use-retained-query-data";

const augmentation: DashboardAugmentation = {
  snapshotToken: "server-result-token",
  context: { resultId: "result-1", industry: "automotive", semanticRevision: "rev-1", periodLabel: "Q2 2026", compareLabel: "Q2 2025", start: "2026-04-01", end: "2026-06-30", priorStart: "2025-04-01", priorEnd: "2025-06-30", filters: { zone: "West" }, dataAsOf: "2026-06-30", computedAt: "2026-07-01T12:00:00Z" },
  metrics: [{ id: "revenue", label: "Revenue", format: "currency", current: 120, prior: 100, definition: "SUM(total_sales)", dimensions: ["zone", "model"], supported: true, unavailableReason: null }],
  highlights: [{ metricId: "revenue", title: "Revenue", body: "Revenue increased by 20%.", tone: "positive" }],
  caveats: [], performance: { elapsedMs: 20, queryCount: 0, warehouseMs: 0, cacheHit: true },
};

const evidence: DashboardExplanation = {
  context: augmentation.context, metric: augmentation.metrics[0]!, dimension: "zone", narrative: "West contributed ₹20 to the change.",
  contributors: [{ label: "Tata Nexon", current: 120, prior: 100, change: 20, filters: { make: "Tata", model: "Nexon" }, residual: false }],
  caveats: ["Contributions are not proven causes."], sourceTables: ["automotive.fact_sales"], sql: "SELECT SUM(total_sales) FROM automotive.fact_sales", sqlParameters: {}, priorSqlParameters: {}, reconciled: true, evidenceChanged: false, queryCount: 0, elapsedMs: 0, conversationId: null, suggestedQuestions: [],
};

function Chart() {
  const actions = useDashboardActions();
  return <div><p>Existing revenue chart</p>{actions ? <button type="button" onClick={() => actions.explain("revenue")}>Explain chart</button> : null}</div>;
}

function setup(data: DashboardAugmentation | undefined = augmentation, onApply = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const content = (value: DashboardAugmentation | undefined, updating = false) => <QueryClientProvider client={client}><DashboardIntelligence augmentation={value} updating={updating} onApplyFilters={onApply} onRefresh={vi.fn()}><Chart /></DashboardIntelligence></QueryClientProvider>;
  const view = render(content(data));
  return { ...view, content, onApply, client };
}

describe("augmented dashboard", () => {
  it("retains the last successful data after failure, but never across industries", async () => {
    const value = { revenue: 120 };
    const { result, rerender } = renderHook(({ data, industry }) => useRetainedQueryData(data, industry), { initialProps: { data: value as typeof value | undefined, industry: "automotive" } });
    await act(async () => { await Promise.resolve(); });
    rerender({ data: undefined, industry: "automotive" });
    expect(result.current).toEqual(value);
    rerender({ data: undefined, industry: "insurance" });
    expect(result.current).toBeUndefined();
  });
  it("renders facts and charts without calling the answer API, and rolls back when absent", () => {
    const post = vi.spyOn(apiClient, "post");
    const view = setup();
    expect(screen.getByText("Existing revenue chart")).toBeInTheDocument();
    expect(screen.getByText("Revenue increased by 20%.")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
    view.rerender(view.content(undefined));
    expect(screen.getByText("Existing revenue chart")).toBeInTheDocument();
    expect(screen.queryByText("Executive briefing")).not.toBeInTheDocument();
  });

  it("uses server references, shows evidence and applies exact contributor filters", async () => {
    const user = userEvent.setup();
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(evidence);
    const view = setup();
    await user.click(screen.getByRole("button", { name: "Explain chart" }));
    await screen.findByText(evidence.narrative);
    expect(post).toHaveBeenCalledWith("/api/v1/executive/explain", { snapshotToken: augmentation.snapshotToken, metricId: "revenue", dimension: "zone" }, expect.objectContaining({ industry: "automotive", signal: expect.any(AbortSignal) }));
    await user.click(screen.getByRole("button", { name: "Apply filter" }));
    expect(view.onApply).toHaveBeenCalledWith({ make: "Tata", model: "Nexon" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("retains the captured context after selection changes and ignores a late old response", async () => {
    const user = userEvent.setup();
    let resolveOld!: (value: unknown) => void;
    const post = vi.spyOn(apiClient, "post").mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; })).mockResolvedValue({ ...evidence, narrative: "New view evidence" });
    const view = setup();
    await user.click(screen.getByRole("button", { name: "Explain chart" }));
    const updated = { ...augmentation, snapshotToken: "new-token", context: { ...augmentation.context, resultId: "result-2", periodLabel: "Q3 2026" } };
    view.rerender(view.content(updated, true));
    expect(screen.getByText(/panel still describes its earlier captured view/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use current selection" })).toBeDisabled();
    view.rerender(view.content(updated));
    await user.click(screen.getByRole("button", { name: "Use current selection" }));
    await screen.findByText("New view evidence");
    await act(async () => resolveOld(evidence));
    expect(screen.queryByText(evidence.narrative)).not.toBeInTheDocument();
    expect(post).toHaveBeenLastCalledWith(expect.anything(), expect.objectContaining({ snapshotToken: "new-token" }), expect.anything());
  });

  it("keeps charts available on expired results and AI quotas", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "post").mockRejectedValueOnce(new ApiError(409, { code: "dashboard_refresh_required", message: "Refresh the captured view", requestId: "x", details: {} })).mockRejectedValueOnce(new ApiError(429, { code: "quota_exceeded", message: "Quota exceeded", requestId: "x", details: {} }));
    setup();
    await user.click(screen.getByRole("button", { name: "Explain chart" }));
    await screen.findByText("Refresh the captured view");
    expect(screen.getByText("Existing revenue chart")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ask a follow-up" }));
    await user.type(screen.getByLabelText("Ask about the captured view"), "Which models changed?");
    await user.click(screen.getByRole("button", { name: /^Ask$/ }));
    await screen.findByText(/Weekly AI quota reached/);
    expect(screen.getByText("Existing revenue chart")).toBeInTheDocument();
  });

  it("aborts an in-flight question and returns focus on Escape", async () => {
    const user = userEvent.setup();
    let signal: AbortSignal | undefined;
    vi.spyOn(apiClient, "post").mockImplementation((_path, _body, options) => { signal = options?.signal as AbortSignal; return new Promise(() => {}); });
    setup();
    const opener = screen.getByRole("button", { name: "Ask about this view" });
    await user.click(opener);
    await user.type(screen.getByLabelText("Ask about the captured view"), "Explain revenue");
    await user.click(screen.getByRole("button", { name: /^Ask$/ }));
    await waitFor(() => expect(signal).toBeDefined());
    await user.keyboard("{Escape}");
    expect(signal?.aborted).toBe(true);
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it("preserves unrelated filters and formats ratio effects as percentage points", () => {
    expect(mergeDashboardFilters({ zone: "West", state: "MH", city: "Mumbai", dealer_id: "2", make: "Tata", model: "Nexon" }, { zone: "South" })).toEqual({ zone: "South", make: "Tata", model: "Nexon" });
    expect(mergeDashboardFilters({ make: "Tata", model: "Nexon", year: "2026" }, { make: "Hyundai", model: "Creta" })).toEqual({ make: "Hyundai", model: "Creta", year: "2026" });
    expect(dashboardChange(-.1, { format: "percent" })).toBe("-10.00 pp");
  });
});
