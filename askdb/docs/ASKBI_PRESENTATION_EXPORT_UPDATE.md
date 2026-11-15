# Auto Report presentation and export update

Implemented 15 November 2026. This is implementation documentation, not a claim
of live Outlook acceptance.

## Changes

- Shared presentation formatting uses Indian grouping, ₹ lakh/crore for currency,
  ordinary counts and percentage units. Zero, negatives, missing and nonfinite
  values are distinct. Inspect data and CSV retain returned precision; formulas
  and SQL do not use rounded display values.
- All existing starter reports use the shared canvas: CEO, CFO, Region & Dealer,
  Sales Team, Make & Model, and Revenue Lift. There are six current starters.
  Desktop charts form two equal columns with no hero or odd-card expansion.
  Mobile stacks cards. Dense multidimensional tables may span both columns.
- Restrained gradients and deterministic category colors preserve labels across
  filtering. Positive/negative regional changes retain their semantic colors.
- Outlook captures a synchronous, isolated snapshot of the report revision,
  plan/filter, returned results, briefing, scope and scenario settings. Animated
  KPI values settle before capture. Controls and animations are excluded, and
  scrollable report tables expand for capture. UI controls lock during export.
  Stale, loading or missing panel results block export.
- The snapshot supplies the complete HTML email, ordered CID PNG chart attachments
  and PDF attachment. No analytical or narration requests are made for capture.
  Saving an unsaved report still uses the existing save operation.
- Graph creates an unsent draft using delegated Mail.ReadWrite; no recipients or
  send endpoint are supplied. A failed attachment upload triggers deletion of
  the incomplete draft. Cleanup failure and uncertain creation are disclosed.
  Report links remain owner-scoped; an email does not grant application access.
- Copy report image uses the PNG clipboard API where supported. It copies a
  picture, not editable text. Long reports download numbered PNG pages in one ZIP;
  all images must be inserted in order. HTML draft text/tables remain editable.
- Capture uses a light export palette without changing the user's selected theme.
  Modern CSS colors are resolved before canvas rendering. Blank captures fail
  explicitly rather than creating empty attachments.

## Verification

- Full frontend suite: 32 files, 194 tests passed.
- AskBI backend suite: 42 cases passed, including governed starter plans,
  arithmetic, stale results, ownership and scope behavior; synthetic dependencies.
- Frontend typecheck and production webpack build passed.
- AskBI-specific lint passed. Older shared result-chart code still has three
  existing React lint errors (two effect state updates and pie angle mutation).
- Chrome fixture verification covers 1440, 820 and 390 widths, Light/Dark/AI
  themes, reduced motion, desktop pairing, visual-only query reuse, scenarios,
  print theme restoration, nonblank downloaded PNG pages and no page errors.
  Actual image labels were visually inspected after capture fixes.
- Fixture tests exercise all chart attachments, complete briefing, frozen values,
  stale rejection, upload failure/cleanup, size rejection and clipboard fallback.

## Compatibility limits and office acceptance

No live warehouse, LLM, Microsoft sign-in, Graph mailbox or real Outlook client was
used during these checks. Fixture tests are not Classic/New/Web Outlook acceptance.

1. Run each of the six starters with real permitted office data. Compare KPI,
   count/percentage/currency units, chart order, filter labels and Inspect data.
   Include zero, negative, empty, missing prior-period and stale-result cases.
2. Change date/make/region, then export after the results settle. Verify the email,
   all PNGs and attached PDF agree. Change Revenue Lift to 20% and confirm its
   target and reconciled regional comparison agree across exports.
3. Sign in using the existing Microsoft Entra Outlook configuration and create a
   draft. Review it in Classic, New and Web Outlook: all CID images, editable
   tables, ₹ glyphs, line wrapping, all briefing paragraphs and PDF readability.
   Check mobile Outlook and paste from the image clipboard separately.
4. Confirm another account cannot open the owner-scoped report link. Email/PDF
   attachments contain the permitted exported data; recipients must be approved.
5. Confirm blocked clipboard permissions give the download fallback. Long reports
   produce a ZIP rather than silently copying only their first image.

Each attachment and the HTML request have a conservative 2.8 MB preflight limit.
Larger attachments do not use Graph upload sessions in this implementation:
export PDF/download images and attach manually. Tenant aggregate message limits
can also reject uploads; incomplete drafts are cleaned up where possible.
An image section taller than 3000 output pixels fails with PDF guidance. Very
dense tables can be scaled in the PDF; verify readability and use raw CSV when
exact machine-readable rows are needed. Raster charts are intentionally not
editable Outlook charts. Clipboard availability depends on browser, HTTPS and
enterprise permissions. No automatic sending or external image hosting was added.

## Main implementation files

`apps/web/components/analytics-builder/askbi/`: `report-format.ts`,
`report-export.ts`, `report-zip.ts`, `outlook-draft.ts`, `report-canvas.tsx`,
`report-panel.tsx`, `regional-contributions.tsx`, `askbi.tsx`.
Shared optional chart formatting is in `components/chat/result-chart.tsx`;
report styles are in `app/globals.css`.

Repeat local fixture verification with the frontend running and
`ASKBI_BASE_URL=http://localhost:YOUR_PORT`:
`node scripts/verify-askbi-presentation.mjs`.
Artifacts are written under `tmp/askbi-presentation/`.
