"use client";

import { BarChart3, Code2, MessageSquareText, Table2 } from "lucide-react";
import * as React from "react";

import type { ResponseTab } from "@/components/chat/types";
import { cn } from "@/lib/utils";

const TABS: Array<{
  id: ResponseTab;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { id: "table", label: "Table", icon: Table2 },
  { id: "chart", label: "Chart", icon: BarChart3 },
  { id: "narration", label: "Narration", icon: MessageSquareText },
  { id: "sql", label: "SQL", icon: Code2 },
];

export function ResponseTabs({
  value,
  onChange,
  className,
}: {
  value: ResponseTab;
  onChange: (tab: ResponseTab) => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "inline-flex max-w-full overflow-x-auto rounded-[var(--radius-control)] border border-border bg-muted/40 p-0.5",
        className,
      )}
      role="tablist"
      aria-label="Response view"
    >
      {TABS.map(({ id, label, icon: Icon }) => {
        const active = value === id;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={active}
            className={cn(
              "inline-flex shrink-0 items-center gap-1.5 rounded-[calc(var(--radius-control)-2px)] px-3 py-1.5 text-xs font-medium transition-colors",
              active
                ? "border border-primary/25 bg-surface-raised text-foreground shadow-sm"
                : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
            )}
            onClick={() => onChange(id)}
          >
            <Icon className="size-3.5" />
            {label}
          </button>
        );
      })}
    </div>
  );
}
