"use client";

import * as React from "react";

import { useCountUp } from "@/hooks/use-count-up";
import { cn } from "@/lib/utils";

export function AnimatedNumber({
  value,
  format,
  fallback = "—",
  duration = 900,
  decimals,
  className,
  as: Tag = "span",
}: {
  value: number | null | undefined;
  /** Formats the animated number for display. Defaults to locale string. */
  format?: (n: number) => string;
  fallback?: string;
  duration?: number;
  decimals?: number;
  className?: string;
  as?: "span" | "p" | "div";
}) {
  const inferredDecimals =
    decimals ??
    (value != null && !Number.isInteger(value) ? Math.min(2, String(value).split(".")[1]?.length ?? 1) : 0);
  const { display, ref } = useCountUp(value, { duration, decimals: inferredDecimals });

  const text =
    value == null || Number.isNaN(value)
      ? fallback
      : (format ?? ((n: number) => n.toLocaleString()))(display);

  // Always attach the intersection observer to a span so tag polymorphism stays type-safe.
  return (
    <Tag className={cn("tabular-nums", className)}>
      <span ref={ref as React.RefObject<HTMLSpanElement>}>{text}</span>
    </Tag>
  );
}
