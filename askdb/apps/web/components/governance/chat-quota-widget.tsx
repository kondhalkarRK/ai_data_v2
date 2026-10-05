"use client";

import { Gauge } from "lucide-react";
import Link from "next/link";

import { useMyUsage } from "@/hooks/use-my-usage";
import { cn } from "@/lib/utils";

function MiniMeter({ label, used, limit }: { label: string; used: number; limit: number }) {
  const pct = limit > 0 ? Math.min((used / limit) * 100, 100) : 0;
  const tone = pct >= 100 ? "bg-danger" : pct >= 80 ? "bg-warning" : "bg-primary";
  return (
    <div className="w-32 space-y-1 sm:w-36">
      <div className="flex items-baseline justify-between gap-2 text-[11px] leading-none">
        <span className="font-medium text-foreground">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {used.toLocaleString("en-US")} / {limit.toLocaleString("en-US")}
        </span>
      </div>
      <div
        className="h-1.5 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label={`${label} used this week`}
        aria-valuemin={0}
        aria-valuemax={limit}
        aria-valuenow={used}
      >
        <div className={cn("h-full rounded-full transition-[width]", tone)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/** Weekly AI quota at a glance, shown in the AI Chat header. */
export function ChatQuotaWidget() {
  const usage = useMyUsage();
  const data = usage.data;
  if (!data) return null;

  if (data.unlimited || (data.callLimit === null && data.tokenLimit === null)) {
    return (
      <span className="hidden items-center gap-1.5 rounded-full border border-border/70 px-2.5 py-1 text-[11px] text-muted-foreground sm:inline-flex">
        <Gauge className="size-3.5" aria-hidden="true" />
        Unlimited AI usage
      </span>
    );
  }

  return (
    <Link
      href="/profile"
      title="Weekly AI quota used. Resets every Monday 00:00 UTC."
      className="flex items-center gap-3 rounded-[var(--radius-control)] border border-border/70 bg-surface-raised/80 px-3 py-1.5 transition-colors hover:bg-muted/40"
    >
      <Gauge className="hidden size-4 text-muted-foreground sm:block" aria-hidden="true" />
      {data.callLimit !== null ? <MiniMeter label="Calls" used={data.callsUsed} limit={data.callLimit} /> : null}
      {data.tokenLimit !== null ? <MiniMeter label="Tokens" used={data.tokensUsed} limit={data.tokenLimit} /> : null}
    </Link>
  );
}
