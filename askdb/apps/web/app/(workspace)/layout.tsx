"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

import { AppBootLoading } from "@/components/loading/loading-state";
import { CommandPalette } from "@/components/shell/command-palette";
import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { useSession } from "@/hooks/use-session";
import { useUiStore } from "@/stores/ui-store";

/**
 * The authenticated shell.
 *
 * Middleware already blocks unauthenticated navigation, but the session is re-checked
 * here because a cookie can expire while the tab sits open. Rendering the shell around a
 * user who is no longer signed in would produce a screen full of 401s.
 *
 * TEMPORARY: NEXT_PUBLIC_AUTH_BYPASS=true relies on API AUTH_BYPASS so /auth/me still
 * returns the bootstrap admin without cookies.
 */
const AUTH_BYPASS = process.env.NEXT_PUBLIC_AUTH_BYPASS === "true";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data: user, isPending, isError } = useSession();
  const presenterMode = useUiStore((state) => state.presenterMode);
  const setSidebarCollapsed = useUiStore((state) => state.setSidebarCollapsed);

  React.useEffect(() => {
    if (AUTH_BYPASS) return;
    if (!isPending && !user) router.replace("/login");
  }, [isPending, user, router]);

  React.useEffect(() => {
    if (presenterMode) setSidebarCollapsed(true);
  }, [presenterMode, setSidebarCollapsed]);

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

  if (!user) {
    if (AUTH_BYPASS) {
      return (
        <div className="flex min-h-dvh items-center justify-center p-6">
          <div className="card-surface max-w-md p-6 text-center">
            <h1 className="text-lg font-semibold">Auth bypass is on, but /auth/me failed</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Set <code className="text-xs">AUTH_BYPASS=true</code> in the API{" "}
              <code className="text-xs">.env</code>, create an admin with{" "}
              <code className="text-xs">scripts/create_admin.py</code>, then restart the API.
            </p>
          </div>
        </div>
      );
    }
    return <AppBootLoading />;
  }

  return (
    <div className={presenterMode ? "flex min-h-dvh presenter-mode" : "flex min-h-dvh"}>
      {presenterMode ? null : <Sidebar user={user} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main
          id="main-content"
          className={
            presenterMode
              ? "min-w-0 flex-1 bg-surface/40 p-6 lg:p-10"
              : "min-w-0 flex-1 bg-surface/40 p-4 lg:p-6"
          }
        >
          {children}
        </main>
      </div>
      <CommandPalette />
    </div>
  );
}
