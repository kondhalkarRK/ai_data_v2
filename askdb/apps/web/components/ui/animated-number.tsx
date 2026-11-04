"use client";

import * as React from "react";

import { useCountUp } from "@/hooks/use-count-up";
import { cn } from "@/lib/utils";

export function AnimatedNumber({
  value,
  format,
  fallback = "—",
  duration = 700,
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
    (value != null && !Number.isInteger(value) ? Math.min(4, String(value).split(".")[1]?.length ?? 1) : 0);
  const { display, ref } = useCountUp(value, { duration, decimals: inferredDecimals });

  const text =
    value == null || !Number.isFinite(value)
      ? fallback
      : (format ?? ((n: number) => n.toLocaleString("en-IN")))(display);

  // Always attach the intersection observer to a span so tag polymorphism stays type-safe.
  return (
    <Tag className={cn("tabular-nums", className)}>
      <span className="sr-only">{value == null || !Number.isFinite(value) ? fallback : (format ?? ((n: number) => n.toLocaleString("en-IN")))(value)}</span>
      <span ref={ref as React.RefObject<HTMLSpanElement>} aria-hidden="true">{text}</span>
    </Tag>
  );
}
