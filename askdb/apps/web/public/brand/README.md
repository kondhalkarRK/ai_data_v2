# Brand assets

Supplied logo (brain mark) with white paper removed so it works on light and dark
surfaces. Product wordmark is **NQL Insight** (per `promt.md`); the mark is the
attached art, not redrawn.

| File | Purpose |
| --- | --- |
| `logo-mark.svg` / `logo-mark.png` | Square mark (light UI) |
| `logo-mark-dark.svg` / `logo-mark-dark.png` | Brightened mark for dark UI |
| `logo-wordmark.svg` | Light-theme wordmark |
| `logo-wordmark-dark.svg` | Dark-theme wordmark |
| `logo-loading.svg` | Same as mark; animation is CSS |
| `logo-lockup-light.png` / `logo-lockup-dark.png` | Full supplied lockup (transparent) |
| `icon.png` | 512×512 app icon |
| `favicon.ico` / `favicon-32.png` | Browser icons |
| `apple-touch-icon.png` | iOS home screen |

`components/brand/logo.tsx` sets `HAS_BRAND_ASSETS = true` and picks light/dark
assets from `next-themes`.

Regenerate from the source PNG:

```bash
python scripts/process_logo.py
```
