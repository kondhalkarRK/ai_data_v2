# Copilot task: diagnose why Analytics Builder still shows the old UI

Run this audit on the office laptop where Ask Me is actually running.
This is a read-only diagnosis. Do not edit source or environment files, install
packages, delete build output, restart services, apply migrations or change flags.
Do not test live PostgreSQL or LLM connectivity. Do not print secrets or complete
environment files. Return a concise, evidence-backed report and an exact proposed
fix; wait for approval before applying it.

## Problem

The user expects the unified automotive Analytics Builder with **Ask Analytics**,
**Save workspace** and one canvas. The browser instead shows the legacy Auto/Custom
toggle and/or AskWiz. Migration 0013 and feature flags were reportedly configured.
Find which source, configuration or running-build condition is selecting the old UI.
Do not assume the reported configuration reached the frontend process.

## Expected implementation

Start at the actual workspace directory, normally:
`E:\ai_data_rag\ai_data_v2\askdb`.
Read applicable AGENTS.md instructions. Inspect actual code before drawing conclusions.

The expected route chain is:

1. `apps/web/app/(workspace)/analytics-builder/page.tsx`
   renders `BuilderModes` after loading the semantic pack.
2. `apps/web/components/analytics-builder/builder-modes.tsx`
   checks active industry and `NEXT_PUBLIC_ASK_ME_ANALYTICS_WORKSPACE_ENABLED`.
3. Automotive + unified flag true renders `AnalyticsWorkspace` before evaluating
   the legacy AskWiz flag.
4. `apps/web/components/analytics-builder/analytics-workspace.tsx`
   renders Ask Analytics, Save workspace, variable panels and the field editor.

Expected conditions:

- Active industry is exactly `automotive`.
- `NEXT_PUBLIC_ASK_ME_ANALYTICS_WORKSPACE_ENABLED` resolves to `true` when Next.js
  evaluates its configuration/build. Production public flags are baked into the
  client bundle; changing an API environment variable cannot update an old bundle.
- `apps/web/next.config.ts` contains the unified flag mapping, with the public
  variable taking precedence over `ASK_ME_ANALYTICS_WORKSPACE_ENABLED` and a false
  fallback. Verify this in the office copy rather than assuming it exists.
- Backend `ASK_ME_ANALYTICS_WORKSPACE_ENABLED=true` enables the new API routes.
  This backend flag alone does not prove the browser received the new UI.
- `ASK_ME_ASKWIZ_ENABLED=true` does not override the unified frontend branch.
  Disabling AskWiz alone selects the old Custom Builder, not the unified workspace.
- Migration 0013 concerns persistence. It does not select the frontend page.

## Audit steps

### 1. Establish the exact checkout

Record the absolute working directory and repository root. If Git is available,
record branch, HEAD SHA, last commit date and a compact working-tree status.
Do not reset, checkout, pull or overwrite anything.

Confirm these files exist and inspect their relevant sections:

- `apps/web/components/analytics-builder/analytics-workspace.tsx`
- `apps/web/components/analytics-builder/builder-modes.tsx`
- `apps/web/next.config.ts`
- `apps/api/app/schemas/analytics_workspace.py`
- `apps/api/app/services/analytics/workspace.py`
- `apps/api/app/api/routes/analytics.py`
- `apps/api/migrations/versions/0013_analytics_workspaces.py`
- `docs/UNIFIED_ANALYTICS_BUILDER_IMPLEMENTATION.md`

Use targeted searches for `AnalyticsWorkspace`, `WORKSPACE_ENABLED`, `BuilderModes`
and `/analytics-builder`. Check whether another route or duplicate checkout is
being launched. A copied migration without the frontend source is not a complete
transfer. Cite file paths and line numbers for the actual component-selection logic.

### 2. Trace environment loading without exposing secrets

Inspect only these allowlisted variables:

```text
ASK_ME_ANALYTICS_WORKSPACE_ENABLED
NEXT_PUBLIC_ASK_ME_ANALYTICS_WORKSPACE_ENABLED
ASK_ME_ASKWIZ_ENABLED
NEXT_PUBLIC_ASK_ME_ASKWIZ_ENABLED
NODE_ENV
ASKDB_ENV_FILE
```

