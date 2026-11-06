import type { BiPlan, BiReport } from "@nql/shared-types";
import { createStandardPublicClientApplication, type IPublicClientApplication } from "@azure/msal-browser";
import { reportReady, type PanelResult } from "./use-askbi";
import { currentValue, isRevenueLift, liftScenario, regionalContributions, reportScopeSpec, LIFT_BASELINE_ID, LIFT_REGION_BASELINE_ID } from "./revenue-lift";

const html = (value: unknown) => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c);
const base64 = (url: string) => url.slice(url.indexOf(",") + 1);
const size = (content: string) => Math.floor(content.length * 0.75);

export function outlookConfigured() {
  return Boolean(process.env.NEXT_PUBLIC_ASK_ME_OUTLOOK_CLIENT_ID && process.env.NEXT_PUBLIC_ASK_ME_OUTLOOK_TENANT_ID);
}

let outlookAuth: IPublicClientApplication | null = null;
let outlookInitialization: Promise<IPublicClientApplication> | null = null;

export function prepareOutlookAuth(): Promise<IPublicClientApplication> {
  const clientId = process.env.NEXT_PUBLIC_ASK_ME_OUTLOOK_CLIENT_ID;
  const tenantId = process.env.NEXT_PUBLIC_ASK_ME_OUTLOOK_TENANT_ID;
  if (!clientId || !tenantId) return Promise.reject(new Error("Outlook needs a Microsoft Entra client and tenant ID."));
  if (!outlookInitialization) {
    outlookInitialization = createStandardPublicClientApplication({ auth: { clientId, authority: `https://login.microsoftonline.com/${tenantId}`, redirectUri: `${window.location.origin}/outlook-redirect` }, cache: { cacheLocation: "sessionStorage" } })
      .then(auth => { outlookAuth = auth; return auth; })
      .catch(error => { outlookInitialization = null; throw error; });
  }
  return outlookInitialization;
}

export function getOutlookToken(): Promise<string> {
  if (!outlookAuth) throw new Error("Outlook is still connecting. Try again in a moment.");
  const request = { scopes: ["Mail.ReadWrite"], redirectUri: `${window.location.origin}/outlook-redirect` };
  const accounts = outlookAuth.getAllAccounts();
  const account = accounts.length === 1 ? accounts[0] : null;
  // Invoke the popup synchronously from the button click; browsers can block
  // popups opened only after report saving, dynamic imports or PDF capture.
  return (account
    ? outlookAuth.acquireTokenPopup({ ...request, account })
    : outlookAuth.loginPopup({ ...request, prompt: "select_account" })
  ).then(result => result.accessToken);
}

export function buildOutlookBody(plan: BiPlan, results: Record<string, PanelResult>, briefing: string[], pictures: Array<{ title: string; cid: string; panelId?: string }>, reportUrl: string, scopeLabel = "Permitted regions", liftPercent = 10): string {
  const first = reportScopeSpec(plan);
  const scope = `${first?.dateFrom ?? ""} to ${first?.dateTo ?? ""} · ${plan.reportFilter?.make ?? "All makes"} · ${plan.reportFilter?.region ? `${plan.reportFilter.region} · ` : ""}${scopeLabel}`;
  const kpis = plan.panels.filter(panel => panel.kind === "kpi").slice(0, 3).map(panel => {
    const result = results[panel.id]?.result;
    const column = String(result?.meta.valueColumn ?? panel.spec.metrics[0]);
    const raw = result?.rows[0]?.[column];
    const value = typeof raw === "number" ? new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, ...(result?.meta.metricFormat === "currency" ? { style: "currency", currency: "INR" } : {}) }).format(raw) : "No data";
    return `<td style="padding:14px;border:1px solid #dad7ed"><small>${html(panel.title)}</small><br><strong style="font-size:22px">${html(value)}</strong></td>`;
  }).join("");
  const paragraphs = briefing.filter(text => !text.includes("unavailable")).slice(0, 2).map(text => `<p>${html(text)}</p>`).join("");
  const lift = isRevenueLift(plan) ? liftScenario(currentValue(plan, results, "leader-1"), currentValue(plan, results, LIFT_BASELINE_ID), liftPercent) : null;
  const scenario = lift ? `<p><strong>Revenue lift target:</strong> ${liftPercent}% above the prior aligned period. Actual lift: ${lift.actualLift.toFixed(1)}%. Target: ${html(new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(lift.target))}. ${lift.gap >= 0 ? "Above target" : "Shortfall to target"}: ${html(new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Math.abs(lift.gap)))}. This target is a scenario, not a forecast.</p>` : "";
  const images = pictures.slice(0, 3).map(item => {
    const drivers = isRevenueLift(plan) && item.panelId === "leader-4" ? regionalContributions(plan, results) : null;
    const panel = plan.panels.find(candidate => candidate.id === item.panelId || (!item.panelId && candidate.title === item.title));
    const result = panel ? results[panel.id]?.result : null;
    const dimension = panel?.spec.dimensions[0];
    const metric = String(result?.meta.valueColumn ?? panel?.spec.metrics[0] ?? "");
    const samples = result?.rows.slice(0, 3).map(row => {
      const raw = row[metric];
      const value = typeof raw === "number" ? new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, ...(result.meta.metricFormat === "currency" ? { style: "currency", currency: "INR" } : {}) }).format(raw) : String(raw ?? "No data");
      return `${String(dimension ? row[dimension] ?? "" : "")}: ${value}`;
    }).join("; ");
    const description = drivers ? `Observed regional revenue change: ${drivers.rows.slice(0, 3).map(row => `${row.name} ${row.delta >= 0 ? "+" : ""}${row.delta.toFixed(2)}`).join("; ")}. These changes do not prove causality.` : samples ? `Displayed values: ${samples}.` : "No matching rows.";
    return `<h3>${html(item.title)}</h3><p>${html(item.title)} for ${html(scope)}. ${html(description)} Open the attached report for the complete data and definitions.</p><img src="cid:${html(item.cid)}" alt="${html(item.title)} for ${html(scope)}" width="640" style="max-width:100%;height:auto">`;
  }).join("");
  return `<html><body style="font-family:Arial,sans-serif;color:#222"><h1>${html(plan.title)}</h1><p>Ask Me · Automotive · ${html(scope)}</p>${paragraphs}<table role="presentation" style="border-spacing:8px"><tr>${kpis}</tr></table>${scenario}${images}<p>The full report is attached as a PDF. <a href="${html(reportUrl)}">Open the saved report in Ask Me</a> to inspect governed definitions. Access requires the report owner's account and permitted scope.</p></body></html>`;
}

