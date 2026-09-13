/** Shared chart / semantic accent colors from design tokens. */

export const CHART_SERIES = {
  primary: "hsl(var(--chart-1))",
  secondary: "hsl(var(--teal))",
  positive: "hsl(var(--success))",
  attention: "hsl(var(--orange))",
  ai: "hsl(var(--accent))",
  muted: "hsl(var(--muted-foreground) / 0.35)",
} as const;

export type StatusTone = "ok" | "warn" | "fail" | "info" | "ai" | "neutral";

export function statusToneClasses(tone: StatusTone): string {
  switch (tone) {
    case "ok":
      return "border-success/30 bg-success/8 text-success";
    case "warn":
      return "border-warning/35 bg-warning/10 text-warning-foreground dark:text-warning";
    case "fail":
      return "border-danger/30 bg-danger/8 text-danger";
    case "info":
      return "border-primary/25 bg-primary/8 text-primary";
    case "ai":
      return "border-accent/30 bg-accent/10 text-accent";
    default:
      return "border-border/70 bg-muted/40 text-muted-foreground";
  }
}
