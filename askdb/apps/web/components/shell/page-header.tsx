import * as React from "react";

import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <div className={cn("mb-5 flex items-start justify-between gap-4", className)}>
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">{title}</h1>
        {description ? (
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/**
 * Marks a route that exists and is reachable but whose feature lands in a later phase.
 *
 * Preferred over a fabricated screen: navigation, roles and layout can be verified now
 * without anyone mistaking mock content for working analytics.
 */
export function PhasePlaceholder({
  phase,
  summary,
  scope,
}: {
  phase: string;
  summary: string;
  scope: string[];
}) {
  return (
    <div className="card-surface max-w-2xl p-6">
      <span className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-0.5 text-2xs font-semibold uppercase tracking-wide text-primary">
        {phase}
      </span>
      <p className="mt-3 text-sm text-foreground">{summary}</p>
      <ul className="mt-3 space-y-1.5">
        {scope.map((entry) => (
          <li key={entry} className="flex gap-2 text-sm text-muted-foreground">
            <span aria-hidden="true" className="mt-2 size-1 shrink-0 rounded-full bg-border" />
            {entry}
          </li>
        ))}
      </ul>
    </div>
  );
}
