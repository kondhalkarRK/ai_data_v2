# NQL Insight — Phase 0 Design Token Plan

## Guiding review

Kept the existing Inter + HSL token system (already light/dark). Did **not**
add “icon chip on every card” or uniform soft shadows. Boldness is reserved
for: Executive Intelligence **Business Health** score, Data Trust **Trust Score**
hero, and active nav. Everything else stays secondary/supporting.

Changed from generic dashboard default: no ALL-CAPS tracked eyebrows; status
always pairs color with an icon shape; card tiers (primary / secondary /
supporting) instead of one shadow everywhere.

## Color (approx. hex — tokens stored as HSL)

| Role | Light | Dark note |
|------|-------|-----------|
| Background | `#FFFFFF` | near `#070D17` |
| Surface | `#F7F9FB` | raised panels |
| Foreground | `#1B2430` | light gray text |
| Border | `#E2E8F0` | muted borders |
| Blue (primary / analytics) | `#2563EB` | lighter blue |
| Green (healthy / success) | `#0F9D6E` | mint |
| Amber (warning) | `#F59E0B` | soft amber |
| Red (critical) | `#E11D48` | soft rose |
| Purple (AI / semantic) | `#8B5CF6` | lavender |
| Teal (data / governance) | `#0D9488` | teal |
| Orange (opportunity / action) | `#EA580C` | soft orange |

~90% neutral / 10% accent.

## Type

- **Family:** Inter (existing) — UI; system mono for SQL/code.
- **Scale:** page title 24px (`text-2xl`), section 16–18px (`text-lg`/`text-base` semibold), card title 14px (`text-sm`), primary metric 28–36px (`text-3xl`/`text-4xl`), supporting 12–13px (`text-xs`/`text-sm`).

## Layout

```text
[Sidebar] | PageShell max-w-7xl mx-auto
          | PageHeader
          | Primary summary (one bold block)
          | Main grid (gap-4 / gap-6)
          | Secondary sections
```

- Page padding: 16px mobile / 24px desktop (existing shell).
- Content max-width: `80rem` (`max-w-7xl`).
- Grid gap: 12–16px cards; section stack 24px.

**Chat:** conversational column, not dashboard grid.  
**Data Preview:** sidebar list + neutral table.

## Icons

**Lucide only** — outlined, `size-3.5` / `size-4`, optional tinted container on primary surfaces only.

## Dark mode

**In scope** — all new tokens defined as `:root` / `.dark` pairs (already the app pattern).
