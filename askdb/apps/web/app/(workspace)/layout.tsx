"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

import { AppBootLoading } from "@/components/loading/loading-state";
import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { useSession } from "@/hooks/use-session";

/**
 * The authenticated shell.
 *
 * Middleware already blocks unauthenticated navigation, but the session is re-checked
 * here because a cookie can expire while the tab sits open. Rendering the shell around a
 * user who is no longer signed in would produce a screen full of 401s.
 */
export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data: user, isPending, isError } = useSession();

  React.useEffect(() => {
    if (!isPending && !user) router.replace("/login");
  }, [isPending, user, router]);

  if (isPending) return <AppBootLoading />;

  if (isError) {
    return (
      <div className="flex min-h-dvh items-center justify-center p-6">
        <div className="card-surface max-w-md p-6 text-center">
          <h1 className="text-lg font-semibold">Cannot reach the server</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            The API did not respond. This is a connectivity problem, not a sign-out — your
            session is intact. Retry once the service is back.
          </p>
        </div>
      </div>
    );
  }

  // The redirect above is in flight.
  if (!user) return <AppBootLoading />;

  return (
    <div className="flex min-h-dvh">
      <Sidebar user={user} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main id="main-content" className="min-w-0 flex-1 p-4 lg:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
