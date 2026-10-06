"use client";

import { Eye, EyeOff, Loader2 } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useLogin } from "@/hooks/use-session";
import { ApiError } from "@/lib/api-client";

/**
 * Turns a failure into something a user can act on without telling an attacker anything.
 *
 * A wrong password and an unknown username produce the same message by design; only rate
 * limiting and outages get a distinct one, because those change what the user should do.
 */
function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) {
      return "Too many attempts. Wait a minute before trying again.";
    }
    if (error.status === 401 || error.status === 403) {
      return "Incorrect username or password.";
    }
    if (error.status >= 500) {
      return "The service is unavailable. Try again shortly.";
    }
  }
  return "Sign-in failed. Check your connection and try again.";
}

export function LoginForm() {
  const login = useLogin();
  const [showPassword, setShowPassword] = React.useState(false);

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    login.mutate({
      username: String(form.get("username") ?? "").trim(),
      password: String(form.get("password") ?? ""),
      rememberMe: form.get("rememberMe") === "on",
    });
  }

  const failed = login.isError;

  return (
    <Card>
      <CardContent className="pt-5">
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <label htmlFor="username" className="text-sm font-medium text-foreground">
              Username
            </label>
            <Input
              id="username"
              name="username"
              type="text"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              required
              autoFocus
              placeholder="e.g. admin"
              aria-invalid={failed || undefined}
              aria-describedby={failed ? "login-error" : undefined}
              disabled={login.isPending}
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="password" className="text-sm font-medium text-foreground">
              Password
            </label>
            <div className="relative">
              <Input
                id="password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
                className="pr-10"
                aria-invalid={failed || undefined}
                aria-describedby={failed ? "login-error" : undefined}
                disabled={login.isPending}
              />
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setShowPassword((value) => !value)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                aria-pressed={showPassword}
                className="absolute right-0.5 top-0.5"
                tabIndex={-1}
              >
                {showPassword ? <EyeOff /> : <Eye />}
              </Button>
            </div>
          </div>

          <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              name="rememberMe"
              defaultChecked
              disabled={login.isPending}
              className="size-4 rounded border-border accent-primary"
            />
            Remember me
          </label>

          {failed ? (
            <p
              id="login-error"
              role="alert"
              className="rounded-[var(--radius-control)] bg-danger/10 px-3 py-2 text-sm text-danger"
            >
              {errorMessage(login.error)}
            </p>
          ) : null}

          <Button type="submit" className="w-full" disabled={login.isPending}>
            {login.isPending ? (
              <>
                <Loader2 className="animate-spin" aria-hidden="true" />
                Signing in
              </>
            ) : (
              "Login"
            )}
          </Button>
        </form>
        <p className="mt-4 text-[11px] leading-relaxed text-muted-foreground">
          Demo: <code>admin</code> / admin123 (all regions). Region users{" "}
          <code>user_north</code>, <code>user_south</code>, <code>user_west</code>,{" "}
          <code>user_east</code> — passwords north123, south123, west123, east123.
        </p>
      </CardContent>
    </Card>
  );
}
