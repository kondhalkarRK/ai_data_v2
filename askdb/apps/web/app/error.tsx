"use client";

import { RotateCcw } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";

/**
 * Route-level error boundary.
 *
 * The message is never rendered: in production it can carry internals, and the digest is
 * enough to find the matching structured log entry on the server.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  React.useEffect(() => {
    console.error("Route error", error.digest ?? error.name);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="card-surface max-w-md p-6 text-center">
        <h1 className="text-lg font-semibold tracking-tight">Something went wrong</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          This view failed to render. Nothing was changed on the server.
        </p>
        {error.digest ? (
          <p className="mt-3 font-mono text-xs text-muted-foreground">
            Reference {error.digest}
          </p>
        ) : null}
        <Button onClick={reset} className="mt-4">
          <RotateCcw />
          Try again
        </Button>
      </div>
    </div>
  );
}
