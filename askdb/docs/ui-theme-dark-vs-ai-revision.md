# Revised Phase 0 Design Proposal — Differentiated Light / Dark / AI

**Status:** Approved. Phase 1 tokens implemented (Midnight Professional Dark vs Aurora Intelligence AI).

**Problem (current code):** Dark and AI share nearly the same surface lightness (~7–14% L), similar blue-family hues, and aurora variables on both. Switching feels like “same dark shell + accent swap,” not two identities.

**Goal:** Three genuinely different visual experiences. Atmosphere and surface hierarchy change—not only accents.

---

## 1. Three clearly differentiated palettes

Approx hex shown for readability; implementation will remain HSL CSS variables.

### Light — Clean Enterprise (unchanged intent)

| Role | Approx | Notes |
|---|---|---|
| Background / page | `#F7F9FC` | Cool grey-white |
| Raised card | `#FFFFFF` | Paper white |
| Sunken / muted | `#EEF2F7` | Soft inset |
| Primary | `#3867E8` | Enterprise blue |
| Accent | indigo-blue | Secondary emphasis |
| Borders | `#E2E8F0` | Hairline |
| Atmosphere | Flat, bright, no aurora | Stripe/Notion restraint |

### Dark — Midnight Professional (revised)

**Identity:** Neutral charcoal / slate. Professional enterprise. **No aurora. No violet surfaces.**

| Role | Approx | Hue intent |
|---|---|---|
| Background | `#12151A` | Near-neutral charcoal (sat ≤ 8%) |
| Surface (page well) | `#171A20` | Slate charcoal |
| Raised (cards, panels) | `#1E232B` | Cool grey, not navy |
| Sunken (inputs wells, SQL chrome surround) | `#0E1014` | Deeper charcoal |
| Foreground | `#E8EAED` | Soft off-white |
| Muted foreground | `#9AA3AE` | Slate grey |
| Primary | `#6B8CC8` | **Muted steel blue** |
| Accent | `#5B7FA6` | Muted blue (not cyan, not violet) |
| `--ai` accent role | Same family as muted blue | Accent token only—not a theme |
| Border / input | `#2A3038` | Neutral grey edge |
| Sidebar | `#14171C` | Matches charcoal family |
| Shadows | Soft black only | No coloured glow |
| Aurora tokens | **Disabled / opacity 0** for Dark | Login = flat charcoal, not gradients |

**Explicitly forbidden in Dark:** purple/violet fills, cyan glow, aurora blobs, glass blur washes.

### AI — Aurora Intelligence (revised)

**Identity:** Midnight-indigo foundation, violet-tinted surfaces, violet + cyan signatures, selective aurora, subtle glass.

| Role | Approx | Hue intent |
|---|---|---|
| Background | `#0A0714` | Deep midnight indigo-violet |
| Surface | `#120E22` | Indigo-tinted base |
| Raised | `#1A1530` + translucent wash | Violet-tinted glass card |
| Sunken | `#070510` | Deeper indigo well |
| Foreground | `#F0EEF8` | Cool lilac-white |
| Muted foreground | `#A8A0C0` | Soft violet-grey |
| Primary | `#8B7CFF` | Signature violet-indigo |
| Accent | `#C084FC` | Violet |
| `--ai` / cyan accent | `#22D3EE`-family | Cyan signature |
| Border | `#2E2850` at ~40–60% alpha | Violet edge / glass rim |
| Sidebar | `#0C0918` | Deeper indigo than page |
| Shadows | Soft violet + black | Coloured elevation |
| Aurora | **On** (login, home hero, chat empty/composer rim) | Selective, not every card |

**Charts:** `--chart-*` for AI remain **copied from Dark chart tokens** (no chart redesign), per existing restriction.

---

## 2. Theme-specific surface hierarchy

| Layer | Light | Dark (Midnight Professional) | AI (Aurora Intelligence) |
|---|---|---|---|
| Page `background` | Cool grey-white | Flat charcoal | Midnight indigo |
| `surface` | Same as page / soft | Slate charcoal | Indigo base |
| `surface-raised` | White opaque | Opaque cool grey card | Violet-tinted + light blur/border |
| `surface-sunken` | Light grey inset | Deeper charcoal | Near-black indigo |
| Borders | Neutral grey | Neutral slate | Violet-slate glass rim |
| Elevation | Soft grey shadow | Black-only shadow | Violet-tinted shadow |
| Atmosphere utilities | None | **No** `.aurora-*` paint | Aurora + `.glass-panel` on shell/chat |

