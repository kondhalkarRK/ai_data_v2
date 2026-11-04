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
 * Counts once on entry, then transitions from the currently displayed value.
 * A new result cancels the previous frame; unrelated renders never restart it.
 */
export function useCountUp(
  target: number | null | undefined,
  {
    duration = 700,
    decimals = 0,
    enabled = true,
  }: { duration?: number; decimals?: number; enabled?: boolean } = {},
): { display: number; ref: React.RefObject<HTMLElement | null> } {
  const ref = React.useRef<HTMLElement | null>(null);
  const [display, setDisplay] = React.useState(0);
  const [visible, setVisible] = React.useState(false);
  const current = React.useRef(0);

  React.useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      const frame = requestAnimationFrame(() => setVisible(true));
      return () => cancelAnimationFrame(frame);
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
    if (target == null || !Number.isFinite(target) || !visible) return;

    let frame = 0;
    const start = performance.now();
    const from = current.current;
    const delta = target - from;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const finish = () => {
      cancelAnimationFrame(frame);
      current.current = target;
      setDisplay(target);
    };
    const onMotionChange = () => { if (media.matches) finish(); };
    media.addEventListener("change", onMotionChange);

    const tick = (now: number) => {
      if (!enabled || prefersReducedMotion() || duration <= 0) {
        finish();
        return;
      }
      const t = Math.min(1, (now - start) / duration);
      const next = from + delta * easeOutCubic(t);
      current.current = next;
      setDisplay(decimals > 0 ? Number(next.toFixed(decimals)) : Math.round(next));
      if (t < 1) frame = requestAnimationFrame(tick);
      else finish();
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      media.removeEventListener("change", onMotionChange);
    };
  }, [target, duration, decimals, enabled, visible]);

  return { display, ref };
}
