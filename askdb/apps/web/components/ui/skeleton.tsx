import { cn } from "@/lib/utils";

/**
 * A content placeholder.
 *
 * Marked aria-hidden because a screen reader gains nothing from the shape; the loading
 * state is announced once by the surrounding region's aria-busy instead.
 */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "animate-[var(--animate-shimmer)] rounded-[var(--radius-control)] bg-muted",
        className,
      )}
      {...props}
    />
  );
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton
          key={index}
          className="h-3.5"
          // A slightly short last line reads as a paragraph rather than a block.
          style={{ width: index === lines - 1 ? "62%" : "100%" }}
        />
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 6, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div className="card-surface overflow-hidden" aria-busy="true">
      <div
        className="grid gap-px border-b border-border bg-border"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: columns }, (_, index) => (
          <div key={index} className="bg-surface-sunken p-3">
            <Skeleton className="h-3 w-2/3" />
          </div>
        ))}
      </div>
      {Array.from({ length: rows }, (_, rowIndex) => (
        <div
          key={rowIndex}
          className="grid gap-px bg-border"
          style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
        >
          {Array.from({ length: columns }, (_, columnIndex) => (
            <div key={columnIndex} className="bg-surface-raised p-3">
              <Skeleton className="h-3 w-4/5" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonKpiGrid({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-busy="true">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="card-surface space-y-3 p-5">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-7 w-32" />
          <Skeleton className="h-3 w-20" />
        </div>
      ))}
    </div>
  );
}
