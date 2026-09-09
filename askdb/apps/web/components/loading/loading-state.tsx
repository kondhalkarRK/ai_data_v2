"use client";

import * as React from "react";

import { LogoMark } from "@/components/brand/logo";
import { cn } from "@/lib/utils";

/**
 * Rotating status messages from spec section 8. Ordered to match the real pipeline, so
 * the text is a rough narration of what is happening rather than decoration.
 */
export const LOADING_MESSAGES = [
  "Analyzing your question...",
  "Understanding business context...",
  "Loading data...",
  "Building semantic relationships...",
  "Exploring ontology...",
  "Generating insights...",
  "Retrieving relevant information...",
  "Preparing dashboard...",
  "Finalizing response...",
] as const;

/** Cycles through messages, pausing under prefers-reduced-motion. */
function useRotatingMessage(messages: readonly string[], intervalMs: number): string {
  const [index, setIndex] = React.useState(0);

  React.useEffect(() => {
    if (messages.length <= 1) return;

    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Rotating text is itself motion. Someone who asked for less of it gets the first
    // message and no churn.
    if (reduceMotion) return;

    const timer = window.setInterval(() => {
      setIndex((current) => (current + 1) % messages.length);
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [messages, intervalMs]);

  return messages[index] ?? messages[0] ?? "";
}

interface LoadingStateProps {
  /** Supply pipeline-specific messages, or omit for the default sequence. */
  messages?: readonly string[];
  intervalMs?: number;
  /** A fixed label shown above the rotating message. */
  title?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

/**
 * A local loading boundary.
 *
 * Sized to sit inside a card or a panel. Spec section 8 forbids blocking the whole UI for
 * a background request, so this never covers the shell — each region shows its own.
 */
export function LoadingState({
  messages = LOADING_MESSAGES,
  intervalMs = 2200,
  title,
  size = "md",
  className,
}: LoadingStateProps) {
  const message = useRotatingMessage(messages, intervalMs);

  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={cn(
        "flex flex-col items-center justify-center gap-3 text-center",
        size === "sm" ? "py-8" : size === "lg" ? "py-20" : "py-14",
        className,
      )}
    >
      <LogoMark size={size === "sm" ? "md" : "lg"} animated />
      {title ? (
        <p className="text-sm font-medium text-foreground">{title}</p>
      ) : null}
      {/* The key restarts the fade each time the message changes. */}
      <p
        key={message}
        className="text-sm text-muted-foreground motion-safe:animate-[var(--animate-fade-in)]"
      >
        {message}
      </p>
    </div>
  );
}

/**
 * Full-page loading, used only for the initial authenticated boot before the shell can
 * render. Every subsequent navigation uses a local boundary instead.
 */
export function AppBootLoading() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-background">
      <LogoMark size="lg" animated />
      <p className="text-sm text-muted-foreground" role="status" aria-live="polite">
        Loading your workspace...
      </p>
    </div>
  );
}
