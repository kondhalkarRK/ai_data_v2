import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { AnalyticsWorkspace } from "@/components/analytics-builder/analytics-workspace";
import { apiClient } from "@/lib/api-client";

vi.mock("@/components/analytics-builder/analytics-builder-shell", () => ({ AnalyticsBuilderShell: () => <div>Structured builder</div> }));
vi.mock("@/components/chat/result-chart", () => ({ ResultChart: () => <div>Chart</div> }));
vi.mock("@/hooks/use-analytics", () => ({ EMPTY_SPEC: { metrics: [], dimensions: [], filters: [], analysis: "basic", limit: 25, window: 3, rankMethod: "rank", orderDirection: "desc" }, useAnalyticsCapabilities: () => ({ data: null }) }));
afterEach(() => vi.restoreAllMocks());

const basePanel = { id: "p1", title: "Revenue", kind: "chart", daily: true, rationale: "Governed sales", spec: { metrics: ["revenue"], dimensions: ["month"], filters: [], viz: "line", datePreset: "custom", dateFrom: "2026-10-26", dateTo: "2026-11-01" } };
const data = { title: "Revenue", rows: [{ month: "2026-10-26", revenue: 120 }], columns: ["month", "revenue"], insights: { executive: "Verified revenue", analyst: "Verified" }, meta: {}, chart: { x: "month", y: "revenue", points: [{ month: "2026-10-26", revenue: 120 }], series: [], type: "line" } };
const response = (title = "Weekly sales", panels = [basePanel]) => ({ plan: { answerKind: "analysis", title, panels, assumptions: [], clarification: null }, elapsedMs: 1, llmCalls: 0, tokens: 0 });

it("keeps successful panels when another panel fails", async () => {
  vi.spyOn(apiClient, "get").mockResolvedValue([]);
  let runs = 0;
  vi.spyOn(apiClient, "post").mockImplementation(async path => {
    if (path.endsWith("plan")) return response("Two views", [basePanel, { ...basePanel, id: "p2", title: "Orders", spec: { ...basePanel.spec, metrics: ["orders"] } }]) as never;
    if (++runs === 2) throw new Error("Orders connection failed");
    return { result: data, evidence: "", elapsedMs: 1, queryCount: 3 } as never;
  });
  render(<AnalyticsWorkspace pack={{} as never} />);
  await userEvent.type(screen.getByRole("textbox", { name: /^Ask Analytics/ }), "Two views");
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Orders connection failed");
  expect(screen.getByText("Verified revenue")).toBeInTheDocument();
  expect(screen.getAllByRole("article")).toHaveLength(2);
});

it("ignores a late response after a newer question completes", async () => {
  vi.spyOn(apiClient, "get").mockResolvedValue([]);
  let finishOld: (value: unknown) => void = () => {};
  let plans = 0;
  vi.spyOn(apiClient, "post").mockImplementation(async path => {
    if (path.endsWith("plan")) {
      if (++plans === 1) return new Promise(resolve => { finishOld = resolve; }) as never;
      return response("Current question") as never;
    }
    return { result: data, evidence: "", elapsedMs: 1, queryCount: 3 } as never;
  });
  render(<AnalyticsWorkspace pack={{} as never} />);
  const input = screen.getByRole("textbox", { name: /^Ask Analytics/ });
  await userEvent.type(input, "Old question");
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  await userEvent.clear(input); await userEvent.type(input, "New question");
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  await screen.findByRole("heading", { name: "Current question" });
  finishOld(response("Stale question"));
  await waitFor(() => expect(screen.queryByRole("heading", { name: "Stale question" })).not.toBeInTheDocument());
});

it("reuses returned data for a conversational chart-type edit", async () => {
  vi.spyOn(apiClient, "get").mockResolvedValue([]);
  let runs = 0;
  let plans = 0;
  vi.spyOn(apiClient, "post").mockImplementation(async path => {
    if (path.endsWith("plan")) return (++plans === 1 ? response() : response("Edited", [{ ...basePanel, spec: { ...basePanel.spec, viz: "bar" } }])) as never;
    runs++; return { result: data, evidence: "", elapsedMs: 1, queryCount: 3 } as never;
  });
  render(<AnalyticsWorkspace pack={{} as never} />);
  const input = screen.getByRole("textbox", { name: /^Ask Analytics/ });
  await userEvent.type(input, "Daily sales last week");
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  await screen.findByText("Verified revenue");
  await userEvent.type(input, "Change this chart to bar");
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  await screen.findByRole("heading", { name: "Edited" });
  expect(runs).toBe(1);
});

it("renders a single KPI response without forcing charts", async () => {
  vi.spyOn(apiClient, "get").mockResolvedValue([]);
  vi.spyOn(apiClient, "post").mockImplementation(async path => (path.endsWith("plan") ? {
    plan: { answerKind: "single_value", title: "Total revenue", assumptions: [], clarification: null,
      panels: [{ id: "p1", title: "Revenue", kind: "kpi", rationale: "Governed revenue", spec: { metrics: ["revenue"], dimensions: [], filters: [], viz: "kpi" } }] },
  } : { result: { rows: [{ revenue: 120 }], columns: ["revenue"], insights: null, meta: {} }, evidence: "", elapsedMs: 1, queryCount: 1 }) as never);
  render(<AnalyticsWorkspace pack={{} as never} />);
  await userEvent.type(screen.getByRole("textbox", { name: /^Ask Analytics/ }), "Total revenue last month");
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  expect(await screen.findByText("120")).toBeInTheDocument();
  expect(screen.queryByText("Chart")).not.toBeInTheDocument();
});

it("shows clarification without executing data queries", async () => {
  vi.spyOn(apiClient, "get").mockResolvedValue([]);
  const post = vi.spyOn(apiClient, "post").mockResolvedValue({ plan: { answerKind: "clarification", title: "Clarify", panels: [], assumptions: [], clarification: "Which metric and period?" } });
  render(<AnalyticsWorkspace pack={{} as never} />);
  await userEvent.type(screen.getByRole("textbox", { name: /^Ask Analytics/ }), "Show performance");
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Which metric and period?"));
  expect(post).toHaveBeenCalledTimes(1);
});
