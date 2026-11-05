# AskBI leadership reports — demo plan

Implemented locally on 2026-11-06 for automotive: four exact starter prompts,
server-owned six-panel definitions, aligned report sections, and browser PDF
export. The adjacent HTML file remains a visual concept with illustrative
numbers; it never calls an API. The undated “total sales by region” fast path
is implemented separately. Outlook delivery with an attached PDF is still open.

## Why these four prompts

Research direction: [ThoughtSpot SpotterViz](https://www.thoughtspot.com/product/agents/spotterviz)
emphasizes governed KPIs, story structure and conversational refinement;
[Microsoft's dashboard guidance](https://learn.microsoft.com/en-us/power-bi/create-reports/service-dashboards-design-tips)
recommends a clear hierarchy, one-screen executive overview and consistent
time scope; [BMW's Tableau case](https://www.tableau.com/solutions/customer/tableau-enables-bmw-group-germany-improve-performance)
shows the value of executive, regional and dealer views. We adopt those layout
ideas with Ask Me's existing automotive measures. No agent integration is needed.

| Audience and starter question | Two KPI cards | Four charts (six query panels total) | Leadership decision |
| --- | --- | --- | --- |
| CFO: “Create a weekly sales and revenue briefing for the CFO” (also monthly) | Revenue, weighted average selling price | Revenue trend; revenue by region; units by vehicle make; revenue by dealer | Where did sales value move, and which segments deserve review? |
| CEO: “Show me the monthly business pulse: growth, mix and geography” | Revenue, units sold | Revenue trend; revenue by region; units by make; units by model | Which markets and products shape the period? |
| Regional leader: “Show this month's region and dealer performance” | Revenue, units sold | Revenue by region; revenue by dealer; units by model; revenue trend | Which dealers or models warrant a closer look within allowed regions? |
| Sales director: “Build a weekly sales team and dealer report” | Units sold, active salespeople | Units by salesperson; revenue by dealer; units by model; daily units trend | Where is sales activity concentrated? |

Each prompt has an explicit period picker: last completed week/month by default;
the week/month choice is visible before generation. The language of the question
should not promise *growth*, *quota attainment*, *profit*, *margin*, *conversion*,
or *productivity* unless the needed comparison/denominator exists and is shown.
For example, the CEO card's “growth” is an investigation theme, not a displayed
growth percentage until an aligned previous period is queried. A regional
leader sees only permitted scope, and dealer/salesperson output observes access
controls and any minimum aggregation policy that applies.

## Visual layout

Use one report page: audience/title + visible date/scope → one or two lines of
fact-based briefing → two KPI cards → a wide trend → a pair of ranked breakdowns
→ one final focused chart. Keep the report canvas wider than the conversation
sidebar; collapse the sidebar into the existing drawer for tablet and PDF.
Use consistent metric colors, axes, units, truncation disclosures and evidence
links. Different presets can change content and wording while preserving this
system. A report should retain chart editing, drill/data inspection and Undo.

The existing six-panel cap means **two KPI cards plus four charts** is the
highest-coverage preset without a schema change. If a third KPI is more useful,
ship three KPI cards and three charts. Never promise four charts plus three cards
under the current cap. Narration can explain supported movements and say when
comparison, target or coverage evidence is missing. Avoid invented causes.

## Implemented path and follow-up

1. Four exact strings now produce server-owned automotive plans with two KPIs
   and four charts. The catalog validates all panels; unknown qualifiers still
   go to normal interpretation. The starter cards fill the AskBI composer; Send
   invokes the same turn API. Weeks are last completed weeks, months last completed
   months. Each panel remains independently loaded and editable.
2. The report canvas groups KPIs, trend and ranked breakdowns. Existing evidence
   narration follows available data and cannot invent a comparison badge.
   Responsive alignment has been changed for these sections. No new layout schema
   or client-authored metrics were added.
3. “Export PDF” invokes the browser print dialog after every panel has current
   data. Users choose **Save as PDF**. Print CSS shows the report and hides app
   chrome and editing controls. Browser/PDF output with real data still needs
   visual QA on the office environment.
4. “Email draft” opens the system's default mail app with a subject and period,
   instructing the sender to attach the exported PDF and check recipients. It
   does **not** attach or send automatically and may open a mail client other than
   Outlook. Authenticated Outlook delivery requires a separate Microsoft Graph
   connection and delegated `Mail.Send` permission; see
   [Microsoft Graph sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0).
   This is an explicit remaining integration task, not a silent email claim.
5. Verify each preset against real office data with 6 bounded panel queries,
   owner/region access, partial and empty periods, rapid edits, tablet layout
   and a multi-page PDF. Measure latency rather than claiming demo targets.

## Immediate defect handled

“Total sales by region” previously missed the exact fast path because no period
was supplied, then depended on an LLM response. The new narrow template uses
the last completed calendar month and states that assumption in both the answer
and report. It does not absorb unknown filters or qualifiers. A more informative
empty-provider message remains an optional follow-up; provider configuration
still matters for novel questions and narration.
