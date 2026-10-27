/**
 * Chart colours resolved from design tokens so SVG/canvas visuals track light/dark theme.
 * Falls back to cockpit hex when `document` is unavailable (tests, SSR).
 */

const FALLBACK_SERIES = [
  "#2f6fed",
  "#14a3a1",
  "#5b8def",
  "#3fbfb5",
  "#7c9cc9",
  "#0e7c86",
] as const;

const TOKEN_KEYS = [
  "--chart-1",
  "--chart-2",
  "--chart-3",
  "--chart-4",
  "--chart-5",
  "--chart-6",
] as const;

function readToken(name: string): string | null {
  if (typeof document === "undefined") return null;
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  if (!raw) return null;
  return `hsl(${raw})`;
}

/** Series colours aligned with `--chart-*` tokens. */
export function chartSeriesColors(): string[] {
  const fromDom = TOKEN_KEYS.map((key) => readToken(key)).filter(Boolean) as string[];
  return fromDom.length === TOKEN_KEYS.length ? fromDom : [...FALLBACK_SERIES];
}

export function chartColor(index: number): string {
  const palette = chartSeriesColors();
  return palette[index % palette.length] ?? palette[0]!;
}

export function chartGridColor(): string {
  return readToken("--chart-grid") ?? "hsl(214 25% 90%)";
}

export function chartAxisColor(): string {
  return readToken("--chart-axis") ?? "hsl(215 16% 45%)";
}

export function chartMutedFill(): string {
  return readToken("--muted-foreground")
    ? `color-mix(in oklab, ${readToken("--muted-foreground")!} 35%, transparent)`
    : "rgba(148, 163, 184, 0.35)";
}

/** SVG attribute colours — token-backed, safe in SSR as static hsl(var(...)). */
export const SVG_CHART = {
  grid: "hsl(var(--chart-grid))",
  axis: "hsl(var(--chart-axis))",
  surface: "hsl(var(--surface-raised))",
  foreground: "hsl(var(--foreground))",
} as const;
