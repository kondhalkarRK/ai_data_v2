/** Shared Tailwind class bundles — one design system across modules. */

export const surface = {
  page: "bg-background",
  pageAurora: "aurora-shell min-h-full",
  panel: "panel-surface",
  panelElevated: "panel-surface-elevated",
  card: "card-surface",
  cardPrimary: "card-primary",
  cardSecondary: "card-secondary",
  supporting: "card-supporting",
  ai: "ai-surface",
} as const;

export const type = {
  title: "text-foreground font-semibold tracking-tight",
  subtitle: "text-xs text-muted-foreground",
  sectionLabel: "text-2xs font-medium uppercase tracking-wide text-muted-foreground",
  body: "text-sm text-foreground",
  muted: "text-sm text-muted-foreground",
  numeric: "tabular-nums text-foreground",
} as const;

export const interactive = {
  iconGhost: "icon-btn-ghost",
  rowHover: "transition-colors duration-150 hover:bg-muted/50",
  tableRow: "border-b border-border transition-colors duration-150 hover:bg-muted/45",
  focusRing: "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
  navActive: "nav-item-active",
} as const;

export const overlay = {
  scrim: "overlay-scrim",
  dropdown:
    "z-[70] min-w-36 rounded-lg border border-border bg-surface-raised p-1 text-xs shadow-overlay animate-[fade-in_180ms_ease-out]",
  menuItem:
    "cursor-pointer rounded px-2 py-1.5 outline-none transition-colors duration-150 data-[highlighted]:bg-muted",
  tooltip:
    "pointer-events-none rounded-lg border border-border bg-surface-raised/95 px-3 py-2 text-2xs shadow-overlay backdrop-blur-sm",
} as const;

export const motion = {
  hover: "transition-colors duration-150",
  press: "transition-transform duration-150 active:scale-[0.98]",
  enter: "animate-[fade-in_200ms_ease-out]",
} as const;