Shared semantic names stay identical (`background`, `surface-raised`, `primary`, `nav-active-*`, etc.). **Values** diverge strongly so every token-consuming component inherits the atmosphere without per-page forks.

---

## 3. Theme-specific sidebar and header

| Element | Light | Dark | AI |
|---|---|---|---|
| Sidebar fill | White | Charcoal `#14171C` | Midnight `#0C0918` |
| Sidebar border | Light grey | Slate grey | Violet edge |
| Active nav | Soft blue wash | Muted steel-blue wash on slate | Violet wash + cyan/violet indicator |
| Inactive nav | Grey text | Slate muted | Violet-grey muted |
| Topbar | White / raised | Charcoal raised, flat | Semi-glass indigo (`backdrop-blur`, translucent border) |
| Module headers | Blue eyebrow | Steel-blue eyebrow | Violet eyebrow |
| Theme toggle track | Light sunken | Slate sunken | Indigo sunken; AI option uses violet glow when selected |

---

## 4. Shared semantic token definitions

Unchanged **token names** (components keep consuming these):

```
--background, --surface, --surface-raised, --surface-sunken
--foreground, --muted, --muted-foreground
--primary, --primary-foreground, --accent, --accent-foreground
--ai, --ai-foreground, --ai-muted          /* accent role, not theme id */
--border, --input, --ring
--sidebar, --sidebar-border
--nav-active-bg, --nav-active-fg
--aurora-a, --aurora-b, --aurora-c         /* Dark: unused / zero opacity */
--shadow-card, --shadow-raised, --shadow-overlay
--chart-*                                  /* AI copies Dark chart set */
```

**New / clarified utilities (implementation after approval):**

| Utility | Light | Dark | AI |
|---|---|---|---|
| `.aurora-shell` / `.hero-ambient` | Subtle cool wash optional | **No paint** (solid bg only) | Full selective aurora |
| `.glass-panel` | n/a or very light | **Off** | Translucent raised + blur |
| `.card-surface` / `.card-secondary` | White card | Opaque slate card | Glass / violet-tint card |

Class strategy unchanged: `.dark` vs `.theme-ai` on `<html>`; `themes=['light','dark','ai']`; storage `nql-theme`.

---

## 5. How Dark vs AI will look different across modules

| Module / surface | Dark (Midnight Professional) | AI (Aurora Intelligence) |
|---|---|---|
| **Login** | Flat charcoal panel, muted blue CTA, no blobs | Aurora backdrop, glass card, violet CTA + cyan accents |
| **Sidebar / topbar** | Neutral slate chrome | Indigo glass chrome, violet active states |
| **Page backgrounds** | Charcoal flat | Midnight indigo with soft aurora at edges (where shell allows) |
| **Cards / modals / dropdowns** | Opaque grey panels, grey borders | Violet-tinted glass, coloured rim/shadow |
| **Buttons / tabs** | Steel-blue primary; grey secondary | Violet primary; cyan/`ai` secondary accents |
| **Inputs / filters** | Charcoal fields, slate border | Indigo fields, violet focus ring |
| **AI Chat** | Professional dark composer/bubbles | Glass composer, violet user bubble / AI accents, aurora empty state |
| **Module headers** | Muted blue eyebrow | Violet eyebrow |
| **Loading / empty** | Grey dashed wells | Indigo wells + soft aurora hint |
| **Data Trust / Semantic / Admin wrappers** | Same charcoal card language | Same glass/indigo card language |
| **Charts inside** | Unchanged SVG/config | Unchanged; chart CSS vars = Dark set |

**Instant test after implementation:** Toggle Dark → AI without scrolling. Page background hue, card tint, sidebar, and topbar must read as different families within one glance—not “purple accents on the same navy.”

---

## 6. Restrictions (unchanged)

- No chart component / chart colour config changes
- AI `--chart-*` may continue to mirror Dark chart tokens
- No backend, API, DB, business logic, or RBAC changes
- Keep `nql-theme` persistence and existing routes/nav

---

## 7. Implementation plan (only after your approval)

1. Retarget `.dark` token block → Midnight Professional (desaturate, kill aurora for Dark).
2. Retarget `.theme-ai` → Aurora Intelligence (indigo foundation, glass, aurora on).
3. Gate aurora/glass CSS so Dark paths render flat.
4. Spot-check shell + chat + login under all three themes.
5. Re-run `npm test` / typecheck; update acceptance note.

---

## Approval ask

Please approve this revised Dark vs AI differentiation (or request palette tweaks). **No code changes for this correction until you approve.**
