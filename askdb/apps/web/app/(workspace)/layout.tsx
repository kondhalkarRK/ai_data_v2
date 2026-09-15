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
  const { data: user, isPending, isError, error } = useSession();
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
    const detail =
      error instanceof Error && error.message
        ? error.message
        : "The API did not respond.";
    return (
      <div className="flex min-h-dvh items-center justify-center p-6">
        <div className="card-surface max-w-md p-6 text-center">
          <h1 className="text-lg font-semibold">Cannot reach the server</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            This is a connectivity / backend problem, not a sign-out — your session is
            intact. Retry once Postgres and the API are healthy.
          </p>
          <p className="mt-3 rounded-md bg-muted/60 px-3 py-2 text-left text-xs text-muted-foreground">
            {detail}
          </p>
          <p className="mt-3 text-left text-xs text-muted-foreground">
            Check <code className="text-[11px]">http://127.0.0.1:8000/ready</code> and
            confirm <code className="text-[11px]">askdb/.env</code> DB passwords match
            bootstrap (<code className="text-[11px]">askdb_app</code> /{" "}
            <code className="text-[11px]">askdb_reader</code>).
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
    <div className={presenterMode ? "flex h-dvh presenter-mode" : "flex h-dvh overflow-hidden"}>
      {presenterMode ? null : <Sidebar user={user} />}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <Topbar />
        <main
          id="main-content"
          className={
            presenterMode
              ? "min-h-0 min-w-0 flex-1 overflow-auto bg-surface/40 p-6 lg:p-10"
              : "min-h-0 min-w-0 flex-1 overflow-auto bg-surface/40 p-4 lg:p-6"
          }
        >
          {children}
        </main>
      </div>
      <CommandPalette />
    </div>
  );
}
