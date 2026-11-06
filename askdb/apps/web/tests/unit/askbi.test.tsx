import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import type { BiPanel, BiReport } from "@nql/shared-types";
import { apiClient } from "@/lib/api-client";
import { useAskBI } from "@/components/analytics-builder/askbi/use-askbi";
import { BuilderModes } from "@/components/analytics-builder/builder-modes";

vi.mock("@/components/analytics-builder/analytics-builder-shell", () => ({ AnalyticsBuilderShell: () => <div>Custom builder content</div> }));
vi.mock("@/components/analytics-builder/analytics-workspace", () => ({ AnalyticsWorkspace: () => <div>Legacy unified content</div> }));
vi.mock("@/components/analytics-builder/askwiz", () => ({ AskWiz: () => <div>Old AskWiz content</div> }));
vi.mock("@/components/analytics-builder/askbi/askbi", () => ({ AskBI: () => <div>AskBI report content</div> }));
const session = vi.hoisted(() => ({ industry: "automotive" }));
vi.mock("@/hooks/use-session", () => ({ useActiveIndustry: () => session.industry, useSession: () => ({ data: { id: "user", role: "admin", regionAccess: {} } }) }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); session.industry = "automotive"; });

const panel: BiPanel = { id: "p1", title: "Revenue", kind: "chart", daily: false, grain: "day", section: "Sales", dateIntent: "last week", calculation: null, rationale: "Governed revenue", spec: { metrics: ["revenue"], dimensions: ["month"], filters: [], viz: "line", analysis: "trend", datePreset: "custom", dateFrom: "2026-10-26", dateTo: "2026-11-01", limit: 500, orderDirection: "asc", window: 3, rankMethod: "rank" } };
const usage = { llmCalls: 0, tokens: 0, usageComplete: true, elapsedMs: 1 };
const draft = (): BiReport => ({ id: "report-1", revision: 1, title: "Draft", saved: false, warning: null, state: { plan: null, previous: null, pending: null, turns: [], usage } });
const answer = (panels = [panel], revision = 2): BiReport => ({ ...draft(), revision, title: "Sales report", state: { ...draft().state, plan: { version: 2, title: "Sales report", answerKind: "report", panels, assumptions: [] }, turns: [{ id: `turn-${revision}`, question: "Sales", answer: "Prepared the requested analysis.", kind: "answer", code: null, changedPanelIds: panels.map(p => p.id) }] } });
const runResult = { result: { title: "Revenue", rows: [{ day: "Monday", revenue: 120 }], columns: ["day", "revenue"], meta: {}, sql: "SELECT approved_metric", recommendedViz: "line" }, evidence: "", elapsedMs: 1, queryCount: 2 };
function setup() {
  vi.spyOn(apiClient, "get").mockImplementation(async path => path.endsWith("capabilities") ? { enabled: true, engine: "askbi-v2", schemaVersion: 2 } as never : [] as never);
  return vi.spyOn(apiClient, "post");
}
async function ready(hook: ReturnType<typeof renderHook<ReturnType<typeof useAskBI>, unknown>>) {
  await waitFor(() => expect(hook.result.current.capability?.enabled).toBe(true));
}

