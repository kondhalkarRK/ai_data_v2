import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import type { BiPanel, BiPlan, BiReport } from "@nql/shared-types";
import { apiClient } from "@/lib/api-client";
import { ReportFilters } from "@/components/analytics-builder/askbi/report-filters";
import { ReportCanvas } from "@/components/analytics-builder/askbi/report-canvas";
import { buildOutlookBody, createOutlookDraft, getOutlookToken, prepareOutlookAuth } from "@/components/analytics-builder/askbi/outlook-draft";
import { panelScope, reportReady } from "@/components/analytics-builder/askbi/use-askbi";
import type { PanelResult } from "@/components/analytics-builder/askbi/use-askbi";

vi.mock("@azure/msal-browser", () => ({ createStandardPublicClientApplication: vi.fn(async () => ({ getAllAccounts: () => [], loginPopup: async () => ({ accessToken: "fixture-token" }) })) }));
vi.mock("html2canvas", () => ({ default: vi.fn(async () => ({ width: 800, height: 250, toDataURL: () => "data:image/jpeg;base64,anBlZw==" })) }));
vi.mock("jspdf", () => ({ jsPDF: class { addPage() {} addImage() {} output() { return "data:application/pdf;base64,cGRm"; } } }));
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

const spec = { metrics: ["revenue"], dimensions: [], filters: [], viz: "kpi" as const, analysis: "basic" as const, datePreset: "custom" as const, dateFrom: "2026-10-01", dateTo: "2026-10-31", limit: 1, orderDirection: "desc" as const, window: 3, rankMethod: "rank" as const };
const plan: BiPlan = { version: 2, title: "CEO <Sales>", answerKind: "report", assumptions: [], reportFilter: { period: "month", year: 2026, month: 10, make: null }, panels: [
  { id: "revenue", title: "Revenue", kind: "kpi", daily: false, grain: null, section: "Key metrics", dateIntent: null, calculation: null, rationale: "Governed", spec },
  { id: "units", title: "Units sold", kind: "kpi", daily: false, grain: null, section: "Key metrics", dateIntent: null, calculation: null, rationale: "Governed", spec: { ...spec, metrics: ["units_sold"] } },
] };

it("shows six distinct starters and puts the chosen question in the composer", async () => {
  const onExample = vi.fn();
  render(<ReportCanvas plan={null} results={{}} selected={null} onSelect={vi.fn()} onCommand={vi.fn()} onRetry={vi.fn()} onExample={onExample} busy={false} briefing={[]} />);
  const starters = ["Sales Report for CEO", "Financial Sales Briefing for CFO", "Region & Dealer Performance", "Sales Team Performance", "Make & Model Comparison", "Sales Momentum & Emerging Models"];
  for (const question of starters) expect(screen.getByRole("button", { name: new RegExp(question.replace(/[&]/g, "&")) })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Sales Report for CEO/ }));
  expect(onExample).toHaveBeenCalledWith("Sales Report for CEO");
});

it("submits one Monday-Sunday week and make selection without an LLM request", async () => {
  vi.spyOn(apiClient, "get").mockResolvedValue({ values: [{ value: "Tata" }] } as never);
  const onApply = vi.fn();
  render(<ReportFilters plan={plan} busy={false} onApply={onApply} />);
  await waitFor(() => expect(screen.getByRole("option", { name: "Tata" })).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Period"), "week");
  fireEvent.change(screen.getByLabelText("Week starting Monday"), { target: { value: "2026-W45" } });
  await userEvent.selectOptions(screen.getByLabelText("Make"), "Tata");
  await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));
  expect(onApply).toHaveBeenCalledWith({ period: "week", year: 2026, weekStart: "2026-11-02", make: "Tata", region: null });
});

it("labels an arbitrary AI date range without pretending it is a month", async () => {
  vi.spyOn(apiClient, "get").mockResolvedValue({ values: [] } as never);
  render(<ReportFilters plan={{ ...plan, reportFilter: null, panels: [{ ...plan.panels[0]!, spec: { ...spec, dateFrom: "2026-10-26", dateTo: "2026-11-01" } }] }} busy={false} onApply={vi.fn()} />);
  expect(screen.getByRole("option", { name: "Current range" })).toBeInTheDocument();
  expect(screen.getByText(/Current dates: 2026-10-26 to 2026-11-01/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Apply filters" })).toBeDisabled();
  await waitFor(() => expect(apiClient.get).toHaveBeenCalled());
});

it("offers permitted region refinement on the region and dealer report", async () => {
  vi.spyOn(apiClient, "get").mockImplementation(async path => ({ values: [{ value: path.includes("region-options") ? "Mumbai" : "Tata" }] }) as never);
  const onApply = vi.fn();
  const regional = { ...plan, panels: [{ ...plan.panels[0]!, title: "Region and model mix" }] };
  render(<ReportFilters plan={regional} busy={false} onApply={onApply} />);
  await waitFor(() => expect(screen.getByRole("option", { name: "Mumbai" })).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Region"), "Mumbai");
  await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));
  expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ period: "month", region: "Mumbai" }));
});

