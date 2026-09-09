"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const OPTIONS = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
] as const;

const subscribeToNothing = () => () => undefined;

/**
 * Theme switch.
 *
 * The change is a class swap on <html>, so nothing re-renders and no request is made —
 * which is how the sub-50 ms target in spec section 19 is met.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  // The server snapshot is false and the browser snapshot true. This expresses the
  // hydration boundary without a synchronous setState inside an effect.
  const mounted = React.useSyncExternalStore(
    subscribeToNothing,
    () => true,
    () => false,
  );

  if (!mounted) {
    return <div className={cn("h-8 w-[6.75rem] rounded-full bg-muted", className)} aria-hidden />;
  }

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full border border-border bg-surface-sunken p-0.5",
        className,
      )}
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const selected = theme === value;
        return (
          <Button
            key={value}
            role="radio"
            aria-checked={selected}
            aria-label={`${label} theme`}
            variant="ghost"
            size="icon-sm"
            onClick={() => setTheme(value)}
            className={cn(
              "rounded-full transition-colors",
              selected && "bg-surface-raised text-foreground shadow-[var(--shadow-card)]",
            )}
          >
            <Icon />
          </Button>
        );
      })}
    </div>
  );
}
