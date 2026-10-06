"use client";

import { CalendarClock } from "lucide-react";

import { UsageMeter } from "@/components/governance/usage-meter";
import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { PageShell } from "@/components/ui/page-shell";
import { EmptyState, StatusPill } from "@/components/ui/status-pill";
import { useMyUsage } from "@/hooks/use-my-usage";
import { useSession } from "@/hooks/use-session";

function formatDay(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ProfilePage() {
  const { data: user } = useSession();
  const usage = useMyUsage();

  return (
    <PageShell className="max-w-3xl">
      <PageHeader
        title="My AI Usage"
        description="Your AI Chat usage for the current week. Only you and administrators can see it."
      />

      {user ? (
        <Card className="mb-5">
          <CardContent className="flex flex-wrap items-center gap-x-8 gap-y-3 pt-5 text-sm">
            <div>
              <CardDescription>Username</CardDescription>
              <p className="font-medium text-foreground">{user.username}</p>
            </div>
            <div>
              <CardDescription>Name</CardDescription>
              <p className="font-medium text-foreground">{user.fullName}</p>
            </div>
            <div>
              <CardDescription>Role</CardDescription>
              <StatusPill tone={user.role === "admin" ? "info" : "neutral"} label={user.role.toUpperCase()} />
            </div>
            <div>
              <CardDescription>Region access</CardDescription>
              <p className="font-medium text-foreground">
                {user.regionAccess?.unrestricted
                  ? "All regions"
                  : (user.regionAccess?.zones ?? []).join(", ") || "Restricted"}
              </p>
            </div>
            {user.lastLoginAt ? (
              <div>
                <CardDescription>Last login</CardDescription>
                <p className="font-medium text-foreground">{formatDay(user.lastLoginAt)}</p>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {usage.isPending ? (
        <LoadingState title="Loading your usage" />
      ) : usage.isError || !usage.data ? (
        <EmptyState
          title="Usage is not available right now"
          detail="The usage service did not respond. AI Chat limits are still enforced on the server."
        />
      ) : (
        <Card>
          <CardContent className="space-y-6 pt-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-base">This week</CardTitle>
              <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                <CalendarClock className="size-3.5" aria-hidden="true" />
                Resets {formatDay(usage.data.resetsAt)}
              </span>
            </div>
            <UsageMeter
              label="Weekly tokens"
              used={usage.data.tokensUsed}
              limit={usage.data.tokenLimit}
              unit="tokens"
            />
            <UsageMeter
              label="Weekly AI calls"
              used={usage.data.callsUsed}
              limit={usage.data.callLimit}
              unit="calls"
            />
            {usage.data.tokensRemaining === 0 || usage.data.callsRemaining === 0 ? (
              <p className="rounded-[var(--radius-control)] border border-warning/40 bg-warning/5 px-3 py-2 text-sm text-foreground">
                Weekly AI quota reached. Please contact your administrator.
              </p>
            ) : null}
            <p className="text-xs text-muted-foreground">
              Every AI Chat question counts as one call. Answers served from the semantic layer or
              the cache use no tokens.
            </p>
          </CardContent>
        </Card>
      )}
    </PageShell>
  );
}
