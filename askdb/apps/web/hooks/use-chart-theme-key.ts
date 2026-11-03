"use client";

import { useTheme } from "next-themes";

/**
 * Stable key that changes when Light / Dark / AI swaps so SVG charts that
 * sample CSS tokens (or computed colours) remount with the active palette.
 */
export function useChartThemeKey(): string {
  const { theme, resolvedTheme } = useTheme();
  return resolvedTheme ?? theme ?? "light";
}
