import { zipReportFiles } from "@/components/analytics-builder/askbi/report-zip";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BiReport } from "@nql/shared-types";
import { formatReportValue, reportCategoryColor } from "@/components/analytics-builder/askbi/report-format";
import { createReportSnapshot, copyReportImage, assertReportCanvas } from "@/components/analytics-builder/askbi/report-export";
import { createOutlookDraft } from "@/components/analytics-builder/askbi/outlook-draft";
import { panelScope, type PanelResult } from "@/components/analytics-builder/askbi/use-askbi";
const mocks = vi.hoisted(() => ({ image: "data:image/png;base64,cG5n" }));
vi.mock("html2canvas", () => ({ default: vi.fn(async () => ({ width: 800, height: 250, getContext: () => ({ getImageData: () => ({ data: new Uint8ClampedArray([255, 255, 255, 255, 0, 0, 0, 255]) }) }), toDataURL: () => mocks.image })) }));
vi.mock("jspdf", () => ({ jsPDF: class { addPage() {} addImage() {} output() { return "data:application/pdf;base64,cGRm"; } } }));
afterEach(() => { vi.unstubAllGlobals(); mocks.image = "data:image/png;base64,cG5n"; });

function fixture(count = 4) {
  const panels = Array.from({ length: count }, (_, i) => ({ id: `panel-${i}`, title: `Chart ${i}`, kind: "chart", spec: { metrics: ["revenue"], dimensions: ["region"], dateFrom: "2026-10-01", dateTo: "2026-10-31" } }));
  const report = { id: "report", revision: 4, saved: true, state: { plan: { title: "Sales", panels, assumptions: ["Last completed month"] }, turns: [{ question: "Sales by region" }] } } as unknown as BiReport;
  const results = Object.fromEntries(report.state.plan!.panels.map(panel => [panel.id, { scope: panelScope(panel), result: { columns: ["region", "revenue"], rows: [{ region: "West", revenue: 83402902 }], meta: { metricFormat: "currency", valueColumn: "revenue" } } }])) as unknown as Record<string, PanelResult>;
  const root = document.createElement("div");
  root.innerHTML = '<header data-askbi-pdf>Sales</header>' + panels.map(p => `<section id="askbi-panel-${p.id}" data-askbi-pdf><h3>${p.title}</h3><div data-export-value="₹8.34 crore">0</div><button>Options</button></section>`).join("");
  return { report, results, root };
}

describe("report number semantics", () => {
  it.each([
    [83402902, "currency", "₹8.34 crore"], [834029, "currency", "₹8.34 lakh"],
    [45200, "currency", "₹45,200"], [0, "currency", "₹0"],
    [-83402902, "currency", "−₹8.34 crore"], [100000, "currency", "₹1 lakh"],
    [10000000, "currency", "₹1 crore"], [99999.999, "currency", "₹1 lakh"],
    [83402902, "number", "8,34,02,902"], [12.5, "percentage", "12.5%"],
    [null, "currency", "—"], [NaN, "currency", "—"], [Infinity, "currency", "—"],
  ])("formats %s as %s", (value, kind, expected) => expect(formatReportValue(value, kind)).toBe(expected));
  it("retains exact Indian-grouped values and stable category colors", () => {
    expect(formatReportValue(83402902.125, "currency", false)).toBe("₹8,34,02,902.125");
    expect(reportCategoryColor("West")).toBe(reportCategoryColor("West"));
  });
});

it("freezes results and settles animated values without mutating the screen", () => {
  const { report, results, root } = fixture();
  const snapshot = createReportSnapshot(report, results, ["Full briefing"], root, "West", 20);
  results["panel-0"]!.result!.rows[0]!.revenue = 1;
  root.textContent = "New report";
  expect(snapshot.results["panel-0"]!.result!.rows[0]!.revenue).toBe(83402902);
  expect(snapshot.root.textContent).toContain("₹8.34 crore");
  expect(snapshot.root.querySelector("button")).toBeNull();
  expect(Object.isFrozen(snapshot.results)).toBe(true);
});

