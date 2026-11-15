import type { BiPlan, BiReport } from "@nql/shared-types";
import { createStandardPublicClientApplication, type IPublicClientApplication } from "@azure/msal-browser";
import { type PanelResult } from "./use-askbi";
import { currentValue, isRevenueLift, liftScenario, regionalContributions, reportScopeSpec, LIFT_BASELINE_ID } from "./revenue-lift";

import { formatReportValue } from "./report-format";
import { captureReport, createReportSnapshot, type ReportSnapshot } from "./report-export";

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

export function buildOutlookBody(plan: BiPlan, results: Record<string, PanelResult>, briefing: string[], pictures: Array<{ title: string; cid: string; panelId?: string }>, reportUrl: string, scopeLabel = "Permitted regions", liftPercent = 10, question = ""): string {
  const first = reportScopeSpec(plan);
  const scope = `${first?.dateFrom ?? ""} to ${first?.dateTo ?? ""} · ${plan.reportFilter?.make ?? "All makes"} · ${plan.reportFilter?.region ? `${plan.reportFilter.region} · ` : ""}${scopeLabel}`;
  const kpis = plan.panels.filter(panel => panel.kind === "kpi").map(panel => {
    const result = results[panel.id]?.result;
    const column = String(result?.meta.valueColumn ?? panel.spec.metrics[0]);
    const raw = result?.rows[0]?.[column];
    return `<tr><td style="padding:12px;border-bottom:1px solid #dde3ed">${html(panel.title)}</td><td style="padding:12px;border-bottom:1px solid #dde3ed;font-size:22px;font-weight:bold">${html(result?.rows.length ? formatReportValue(raw, result.meta.metricFormat) : "No data")}<br><small style="font-size:11px;color:#526176">${html(formatReportValue(raw, result?.meta.metricFormat, false))}</small></td></tr>`;
  }).join("");
  const paragraphs = briefing.map(text => `<p>${html(text)}</p>`).join("");
  const lift = isRevenueLift(plan) ? liftScenario(currentValue(plan, results, "leader-1"), currentValue(plan, results, LIFT_BASELINE_ID), liftPercent) : null;
  const money = (value: number) => formatReportValue(value, "currency");
  const scenario = lift ? `<h2>Revenue lift scenario</h2><p>Target: ${liftPercent}% above the prior aligned period. Actual lift: ${lift.actualLift.toFixed(1)}%. Actual: ${html(money(lift.current))}. Prior: ${html(money(lift.baseline))}. Target revenue: ${html(money(lift.target))}. ${lift.gap >= 0 ? "Above target" : "Shortfall to target"}: ${html(money(Math.abs(lift.gap)))}. This target is a scenario, not a forecast.</p>` : "";
  const images = pictures.map(item => {
    const drivers = isRevenueLift(plan) && item.panelId === "leader-4" ? regionalContributions(plan, results) : null;
    const panel = plan.panels.find(candidate => candidate.id === item.panelId || (!item.panelId && candidate.title === item.title));
    const result = panel ? results[panel.id]?.result : null;
    const details = drivers ? `<p>Observed regional changes: ${drivers.rows.map(row => `${html(row.name)}: ${html(money(row.delta))}`).join("; ")}. These changes do not prove causality.</p>` : result?.insights?.executive ? `<p>${html(result.insights.executive)}</p>` : "";
    const columns = result?.columns ?? [];
    const valueColumn = String(result?.meta.valueColumn ?? panel?.spec.metrics[0] ?? "");
    const comparison = drivers ? `<table width="100%" style="border-collapse:collapse;font-size:12px"><caption style="text-align:left">Regional comparison</caption><tr><th>Region</th><th>Prior revenue</th><th>Current revenue</th><th>Change</th></tr>${drivers.rows.map(row => `<tr><td style="padding:6px">${html(row.name)}</td><td style="padding:6px">${row.name === "Other / reconciliation" ? "—" : html(money(row.prior))}</td><td style="padding:6px">${row.name === "Other / reconciliation" ? "—" : html(money(row.current))}</td><td style="padding:6px">${html(money(row.delta))}</td></tr>`).join("")}</table>` : "";
    const values = result?.rows.length ? `<table width="100%" style="border-collapse:collapse;font-size:12px"><caption style="text-align:left">Returned values</caption><tr>${columns.map(column => `<th style="padding:6px;text-align:left;border-bottom:1px solid #dde3ed">${html(column)}</th>`).join("")}</tr>${result.rows.map(row => `<tr>${columns.map(column => `<td style="padding:6px;border-bottom:1px solid #edf1f6" title="${html(formatReportValue(row[column], column === valueColumn ? result.meta.metricFormat : undefined, false))}">${html(formatReportValue(row[column], column === valueColumn ? result.meta.metricFormat : undefined))}</td>`).join("")}</tr>`).join("")}</table>` : "";
    return `<tr><td style="padding:18px 0;border-top:1px solid #dde3ed"><h2 style="font-size:18px">${html(item.title)}</h2>${details}<img src="cid:${html(item.cid)}" alt="${html(item.title)} for ${html(scope)}" width="680" style="display:block;border:0;width:100%;max-width:680px;height:auto">${comparison}${values}</td></tr>`;
  }).join("");
  const definitions = plan.panels.map(panel => {
    const result = results[panel.id]?.result;
    const notes = [...(result?.meta.notes ?? []), ...(result?.meta.warnings ?? [])];
    return `<p><strong>${html(panel.title)}:</strong> ${html(panel.rationale)}. Period: ${html(panel.spec.dateFrom)} to ${html(panel.spec.dateTo)}. Data as of: ${html(result?.meta.dataAsOf ?? "Unknown")}.${notes.map(note => ` ${html(note)}`).join("")}</p>`;
  }).join("");
  return `<html><body style="margin:0;padding:20px;font-family:Arial,sans-serif;color:#1c273b;background:#fff"><table role="presentation" width="100%" style="max-width:720px;border-collapse:collapse"><tr><td><p>AskMe · Automotive</p><h1 style="font-size:26px">${html(plan.title)}</h1>${question ? `<p><strong>Your question:</strong> ${html(question)}</p>` : ""}<p>${html(scope)}</p>${paragraphs}<table role="presentation" width="100%" style="border-collapse:collapse">${kpis}</table>${scenario}</td></tr>${images}<tr><td><h2 style="font-size:18px">Assumptions and definitions</h2>${plan.assumptions.map(text => `<p>${html(text)}</p>`).join("")}${definitions}<p>The complete report is attached as a PDF. <a href="${html(reportUrl)}">Open the saved report in AskMe</a>. This link requires the report owner's account and permitted scope; emailing it does not grant access.</p></td></tr></table></body></html>`;
}

