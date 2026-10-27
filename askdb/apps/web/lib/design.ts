/** Shared chart / semantic accent colors from design tokens. */

export const CHART_SERIES = {
  primary: "hsl(var(--chart-1))",
  secondary: "hsl(var(--chart-2))",
  tertiary: "hsl(var(--chart-3))",
  positive: "hsl(var(--success))",
  attention: "hsl(var(--chart-4))",
  ai: "hsl(var(--ai))",
  accent: "hsl(var(--accent))",
  muted: "hsl(var(--muted-foreground) / 0.35)",
  grid: "hsl(var(--chart-grid))",
  axis: "hsl(var(--chart-axis))",
} as const;

export const DIMENSION_CHART: Record<string, string> = {
  accuracy: "hsl(var(--chart-1))",
  completeness: "hsl(var(--chart-2))",
  consistency: "hsl(var(--chart-5))",
  timeliness: "hsl(var(--teal))",
  validity: "hsl(var(--chart-6))",
  uniqueness: "hsl(var(--chart-3))",
};

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
      return "border-ai/35 bg-ai-muted/80 text-ai dark:bg-ai/12 dark:text-ai";
    default:
      return "border-border/70 bg-muted/40 text-muted-foreground";
  }
}
