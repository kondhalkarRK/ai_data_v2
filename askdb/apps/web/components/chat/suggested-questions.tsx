"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function SuggestedQuestions({
  items,
  disabled,
  onSelect,
  className,
}: {
  items: string[];
  disabled?: boolean;
  onSelect: (question: string) => void;
  className?: string;
}) {
  if (!items.length) return null;
  return (
    <div className={cn("space-y-2", className)}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        Suggested follow-ups
      </p>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <Button
            key={item}
            type="button"
            size="sm"
            variant="secondary"
            className="h-8 rounded-full text-xs"
            disabled={disabled}
            onClick={() => onSelect(item)}
          >
            {item}
          </Button>
        ))}
      </div>
    </div>
  );
}