Check the repository-root `.env` files, `apps/web/.env*`, `apps/api/.env*`, and the
current terminal environment. Report only the allowlisted assignments, source
file and line number. Do not print API keys, passwords, URLs with credentials,
cookies or unrelated process environment variables.

Inspect `scripts/dev.ps1`, package scripts, VS Code launch/tasks configuration and
any deployment/start scripts actually used. Establish the web process working
directory and whether the launcher exports variables before starting Next.js.
Check whether a shell/process variable overrides a dotenv file, and whether a public
flag explicitly set to false overrides a backend-named flag set to true.

Use the installed Next.js version/documentation and its actual environment loader
to verify precedence. If useful, a short read-only Node command from `apps/web` can
call the installed `@next/env` loader and print ONLY the two unified flags after
loading the correct development/production mode. This shows what a NEW process
would load; it does not prove the already running process used those values.

Distinguish `.env.example` from active configuration. Do not assume the repository
root `.env` is automatically loaded by a web process whose project root is apps/web.

### 3. Identify the server serving the browser

Record the exact browser URL, including hostname, port and path. If it is unknown,
ask the user for that URL while continuing the filesystem checks.

Use read-only process/listening-port inspection appropriate to Windows. Match the
browser's port to its PID and parent launcher. Determine whether it is `next dev`,
`next start`, Docker, a proxy or a remote deployment. Inspect relevant command lines
without printing secrets. Do not terminate any process.

Check for multiple frontend processes, another checkout directory, port fallback
(for example 3000 versus 3001), an old production server, or a proxy pointing to a
different frontend. Report uncertainty if process working directory cannot be
established; do not infer it from the terminal currently open in VS Code.

### 4. Inspect build identity and freshness

For the web directory actually served, inspect the existence/timestamps of
`.next/BUILD_ID`, relevant manifests and static chunks. Do not delete or rebuild.

Use targeted searches in emitted client chunks for:

- `Ask Analytics`
- `Save workspace`
- `Automotive analysis`
- `Auto · AskWiz`
- `NEXT_PUBLIC_ASK_ME_ANALYTICS_WORKSPACE_ENABLED`

Public environment variable names may disappear after compilation. Their absence
is not proof of a missing flag. Legacy strings may coexist in a valid bundle due
to rollback support; their presence alone does not prove the old UI is selected.
Compare source modification times with the build and determine whether production
was rebuilt AFTER the flag/source change.

If browser inspection is available, compare the JavaScript chunk URLs actually
loaded by the page with the build being inspected. Confirm the active industry
through the visible selector or existing session/UI state; do not expose session
tokens. Check console errors and failed frontend resources. Do not change the
default industry or user preferences during this read-only audit.

### 5. Establish the selecting condition

Answer with direct evidence:

1. Does the office checkout contain the new component and route wiring?
2. What unified flag would a new web process load, and from which source?
3. Is the active industry automotive?
4. Which frontend PID/deployment serves the browser URL?
5. Does that process/build predate the new source or flag configuration?
6. Does the browser load assets from that same build?
7. What precise condition explains the old UI, and which possibilities remain
   unverified?

Do not blame the database, migration or LLM for a legacy component being selected
without evidence connecting that dependency to the selection logic.

## Required report

Return Markdown in this format, keeping it concise:

```markdown
## Finding
Confirmed root cause, or the narrowest supported explanation.

## Evidence
- Checkout/root/branch/SHA and relevant file references.
- Actual route/component-selection condition.
- Allowlisted flag values and their sources/precedence.
- Browser URL, frontend PID/start mode and build identity/freshness.
- Active industry and browser asset findings, if inspected.

## Proposed fix
Exact files/allowlisted settings and commands needed for THIS setup.
Specify whether a web restart, production rebuild, correct port/checkout, or
source transfer is required. Do not apply these changes yet.

## Verification after the fix
Expected screen: Ask Analytics + Save workspace, no Auto/Custom toggle.
State how to confirm automotive scope and the correct running build.

## Unknowns
Only facts that could not be verified and the single next check needed for each.
```

If possible, save the report as `docs/ANALYTICS_BUILDER_OFFICE_AUDIT_REPORT.md`
only after the user authorizes writing the report. Otherwise paste it into chat.
The user can share that report back here; it must contain no secrets.
