import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginForm } from "@/components/auth/login-form";
import { Logo } from "@/components/brand/logo";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <main
      id="main-content"
      className="flex min-h-dvh items-center justify-center bg-surface-sunken p-6"
    >
      <div className="w-full max-w-sm">
        <div className="mb-7 flex flex-col items-center gap-3 text-center">
          <Logo size="lg" withTagline />
          <p className="text-sm text-muted-foreground">
            Ask your data anything — grounded in your semantic layer.
          </p>
        </div>
        {/* The form reads the `next` query parameter, which opts it out of static
            rendering unless it sits behind a boundary. */}
        <Suspense fallback={<Skeleton className="h-64 w-full" />}>
          <LoginForm />
        </Suspense>
        <p className="mt-6 text-center text-xs text-muted-foreground">
          Accounts are provisioned by an administrator. There is no self-service sign-up.
        </p>
      </div>
    </main>
  );
}