it("restores Custom and Auto despite the older unified flag", async () => {
  vi.stubEnv("NEXT_PUBLIC_ASK_ME_ASKBI_ENABLED", "true");
  vi.stubEnv("NEXT_PUBLIC_ASK_ME_ANALYTICS_WORKSPACE_ENABLED", "true");
  render(<BuilderModes pack={{} as never} />);
  expect(screen.getByRole("button", { name: "Custom Report" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Auto Report · AskBI" }));
  expect(screen.getByText("AskBI report content")).toBeVisible();
  expect(screen.queryByText("Legacy unified content")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Custom Report" }));
  expect(screen.getByText("Custom builder content")).toBeVisible();
});

it("leaves insurance on its existing Custom implementation", () => {
  vi.stubEnv("NEXT_PUBLIC_ASK_ME_ASKBI_ENABLED", "true"); session.industry = "insurance";
  render(<BuilderModes pack={{} as never} />);
  expect(screen.getByText("Custom builder content")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /AskBI/ })).not.toBeInTheDocument();
});

it("opens Auto Report for a saved-report link", async () => {
  vi.stubEnv("NEXT_PUBLIC_ASK_ME_ASKBI_ENABLED", "true");
  window.history.replaceState({}, "", "/analytics-builder?askbiReport=report-1");
  try {
    render(<BuilderModes pack={{} as never} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Auto Report · AskBI" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByText("AskBI report content")).toBeVisible();
  } finally { window.history.replaceState({}, "", "/"); }
});

it("opens Auto Report from the Home CTA without opening a saved report", async () => {
  vi.stubEnv("NEXT_PUBLIC_ASK_ME_ASKBI_ENABLED", "true");
  window.history.replaceState({}, "", "/analytics-builder?mode=auto");
  try {
    render(<BuilderModes pack={{} as never} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Auto Report · AskBI" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByText("AskBI report content")).toBeVisible();
  } finally { window.history.replaceState({}, "", "/"); }
});

it("keeps one durable conversation through clarification and short answer", async () => {
  const post = setup(); let turns = 0;
  const clarification: BiReport = { ...draft(), revision: 2, state: { ...draft().state, pending: { question: "Sales", clarification: "Which period?", selectedPanelId: null }, turns: [{ id: "t1", question: "Sales", answer: "Which period?", kind: "clarification", code: null, changedPanelIds: [] }] } };
  post.mockImplementation(async path => path.endsWith("/reports") ? draft() as never : path.endsWith("/turns") ? (++turns === 1 ? clarification : answer([panel], 3)) as never : runResult as never);
  const hook = renderHook(useAskBI); await ready(hook);
  await act(() => hook.result.current.command("ask", "Sales"));
  expect(hook.result.current.report?.state.pending?.question).toBe("Sales");
  expect(post.mock.calls.filter(([p]) => p.endsWith("/run"))).toHaveLength(0);
  await act(() => hook.result.current.command("ask", "Revenue last week"));
  expect(post.mock.calls.filter(([p]) => p.endsWith("/reports"))).toHaveLength(1);
  const sent = post.mock.calls.filter(([p]) => p.endsWith("/turns"))[1]?.[1];
  expect(sent).toMatchObject({ revision: 2, question: "Revenue last week" });
  expect(hook.result.current.results.p1?.result?.rows).toHaveLength(1);
});

it("does not rerun data for presentation-only edits", async () => {
  const post = setup(); let turns = 0;
  post.mockImplementation(async path => {
    if (path.endsWith("/reports")) return draft() as never;
    if (path.endsWith("/turns")) return answer([{ ...panel, spec: { ...panel.spec, viz: ++turns === 1 ? "line" : "bar" } }], turns + 1) as never;
    return runResult as never;
  });
  const hook = renderHook(useAskBI); await ready(hook);
  await act(() => hook.result.current.command("ask", "Daily sales last week"));
  await act(() => hook.result.current.command("visualize", "", "bar", "p1"));
  expect(post.mock.calls.filter(([p]) => p.endsWith("/run"))).toHaveLength(1);
  expect(hook.result.current.report?.state.plan?.panels[0]?.spec.viz).toBe("bar");
});

it("retains successful panels when a different query fails", async () => {
  const post = setup();
  const orders = { ...panel, id: "p2", title: "Orders", spec: { ...panel.spec, metrics: ["orders"] } };
  post.mockImplementation(async (path, body) => {
    if (path.endsWith("/reports")) return draft() as never;
    if (path.endsWith("/turns")) return answer([panel, orders]) as never;
    if ((body as { panelId: string }).panelId === "p2") throw new Error("Query timeout");
    return runResult as never;
  });
  const hook = renderHook(useAskBI); await ready(hook);
  await act(() => hook.result.current.command("ask", "Revenue and orders"));
  expect(hook.result.current.results.p1?.result).toBeDefined();
  expect(hook.result.current.results.p2?.error).toBe("Query timeout");
  expect(hook.result.current.error).toContain("1 panel(s)");
});

it("discards a late turn response after New report", async () => {
  const post = setup(); let finish: (value: unknown) => void = () => {};
  post.mockImplementation(async path => path.endsWith("/reports") ? draft() as never : new Promise(resolve => { finish = resolve; }) as never);
  const hook = renderHook(useAskBI); await ready(hook);
  let work: Promise<BiReport | undefined>;
  act(() => { work = hook.result.current.command("ask", "Old question"); });
  await waitFor(() => expect(post.mock.calls.some(([p]) => p.endsWith("/turns"))).toBe(true));
  act(() => hook.result.current.reset());
  await act(async () => { finish(answer()); await work; });
  expect(hook.result.current.report).toBeNull();
  expect(hook.result.current.results).toEqual({});
});

it("retries an acknowledged provider error with a new request ID", async () => {
  const post = setup(); let turns = 0;
  const failed = { ...answer(), state: { ...draft().state, turns: [{ id: "failed", question: "Analyze sales", answer: "Provider unavailable", kind: "error", code: "provider_unavailable", changedPanelIds: [] }] } };
  post.mockImplementation(async path => path.endsWith("/reports") ? draft() as never : path.endsWith("/turns") ? (++turns === 1 ? failed : answer()) as never : runResult as never);
  const hook = renderHook(useAskBI); await ready(hook);
  await act(() => hook.result.current.command("ask", "Analyze sales"));
  await act(() => hook.result.current.command("ask", "", undefined, null, true));
  const bodies = post.mock.calls.filter(([p]) => p.endsWith("/turns")).map(([, body]) => body as { requestId: string; question: string });
  expect(bodies[1]?.question).toBe("Analyze sales");
  expect(bodies[1]?.requestId).not.toBe(bodies[0]?.requestId);
});
