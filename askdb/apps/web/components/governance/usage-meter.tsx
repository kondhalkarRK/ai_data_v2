import { cn } from "@/lib/utils";

function fmt(value: number): string {
  return value.toLocaleString("en-US");
}

/** Used vs. limit with a progress bar; `limit === null` means unlimited. */
export function UsageMeter({
  label,
  used,
  limit,
  unit,
  compact,
}: {
  label: string;
  used: number;
  limit: number | null;
  unit: string;
  compact?: boolean;
}) {
  const pct = limit ? Math.min((used / limit) * 100, 100) : 0;
  const tone = pct >= 100 ? "bg-danger" : pct >= 80 ? "bg-warning" : "bg-primary";
  const remaining = limit === null ? null : Math.max(limit - used, 0);

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className={cn("font-medium text-foreground", compact ? "text-xs" : "text-sm")}>
          {label}
        </span>
        <span className="text-xs tabular-nums text-muted-foreground">
          {fmt(used)} / {limit === null ? "Unlimited" : fmt(limit)} {unit}
        </span>
      </div>
      <div
        className={cn("overflow-hidden rounded-full bg-muted", compact ? "h-1.5" : "h-2.5")}
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={limit ?? undefined}
        aria-valuenow={used}
      >
        <div
          className={cn("h-full rounded-full transition-[width]", limit === null ? "bg-success/60" : tone)}
          style={{ width: limit === null ? "100%" : `${pct}%` }}
        />
      </div>
      {compact ? null : (
        <p className="text-xs text-muted-foreground">
          {remaining === null ? "No weekly limit for administrators." : `${fmt(remaining)} ${unit} remaining`}
        </p>
      )}
    </div>
  );
}