it("rejects stale results before capture", () => {
  const { report, results, root } = fixture(); results["panel-0"]!.scope = "old";
  expect(() => createReportSnapshot(report, results, [], root, "West", 10)).toThrow("current panels");
});

it("uploads every chart and PDF separately without sending or dropping context", async () => {
  const { report, results, root } = fixture();
  const request = vi.fn(async () => new Response(JSON.stringify({ id: "draft", webLink: "https://outlook.office.com/draft" }), { status: 201 })); vi.stubGlobal("fetch", request);
  await createOutlookDraft(report, results, ["One", "Two", "Three", "Unavailable prior comparison"], root, "West", "token");
  expect(request).toHaveBeenCalledTimes(6);
  const calls = request.mock.calls as unknown as Array<[string, RequestInit]>;
  const body = JSON.parse(String(calls[0]![1].body));
  expect(body.body.content).toContain("Three");
  expect(body.body.content).toContain("Unavailable prior comparison");
  expect(body.body.content).toContain("cid:askbi-chart-4");
  expect(body.body.content).toContain("₹8.34 crore");
  expect(body).not.toHaveProperty("toRecipients");
  expect(calls.some(([url]) => url.includes("/send"))).toBe(false);
});

it.each([true, false])("cleans partial uploads and reports cleanup outcome (%s)", async removed => {
  const { report, results, root } = fixture(1);
  const request = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ id: "draft" }), { status: 201 })).mockResolvedValueOnce(new Response("failed", { status: 500 })).mockResolvedValueOnce(new Response(null, { status: removed ? 204 : 403 }));
  vi.stubGlobal("fetch", request);
  await expect(createOutlookDraft(report, results, [], root, "West", "token")).rejects.toThrow(removed ? "incomplete draft was removed" : "could not be removed");
  expect(request.mock.calls[2]![1].method).toBe("DELETE");
});

it("fails before creating a draft when a panel cannot be captured", async () => {
  const { report, results, root } = fixture(); root.querySelector("#askbi-panel-panel-2")!.remove();
  const request = vi.fn(); vi.stubGlobal("fetch", request);
  await expect(createOutlookDraft(report, results, [], root, "West", "token")).rejects.toThrow("Missing report panel");
  expect(request).not.toHaveBeenCalled();
});

it("rejects oversized complete attachments before creating a draft", async () => {
  const { report, results, root } = fixture(1); mocks.image = "data:image/png;base64," + "A".repeat(4_000_000);
  const request = vi.fn(); vi.stubGlobal("fetch", request);
  await expect(createOutlookDraft(report, results, [], root, "West", "token")).rejects.toThrow("exceeds");
  expect(request).not.toHaveBeenCalled();
});

it("offers a clear download fallback when image clipboard is unavailable", async () => {
  const { report, results, root } = fixture();
  await expect(copyReportImage(createReportSnapshot(report, results, [], root, "West", 10))).rejects.toThrow("Download images");
});

it("packages every numbered image in a stored ZIP directory", () => {
  const archive = zipReportFiles([{ name: "AskMe-report-1.png", bytes: new TextEncoder().encode("hello") }, { name: "AskMe-report-2.png", bytes: new Uint8Array([1, 2, 3]) }]);
  const view = new DataView(archive.buffer);
  expect(view.getUint32(0, true)).toBe(0x04034b50);
  expect(view.getUint32(14, true)).toBe(0x3610a686);
  const end = archive.length - 22;
  expect(view.getUint32(end, true)).toBe(0x06054b50);
  expect(view.getUint16(end + 10, true)).toBe(2);
  const central = view.getUint32(end + 16, true);
  expect(view.getUint32(central, true)).toBe(0x02014b50);
  expect(new TextDecoder().decode(archive)).toContain("AskMe-report-2.png");
});

it("rejects a nonempty but completely blank image", () => {
  const canvas = { width: 10, height: 10, getContext: () => ({ getImageData: () => ({ data: new Uint8ClampedArray(400).fill(255) }) }) } as unknown as HTMLCanvasElement;
  expect(() => assertReportCanvas(canvas)).toThrow("blank report image");
});
