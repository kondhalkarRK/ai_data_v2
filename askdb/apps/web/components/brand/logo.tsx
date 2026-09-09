"use client";

import Image from "next/image";
import { useTheme } from "next-themes";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Brand mark from the supplied logo (brain). White paper is stripped so the mark
 * works on light and dark surfaces. Wordmark uses the product name NQL Insight with
 * theme-specific assets (navy fails on dark; cyan accent matches the mark).
 */

export const BRAND_NAME = "NQL Insight";
export const BRAND_TAGLINE = "Intelligence. Refined. Delivered.";

const HAS_BRAND_ASSETS = true;

type LogoSize = "sm" | "md" | "lg";

const MARK_PIXELS: Record<LogoSize, number> = { sm: 22, md: 28, lg: 44 };

const WORDMARK_SIZE: Record<LogoSize, { width: number; height: number }> = {
  sm: { width: 108, height: 18 },
  md: { width: 128, height: 22 },
  lg: { width: 168, height: 28 },
};

function useResolvedDark(): boolean {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  // Prefer light assets until mounted to avoid a flash of the wrong wordmark.
  if (!mounted) return false;
  return resolvedTheme === "dark";
}

interface LogoMarkProps {
  size?: LogoSize;
  className?: string;
  /** Glow, orbit and breathing — loading state only. */
  animated?: boolean;
}

export function LogoMark({ size = "md", className, animated = false }: LogoMarkProps) {
  const pixels = MARK_PIXELS[size];
  const dark = useResolvedDark();
  const src = dark ? "/brand/logo-mark-dark.png" : "/brand/logo-mark.png";

  return (
    <span
      className={cn("relative inline-flex shrink-0 items-center justify-center", className)}
      style={{ width: pixels, height: pixels }}
    >
      {animated ? (
        <>
          <span
            aria-hidden="true"
            className="absolute inset-0 rounded-full bg-primary/25 blur-md motion-safe:animate-[var(--animate-breathe)]"
          />
          <span
            aria-hidden="true"
            className="absolute inset-[-18%] rounded-full opacity-70 motion-safe:animate-[var(--animate-orbit)]"
            style={{
              background:
                "conic-gradient(from 0deg, transparent 0deg, hsl(var(--primary) / 0.55) 90deg, hsl(var(--accent) / 0.5) 190deg, transparent 300deg)",
              maskImage: "radial-gradient(circle, transparent 58%, black 62%)",
              WebkitMaskImage: "radial-gradient(circle, transparent 58%, black 62%)",
            }}
          />
        </>
      ) : null}

      {HAS_BRAND_ASSETS ? (
        <Image
          key={src}
          src={src}
          alt=""
          width={pixels}
          height={pixels}
          priority
          unoptimized
          className="relative drop-shadow-sm"
        />
      ) : (
        <span
          aria-hidden="true"
          className="relative flex size-full items-center justify-center rounded-[0.4rem] bg-primary font-semibold tracking-tight text-primary-foreground"
          style={{ fontSize: pixels * 0.42 }}
        >
          NQ
        </span>
      )}
    </span>
  );
}

interface LogoProps {
  size?: LogoSize;
  /** Mark only, for the collapsed sidebar. */
  compact?: boolean;
  animated?: boolean;
  /** Show the supplied tagline under the wordmark (login / marketing). */
  withTagline?: boolean;
  className?: string;
}

export function Logo({
  size = "md",
  compact = false,
  animated = false,
  withTagline = false,
  className,
}: LogoProps) {
  const dark = useResolvedDark();
  const wordmark = dark ? "/brand/logo-wordmark-dark.svg" : "/brand/logo-wordmark.svg";
  const dims = WORDMARK_SIZE[size];

  return (
    <span
      className={cn(
        "inline-flex flex-col gap-1",
        withTagline ? "items-center" : "items-start",
        className,
      )}
    >
      <span className="inline-flex items-center gap-2.5">
        <LogoMark size={size} animated={animated} />
        {compact ? null : HAS_BRAND_ASSETS ? (
          <Image
            key={wordmark}
            src={wordmark}
            alt={BRAND_NAME}
            width={dims.width}
            height={dims.height}
            priority
            unoptimized
            className="relative"
          />
        ) : (
          <span
            className={cn(
              "font-semibold tracking-tight text-foreground",
              size === "sm" && "text-sm",
              size === "md" && "text-lg",
              size === "lg" && "text-2xl",
            )}
          >
            NQL <span className="font-normal text-cyan-700 dark:text-cyan-300">Insight</span>
          </span>
        )}
        <span className="sr-only">{BRAND_NAME}</span>
      </span>
      {withTagline && !compact ? (
        <span
          className={cn(
            "font-serif text-muted-foreground",
            size === "lg" ? "text-xs tracking-wide" : "text-[10px]",
          )}
        >
          {BRAND_TAGLINE}
        </span>
      ) : null}
    </span>
  );
}
