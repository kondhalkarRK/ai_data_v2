"use client";

import { Pin, Link2, Copy, Download, Star } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type ActionKey = "pin" | "share" | "copy" | "export" | "save";

interface ActionDef {
  key: ActionKey;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  /** When false, button is disabled with Coming soon tooltip. */
  enabled: boolean;
}

export function ActionToolbar({
  className,
  onAction,
  enabled = { copy: true, export: true, save: true, pin: false, share: false },
}: {
  className?: string;
  onAction: (key: ActionKey) => void;
  enabled?: Partial<Record<ActionKey, boolean>>;
}) {
  const actions: ActionDef[] = [
    { key: "pin", label: "Pin", icon: Pin, enabled: Boolean(enabled.pin) },
    { key: "share", label: "Share", icon: Link2, enabled: Boolean(enabled.share) },
    { key: "copy", label: "Copy", icon: Copy, enabled: enabled.copy !== false },
    { key: "export", label: "Export", icon: Download, enabled: enabled.export !== false },
    { key: "save", label: "Save Insight", icon: Star, enabled: enabled.save !== false },
  ];

  return (
    <div className={cn("flex flex-wrap items-center justify-end gap-1", className)}>
      {actions.map(({ key, label, icon: Icon, enabled: isEnabled }) => (
        <Button
          key={key}
          type="button"
          size="sm"
          variant="ghost"
          className="h-8 gap-1.5 px-2 text-xs text-muted-foreground"
          disabled={!isEnabled}
          title={isEnabled ? label : "Coming soon"}
          aria-label={isEnabled ? label : `${label} (coming soon)`}
          onClick={() => {
            if (isEnabled) onAction(key);
          }}
        >
          <Icon className="size-3.5" />
          <span className="hidden sm:inline">{label}</span>
        </Button>
      ))}
    </div>
  );
}
