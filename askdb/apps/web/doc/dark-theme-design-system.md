# AskDB dark theme design system

## Token source

All theme values live in `app/globals.css` as HSL custom properties on `:root` and `.dark`. Tailwind maps them via `@theme inline` (`bg-surface-raised`, `text-ai`, `border-border`, etc.).

### Surfaces (dark)

| Token | Role |
|--------|------|
| `--background` | App canvas (midnight charcoal) |
| `--surface` | Page sections |
| `--surface-raised` | Cards, panels, dropdowns |
| `--surface-sunken` | Inset wells, graph backgrounds |
| `--sidebar` | Navigation rail |

### Brand & AI

| Token | Role |
|--------|------|
| `--primary` | Primary actions, links |
| `--ai` / `--ai-muted` | LLM activity, semantic/AI chips, query progress |
| `--accent` | Secondary emphasis (cyan family in dark) |

### Data viz

| Token | Role |
|--------|------|
| `--chart-1` … `--chart-6` | Series palette (aligned across Executive, Trust, Chat) |
| `--chart-grid` / `--chart-axis` | Gridlines and axis labels in SVG charts |

### Shared utilities (`globals.css`)

- `card-surface`, `panel-surface`, `panel-surface-elevated`
- `data-table`, `data-table-wrap`, `empty-state`
- `segmented-control`, `icon-btn-ghost`, `overlay-scrim`, `ai-surface`

### TypeScript helpers

- `lib/surface.ts` — class bundles for panels, typography, overlays
- `lib/design.ts` — `CHART_SERIES`, `statusToneClasses`, DQ dimension colours
- `lib/chart-colors.ts` — runtime series colours + `SVG_CHART` constants

## Module coverage

Styling passes applied to: shell (sidebar/topbar), Executive cockpit charts, Data Trust / reliability, chat (timeline, grounding), semantic galaxy (existing token CSS), and bulk token migration away from `slate-*` / `#2f6fed` literals in `components/` and `app/`.

## Theme toggle

Unchanged: `next-themes` class on `<html>`; light tokens remain on `:root`.

## Verification

```bash
cd askdb/apps/web
npm run typecheck
npm run lint
npm run test
npm run build
```

Some SVG point strokes may still use fixed white halos for contrast on coloured series; series colours resolve via `categoryColour()` / `--chart-*` at runtime.
