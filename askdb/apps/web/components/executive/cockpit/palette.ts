/**
 * Cockpit palette: soft blue, executive grey and light teal. Concrete colours (not CSS
 * variables) so exported PNGs render identically outside the page.
 */
export const COCKPIT = {
  blue: "#2f6fed",
  blueSoft: "#8fb3f5",
  blueMist: "#e3ecfd",
  teal: "#14a3a1",
  tealSoft: "#8fd6d2",
  tealMist: "#dff4f2",
  grey: "#64748b",
  greySoft: "#cbd5e1",
  greyMist: "#f1f5f9",
  ink: "#1e293b",
  positive: "#0f8f7e",
  negative: "#c8574d",
  amber: "#d69e2e",
  amberMist: "#fdf3dc",
} as const;

export const CATEGORY_COLOURS = [
  "#2f6fed",
  "#14a3a1",
  "#5b8def",
  "#3fbfb5",
  "#7c9cc9",
  "#0e7c86",
  "#9db7f0",
  "#6fcfc4",
  "#94a3b8",
  "#4f79b8",
  "#a7c4f2",
  "#2c9c9a",
  "#b4c6dc",
  "#5e81ac",
  "#7fd1c7",
];

export function categoryColour(index: number): string {
  return CATEGORY_COLOURS[index % CATEGORY_COLOURS.length] ?? COCKPIT.blue;
}

/** Mix a hex colour toward white (amount 0..1). */
export function tint(hex: string, amount: number): string {
  const n = Number.parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  const mix = (c: number) => Math.round(c + (255 - c) * amount);
  return `#${[mix(r), mix(g), mix(b)].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

/** Diverging growth colour: coral (decline) ← grey → teal (growth). */
export function growthColour(growth: number | null, max = 0.25): string {
  if (growth == null) return COCKPIT.greySoft;
  const t = Math.max(-1, Math.min(1, growth / max));
  if (t >= 0) return tint(COCKPIT.positive, 0.85 - 0.6 * t);
  return tint(COCKPIT.negative, 0.85 + 0.6 * t);
}

export function toneColour(tone: "positive" | "negative" | "neutral"): string {
  return tone === "positive" ? COCKPIT.positive : tone === "negative" ? COCKPIT.negative : COCKPIT.grey;
}