export async function createOutlookDraft(report: BiReport, results: Record<string, PanelResult>, briefing: string[], root: HTMLElement, scopeLabel: string, token: string, liftPercent = 10, existingSnapshot?: ReportSnapshot): Promise<string> {
  if (!report.saved || !report.state.plan) throw new Error("Save the completed report before creating an Outlook draft.");
  if (!token) throw new Error("Outlook sign-in is required.");
  const snapshot = existingSnapshot ?? createReportSnapshot(report, results, briefing, root, scopeLabel, liftPercent);
  if (snapshot.report.id !== report.id || JSON.stringify(snapshot.report.state.plan) !== JSON.stringify(report.state.plan)) throw new Error("The report changed while saving. Please export again.");
  const plan = snapshot.report.state.plan!;
  const captured = await captureReport(snapshot);
  const pictures = captured.pictures.map((item, i) => ({ ...item, cid: `askbi-chart-${i + 1}` }));
  const attachments: Array<Record<string, unknown>> = pictures.map(item => ({ "@odata.type": "#microsoft.graph.fileAttachment", name: `${item.cid}.png`, contentType: "image/png", contentBytes: base64(item.dataUrl), contentId: item.cid, isInline: true }));
  attachments.push({ "@odata.type": "#microsoft.graph.fileAttachment", name: "AskBI-report.pdf", contentType: "application/pdf", contentBytes: base64(captured.pdfDataUrl), isInline: false });
  if (attachments.some(item => size(String(item.contentBytes)) >= 2_800_000)) throw new Error("A complete report attachment exceeds the supported inline upload size. Export PDF/download images and attach manually; no draft was created.");
  const reportUrl = `${window.location.origin}/analytics-builder?askbiReport=${encodeURIComponent(report.id)}${isRevenueLift(plan) ? `&lift=${snapshot.liftPercent}` : ""}`;
  const question = snapshot.report.state.turns.find(turn => turn.question)?.question ?? "";
  const body = buildOutlookBody(plan, snapshot.results, snapshot.briefing, pictures, reportUrl, snapshot.scopeLabel, snapshot.liftPercent, question);
  const payload = JSON.stringify({ subject: `AskMe · ${plan.title}`, body: { contentType: "HTML", content: body } });
  if (new TextEncoder().encode(payload).length >= 2_800_000) throw new Error("The complete email body is too large. Use the PDF export; no draft was created.");
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  let response: Response;
  try { response = await fetch("https://graph.microsoft.com/v1.0/me/messages", { method: "POST", headers, body: payload }); }
  catch { throw new Error("Outlook draft creation could not be confirmed. Check Drafts before retrying; no email was sent."); }
  if (!response.ok) throw new Error(`Outlook draft creation failed (${response.status}). No successful draft was confirmed.`);
  let draft: { id?: string; webLink?: string };
  try { draft = await response.json(); }
  catch { throw new Error("Outlook returned an unreadable draft response. Check Drafts before retrying; no email was sent."); }
  if (!draft.id) throw new Error("Outlook did not return a draft ID. Check Drafts before retrying; creation could not be confirmed.");
  const draftUrl = `https://graph.microsoft.com/v1.0/me/messages/${encodeURIComponent(draft.id)}`;
  try {
    for (const attachment of attachments) {
      const upload = await fetch(`${draftUrl}/attachments`, { method: "POST", headers, body: JSON.stringify(attachment) });
      if (!upload.ok) throw new Error(`Attachment upload failed (${upload.status}).`);
    }
  } catch (cause) {
    let removed = false;
    try { removed = (await fetch(draftUrl, { method: "DELETE", headers })).ok; } catch { /* Surface uncertain cleanup below. */ }
    throw new Error(`${cause instanceof Error ? cause.message : "Attachment upload failed."} ${removed ? "The incomplete draft was removed." : "The incomplete draft could not be removed. Delete it in Outlook Drafts before retrying."}`);
  }
  return draft.webLink || "https://outlook.office.com/mail/";
}