it("keeps PDF and Outlook disabled for stale, incomplete or failed panels", () => {
  const current = Object.fromEntries(plan.panels.map(panel => [panel.id, { scope: panelScope(panel), result: { rows: [], meta: {} } }])) as unknown as Record<string, PanelResult>;
  expect(reportReady(plan, current)).toBe(true);
  expect(reportReady(plan, { ...current, units: { ...current.units, scope: "previous-scope" } })).toBe(false);
  expect(reportReady(plan, { ...current, units: { ...current.units, loading: true } })).toBe(false);
  expect(reportReady(plan, { ...current, units: { ...current.units, error: "timeout" } })).toBe(false);
});

it("uses completed KPI values and active scope in a short escaped Outlook body", () => {
  const scoped: BiPlan = { ...plan, reportFilter: { period: "month", year: 2026, month: 10, make: "Tata" }, panels: [...plan.panels, { ...plan.panels[0]!, id: "regional", title: "Revenue by region", kind: "chart", spec: { ...spec, viz: "bar", dimensions: ["region"] } }] };
  const results = {
    revenue: { result: { rows: [{ revenue: 1234567.4 }], meta: { valueColumn: "revenue", metricFormat: "currency" } } },
    units: { result: { rows: [], meta: { valueColumn: "units_sold" } } },
    regional: { result: { rows: [{ region: "West", revenue: 120 }], meta: { valueColumn: "revenue", metricFormat: "currency" } } },
  } as never;
  const body = buildOutlookBody(scoped, results, ["Revenue increased from verified data."], Array.from({ length: 4 }, (_, i) => ({ title: i === 0 ? "Revenue by region" : `Chart ${i + 1}`, cid: `chart-${i + 1}` })), "https://ask.example/analytics-builder?askbiReport=1");
  expect(body).toContain("CEO &lt;Sales&gt;");
  expect(body).toContain("2026-10-01 to 2026-10-31 · Tata");
  expect(body).toContain("₹12,34,567.4");
  expect(body).toContain("No data");
  expect(body).toContain("West: ₹120");
  expect(body).toContain("cid:chart-3");
  expect(body).not.toContain("cid:chart-4");
  expect(body).toContain("askbiReport=1");
});

it("creates only a reviewable Graph draft with inline chart and full PDF", async () => {
  vi.stubEnv("NEXT_PUBLIC_ASK_ME_OUTLOOK_CLIENT_ID", "client-id");
  vi.stubEnv("NEXT_PUBLIC_ASK_ME_OUTLOOK_TENANT_ID", "tenant-id");
  const chart: BiPanel = { ...plan.panels[0]!, id: "chart", title: "Revenue trend", kind: "chart", spec: { ...spec, viz: "line", analysis: "trend", dimensions: ["month"] } };
  const report: BiReport = { id: "report-id", revision: 2, title: plan.title, saved: true, warning: null, state: { plan: { ...plan, panels: [...plan.panels, chart] }, previous: null, pending: null, turns: [], usage: { llmCalls: 0, tokens: 0, usageComplete: true, elapsedMs: 1 } } };
  const results = Object.fromEntries(report.state.plan!.panels.map(panel => [panel.id, { scope: panelScope(panel), result: { rows: [{ [panel.spec.metrics[0]!]: 120 }], meta: { valueColumn: panel.spec.metrics[0] } } }])) as never;
  const root = document.createElement("div");
  root.innerHTML = '<div data-askbi-pdf>Report</div><div id="askbi-panel-chart" data-askbi-pdf>Chart</div>';
  const fetchDraft = vi.fn(async () => new Response(JSON.stringify({ webLink: "https://outlook.office.com/draft/1" }), { status: 201, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchDraft);
  const link = await createOutlookDraft(report, results, ["Verified briefing."], root, "West", "fixture-token");
  expect(link).toContain("/draft/1");
  expect(fetchDraft).toHaveBeenCalledOnce();
  const [url, options] = fetchDraft.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("https://graph.microsoft.com/v1.0/me/messages");
  expect(options.method).toBe("POST");
  const message = JSON.parse(String(options.body));
  expect(message).not.toHaveProperty("toRecipients");
  expect(message.body.content).toContain("West");
  expect(message.attachments).toEqual(expect.arrayContaining([
    expect.objectContaining({ isInline: true, contentId: "askbi-chart-1", contentType: "image/jpeg" }),
    expect.objectContaining({ isInline: false, name: "AskBI-report.pdf", contentType: "application/pdf" }),
  ]));
});

it("prepares the Outlook client before requesting delegated draft access", async () => {
  vi.stubEnv("NEXT_PUBLIC_ASK_ME_OUTLOOK_CLIENT_ID", "client-id");
  vi.stubEnv("NEXT_PUBLIC_ASK_ME_OUTLOOK_TENANT_ID", "tenant-id");
  await prepareOutlookAuth();
  expect(await getOutlookToken()).toBe("fixture-token");
});
