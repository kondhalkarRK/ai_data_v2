# Soci branding and Chat update

Implemented in AskDB on 2026-11-23. No Agentic project files were inspected, imported, or changed for this update.

## What changed

- The product name is **Soci** on Home, navigation, metadata, Chat, active public help guides, report canvases, report downloads and Outlook draft content. The existing brain mark, blue/teal wordmark treatment, tagline and three themes remain. Technical environment variables, API routes, package names, database names, old migration identifiers and the stored Chat-mode key remain compatible. Historical planning documents retain their original titles where they describe past work.
- Classic and New Chat now share one conversation controller, draft and source selections. Their empty state greets the currently authenticated profile's first name, with **Hi there.** for a blank or missing name. No demo name is hardcoded. Changing accounts or access scope resets the visible conversation.
- An empty conversation centers the greeting and composer. After a message, the composer sits below the scrolling conversation. New Chat uses up to 1,200px of the available canvas; prose retains a readable line length and wide tables scroll inside their card.
- The composer keeps report navigation, Unstructured data and Web retrieval in one wrapping row. **Generate report** opens the existing Analytics Builder; it does not add a new report-generation Chat mode. The existing document capability disables document selection where unavailable. Both Chat layouts now submit the same document/web options through the existing Chat endpoint.
- New Chat has a hidden-by-default right-side history drawer using the same Radix dialog pattern as existing dashboard drawers. It shows only the current user's conversations in the active industry. Opening/closing it preserves the draft; selecting a conversation restores its saved response content and ratings without asking the model or rerunning SQL.
- Completed assistant responses have a compact information action and thumbs-up/down. Up saves immediately. Down opens an optional reason/note form. Ratings can be changed or removed; failed saves restore the previous state and show an error.

## Persistence and permissions

The existing **query_history.id** is the stable response ID. The live stage/done events already carry it; restored messages reuse it. The browser's temporary message key is not used as a feedback identity.

The migration adds a nullable response_snapshot to query_history and a chat_ratings table. One canonical response snapshot enables history replay; feedback rows contain only user/response references, rating, reason, optional note, timestamps and optional server-owned report references. Feedback does not copy questions, SQL or result rows. At most one rating per user/response is enforced by a composite primary key and atomic upsert.

New response/history/rating APIs enforce owner and industry, including for administrators. Saved answers also carry the server's role/regional scope. A changed scope prevents replay of the old answer. Document-backed answers recheck current document permissions and the document feature gate before replay or feedback access. Linked reports recheck ownership and scope. Clients cannot provide another user ID or report ID in a rating request. Feedback has no analytics-connection or model dependency.

Current AskDB Chat does not generate AskBI report responses itself. Nullable report references support a trusted response-to-report association when applicable; no Agentic run ID or fabricated report association is introduced. The query-history ID remains the query/run reference.

Older query-history rows keep their existing IDs. Their answer text/results were not previously persisted, so the history drawer shows an explicit missing-content message rather than inventing an answer or automatically rerunning the question. New responses have replayable snapshots. History is bounded to the 200 most recently updated conversations and the 200 most recent turns per conversation, with an explicit limit notice.

Only the selected conversation ID is stored in tab storage, under the authenticated user's ID and industry. Tokens stay in the existing HttpOnly-cookie authentication flow. Drafts remain in the shared in-memory controller; they survive layout switches and opening/closing history, but unsent drafts are not persisted across a full page reload.

## Apply the application migration

The migration was generated and checked as PostgreSQL SQL; it has **not** been applied to your configured application database. No analytics database, data seed or new database is required.

Run once in PowerShell before starting the updated API:

```powershell
cd "E:\ai_data_rag\ai_data_v2\askdb\apps\api"
.\.venv\Scripts\python.exe -m alembic -x target=app upgrade head
```

Calling the environment's Python directly means activation is optional. Keep the existing .env and credentials. No new dependencies or secret keys were added.

