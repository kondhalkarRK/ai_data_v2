# AskBI report studio — implementation record

Updated 2026-11-06. Automotive only; Custom Report, Executive Intelligence,
insurance and general AI Chat retain their existing paths.

## Server-owned starter reports

The six exact cards fill the AskBI composer. Send uses a validated predefined
plan, with no interpretation call. Each plan has two approved KPI cards and four
charts; novel questions and bounded evidence narration can use the existing LLM.
All panel queries remain governed and independently loaded.

- **Sales Report for CEO:** revenue, units, revenue trend, regional revenue,
  make mix and leading models.
- **Financial Sales Briefing for CFO:** revenue, weighted ASP, revenue trend,
  ASP by make, regional revenue concentration and dealer revenue. It does not
  present unsupported margin, profit or budget metrics.
- **Region & Dealer Performance:** revenue, units, region ranking, dealer units,
  revenue trend and a region/model mix heatmap. Dealer analysis is limited to
  the signed-in user's permitted region scope.
- **Sales Team Performance:** units, active salespeople, units trend,
  salesperson ranking, dealer orders and model units. It avoids an undefined
  productivity ratio.
- **Make & Model Comparison:** units, weighted ASP, make and model rankings,
  ASP by model and revenue trend. Make selection narrows this comparison and
  the UI says so.
- **Sales Momentum & Emerging Models:** revenue, orders, revenue and units
  trends, leading models and make revenue. The generated title says “Model
  Leaders”; it does not claim an emerging model without aligned comparisons.

The first period is the last completed calendar month or Monday–Sunday week,
visible in the title area and assumptions. After generation, a year, month,
week and make bar applies one server-validated scope to every panel. Make values
come from scoped automotive sales; the region/dealer report also
offers a zone-filtered region selector for dealer and model investigation.
Filter turns do not call an LLM.
Saved reports and Undo preserve the selection; Refresh recalculates relative
periods while explicit filter dates stay fixed. Prior values remain marked as
previous while new data loads, and failed/empty panels keep their own states.

## Presentation and export

The report has an on-canvas title, dates, make and permission reminder, a short
evidence briefing, KPI row, prominent chart and grouped supporting charts.
Existing chart editing, evidence inspection, conversations and Undo remain.
Browser Export PDF is enabled only when all current panels finish; its print CSS
hides editing controls and avoids splitting chart containers.

With an Entra SPA connection configured, **Create Outlook draft** saves the
report, captures up to three current charts as inline images, includes two or
three KPI values and a short briefing in simple HTML, generates a full PDF and
uses delegated `Mail.ReadWrite` to create an unsent Microsoft Graph draft. The
report link requires owner access. **Manual email draft** remains for a mailto
handoff; the user attaches the exported PDF there. No message is sent by AskBI.

## Checks and remaining acceptance

Offline semantic/compiler tests cover all six plans, filter consistency,
Monday–Sunday dates, scoped values, and strict qualifiers. Focused frontend
tests cover all six cards, filter submission, stale-response hook behavior and
HTML email values/escaping. The office environment still needs real automotive
data, real Outlook tenant consent, browser/tablet and printed PDF inspection,
desktop/web Outlook image rendering, attachments and regional permission review.
Local PostgreSQL, LLM and Graph verification were unavailable and were not
claimed. The two public Entra IDs must be configured in `apps/web/.env.local`;
see `ASKBI_IMPLEMENTATION.md`.
