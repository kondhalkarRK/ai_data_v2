"use client";

import * as React from "react";

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3;
}

/**
 * Animates a numeric value from 0 → target when the element enters the viewport.
 * Skips motion when the user prefers reduced motion.
 */
export function useCountUp(
  target: number | null | undefined,
  {
    duration = 900,
    decimals = 0,
    enabled = true,
  }: { duration?: number; decimals?: number; enabled?: boolean } = {},
): { display: number; ref: React.RefObject<HTMLElement | null> } {
  const ref = React.useRef<HTMLElement | null>(null);
  const [display, setDisplay] = React.useState(0);
  const [visible, setVisible] = React.useState(false);

  React.useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.35 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  React.useEffect(() => {
    if (!enabled || !visible) return;
    if (target == null || Number.isNaN(target)) {
      setDisplay(0);
      return;
    }
    if (prefersReducedMotion() || duration <= 0) {
      setDisplay(target);
      return;
    }

    let frame = 0;
    const start = performance.now();
    const from = 0;
    const delta = target - from;

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const next = from + delta * easeOutCubic(t);
      setDisplay(decimals > 0 ? Number(next.toFixed(decimals)) : Math.round(next));
      if (t < 1) frame = requestAnimationFrame(tick);
      else setDisplay(target);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, duration, decimals, enabled, visible]);

  return { display, ref };
}