Restart the API in one terminal:

```powershell
cd "E:\ai_data_rag\ai_data_v2\askdb\apps\api"
.\.venv\Scripts\python.exe run_dev.py
```

Restart the frontend in another:

```powershell
cd "E:\ai_data_rag\ai_data_v2\askdb"
npm.cmd run dev
```

The existing ASK_ME_NEW_CHAT_UI_ENABLED / NEXT_PUBLIC_ASK_ME_NEW_CHAT_UI_ENABLED gate still controls whether the Classic/New switch is available. If already enabled, no flag change is needed. Rebuild/restart the frontend after changing a public flag.

## Validation

- **15 new backend checks passed** using an isolated SQLite application database. Covered editable ratings, removal, one-row uniqueness, validation limits, ownership, industry changes, changed regional scope, unavailable document evidence, report ownership/revision, legacy IDs, authentication, and both streaming and synchronous response persistence. The transport checks prohibit warehouse execution. These are automated checks, not 15 live-model answers.
- **199 frontend tests passed** across the complete frontend suite. Later focused checks cover authenticated/fallback greetings, account changes, draft/selection continuity, history focus and restoration, rating removal, failed-save rollback and an in-flight layout switch. TypeScript checking passed.
- Browser checks passed in **Classic/New at 1440px and 390px**, in Light, Dark and AI themes. Real components rendered synthetic API responses. Checks covered centered initial composition, the wider answer canvas, wide-table containment, SQL access, rating restoration after reload, the history drawer, Escape/focus restoration and draft preservation. Reload and feedback made no extra analytical-question request. These checks did not contact a live model, warehouse or Microsoft mailbox.
- PostgreSQL migration SQL generated successfully for the application target from the previous head. The live PostgreSQL migration and live application-database persistence remain for local deployment verification.
- The full backend suite has **three existing document/RAG failures**. All three were reproduced against the pre-change HEAD versions of the modified API modules loaded in memory, without replacing working files. The failures concern legacy hash search under the enabled RAG flag and two older document-route expectations. No RAG routing behavior was changed to mask them.
- The **Webpack production build passed**, including TypeScript checking and generation of all 25 routes, using `npm.cmd run build --workspace apps/web -- --webpack`. The default Turbopack build encountered environment failures: Google Fonts could not be fetched in the restricted run, and an elevated retry hit a Turbopack child-process startup failure in an unrelated ontology stylesheet. The default build script, font configuration and dependencies were not changed.

Local browser captures, generated migration SQL and baseline reproduction evidence are under tmp/soci-qa and excluded from Git. The existing unrelated 1.png was left untouched.

## Main files

| Area | Files |
| --- | --- |
| Branding | apps/web/lib/brand.ts; components/brand/wordmark.tsx and logo.tsx; Home and AskBI presentation/export files; public brand SVGs and public help guides; apps/api/app/main.py and product-name text; README.md and docs/ASK_ME_CODEBASE_CONTEXT.md |
| Shared Chat state/layout | apps/web/hooks/use-chat-ask.ts; components/chat/chat-mode-shell.tsx, chat-workspace.tsx, new-chat-workspace.tsx, chat-workspace-view.tsx; lib/chat-greeting.ts |
| Feedback/history UI | apps/web/components/chat/response-actions.tsx and chat-history.tsx; components/chat/types.ts and sse.ts; packages/shared-types/src/index.ts |
| App persistence/APIs | apps/api/app/api/routes/chat.py; services/chat/responses.py; models/activity.py, chat_rating.py and __init__.py |
| Migration | apps/api/migrations/versions/0015_chat_response_ratings.py |
| Checks | apps/api/tests/test_chat_ratings.py; apps/web/tests/unit/soci-chat.test.tsx; updated Chat, Home and export tests |

No metric formulas, SQL planning logic, warehouse schema, permissions policy, authentication identifiers or Agentic dependencies were migrated or renamed.