export async function createOutlookDraft(report: BiReport, results: Record<string, PanelResult>, briefing: string[], root: HTMLElement, scopeLabel: string, token: string, liftPercent = 10): Promise<string> {
  const plan = report.state.plan;
  if (!report.saved || !plan) throw new Error("Save the completed report before creating an Outlook draft.");
  if (!token) throw new Error("Outlook sign-in is required. Use the manual email draft until it is connected.");
  if (!reportReady(plan, results)) throw new Error("Wait for all current report panels before creating a draft.");
  const html2canvas = (await import("html2canvas")).default;
  const { jsPDF } = await import("jspdf");
  const attachments: Array<Record<string, unknown>> = [];
  const charts = plan.panels.filter(panel => panel.kind === "chart" && panel.id !== LIFT_REGION_BASELINE_ID).slice(0, 3);
  const pictures: Array<{ title: string; cid: string; panelId: string }> = [];
  const capture = (element: HTMLElement) => html2canvas(element, { scale: 1, backgroundColor: "#ffffff", foreignObjectRendering: true, ignoreElements: node => ["BUTTON", "SELECT", "DETAILS"].includes(node.tagName) });
  for (const panel of charts) {
    const element = [...root.querySelectorAll<HTMLElement>("[id^='askbi-panel-']")].find(node => node.id === `askbi-panel-${panel.id}`);
    if (!element) continue;
    const contentBytes = base64((await capture(element)).toDataURL("image/jpeg", 0.78));
    if (size(contentBytes) >= 2_800_000) throw new Error("A chart image is too large for an Outlook draft. Use the manual PDF export.");
    const cid = `askbi-chart-${pictures.length + 1}`;
    pictures.push({ title: isRevenueLift(plan) && panel.id === "leader-4" ? "Observed revenue change by region" : panel.title, cid, panelId: panel.id });
    attachments.push({ "@odata.type": "#microsoft.graph.fileAttachment", name: `${cid}.jpg`, contentType: "image/jpeg", contentBytes, contentId: cid, isInline: true });
  }
  const pdf = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
  const pageWidth = 273, pageHeight = 186;
  let cursor = 12;
  for (const block of root.querySelectorAll<HTMLElement>("[data-askbi-pdf]")) {
    const canvas = await capture(block);
    if (!canvas.width || !canvas.height) continue;
    const width = Math.min(pageWidth, pageHeight * canvas.width / canvas.height);
    const height = canvas.height * width / canvas.width;
    if (cursor + height > 198) { pdf.addPage(); cursor = 12; }
    pdf.addImage(canvas.toDataURL("image/jpeg", 0.78), "JPEG", 12, cursor, width, height);
    cursor += height + 5;
  }
  const pdfBytes = base64(pdf.output("datauristring"));
  if (size(pdfBytes) >= 2_800_000) throw new Error("The PDF is too large for this draft. Export and attach it manually.");
  attachments.push({ "@odata.type": "#microsoft.graph.fileAttachment", name: "AskBI-report.pdf", contentType: "application/pdf", contentBytes: pdfBytes, isInline: false });
  const reportUrl = `${window.location.origin}/analytics-builder?askbiReport=${encodeURIComponent(report.id)}${isRevenueLift(plan) ? `&lift=${liftPercent}` : ""}`;
  const body = buildOutlookBody(plan, results, briefing, pictures, reportUrl, scopeLabel, liftPercent);
  if (attachments.reduce((total, item) => total + size(String(item.contentBytes ?? "")), 0) >= 2_800_000) throw new Error("The report and images exceed Outlook's draft attachment limit. Export the PDF and use Manual email draft.");
  const response = await fetch("https://graph.microsoft.com/v1.0/me/messages", { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify({ subject: `Ask Me · ${plan.title}`, body: { contentType: "HTML", content: body }, attachments }) });
  if (!response.ok) throw new Error(`Outlook did not create the draft (${response.status}). Check consent and attachment size.`);
  const draft = await response.json() as { webLink?: string };
  return draft.webLink || "https://outlook.office.com/mail/";
}
