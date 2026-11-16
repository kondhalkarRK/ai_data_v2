# Ask Me UI/UX Redesign — Acceptance Report

**Date:** 2026-11-03  
**Scope:** Phases 1–6 (presentation-only). No API, RBAC, chart engine, or navigation item changes.

## Themes

| Preference | HTML class | Notes |
|---|---|---|
| Light | `(none)` / `light` | Enterprise light palette |
| Dark | `.dark` | Navy dark palette |
| AI | `.theme-ai` | Indigo/violet/cyan signature; `--ai` accent tokens retained |

- `next-themes`: `themes={['light','dark','ai']}`, `enableSystem={false}`, storage key `nql-theme`
- Tailwind `dark:` also matches `.theme-ai`; dedicated `theme-ai:` variant available
- Chart CSS vars under AI theme mirror Dark (no chart visual redesign)
- Logo uses dark mark for Dark and AI

## Phase delivery

| Phase | Status | Highlights |
|---|---|---|
| 0 Audit | Done | Inventory + risks locked before edits |
| 1 Tokens + toggle | Done | Three token sets, ThemeProvider, ThemeToggle (Light/Dark/AI) |
| 2 Shell | Done | Sidebar, topbar, page headers, login aurora chrome, workspace padding |
| 3 Primitives | Done | Button, card, input, surfaces, empty-state / badge utilities |
| 4 Modules | Done | Chat (Classic + New) composers/cards; Knowledge Hub; Admin tabs; Data Trust wrappers; Semantic Atlas tabs; Analytics Builder already token-based; secondary pages polish |
| 5 Regression | Done | Unit tests + typecheck (see below) |
| 6 Polish | Done | Non-chart hex → semantic tokens (reliability chrome, SQL viewer); reduced-motion retained; focus/transition durations ~150 ms |

## Chart protection (verified by scope)

Unchanged rendering/config:

- `components/chat/result-chart.tsx`
- `components/executive/cockpit/*` SVG / `palette.ts`
- Trust chart SVG bodies / ontology galaxy engine
- Admin chart series mapping

Allowed chrome-only changes around those surfaces were applied.

## Functionality preservation

- Nav source of truth (`lib/navigation.ts`) and RBAC unchanged
- No backend / schema / SQL / RAG behaviour changes in this redesign
- Theme persistence remains client `localStorage` via `nql-theme`

## Test results (2026-11-03)

| Check | Command | Result |
|---|---|---|
| Unit | `npm test` (vitest) in `apps/web` | **Pass** (exit 0) |
| Typecheck | `npm run typecheck` | **Pass** (exit 0) |
| E2E | `npm run test:e2e` | Not run in this pass (needs Playwright browser + running app). Spec already expects Dark theme radios; System removed in favour of AI |

Theme unit coverage: `tests/unit/theme-toggle.test.tsx` asserts Light / Dark / AI and absence of System.

## Manual sweep checklist

Confirm in browser under Light, Dark, and AI:

1. Shell: sidebar active states, topbar tabs, theme toggle (both placements if visible)
2. Login aurora + form contrast
3. `/chat` Classic and New: composer, user bubble, response card, SQL viewer
4. `/dashboard` containers only (cockpit charts look as before)
5. `/data-quality` chrome vs chart bodies
6. `/semantic` atlas tabs + ontology chrome (galaxy engine unchanged)
7. `/analytics-builder`, `/knowledge`, `/admin`, saved questions / history / profile

## Residual notes

- Cockpit / geo / ranked hex accents inside protected chart layers remain intentional
- Ontology particle/glow skin was not rewritten (chrome only per plan)
- If an older session stored `system` in `nql-theme`, next-themes falls back to `defaultTheme=light` after System removal
