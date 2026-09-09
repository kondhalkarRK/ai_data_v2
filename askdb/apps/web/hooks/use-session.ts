"use client";

import type { Industry, LoginRequest, SessionResponse, UserProfile } from "@nql/shared-types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";

import { ApiError, apiClient } from "@/lib/api-client";
import { useUiStore } from "@/stores/ui-store";

export const sessionKey = ["session"] as const;

/**
 * The authenticated user, or null when signed out.
 *
 * A 401 is a valid answer here, not an error: it means "nobody is signed in". Anything
 * else is surfaced so a backend outage is not mistaken for a logout.
 */
export function useSession() {
  return useQuery<UserProfile | null>({
    queryKey: sessionKey,
    queryFn: async () => {
      try {
        return await apiClient.get<UserProfile>("/api/v1/auth/me", { skipRefresh: false });
      } catch (error) {
        if (error instanceof ApiError && error.isAuthError) return null;
        throw error;
      }
    },
    staleTime: 60_000,
    retry: (failureCount, error) =>
      error instanceof ApiError && error.isRetryable && failureCount < 2,
  });
}

/**
 * Only same-origin, absolute-path destinations are honoured after sign-in. Anything else
 * is an open-redirect waiting to happen, so it falls back to the landing tab.
 */
function safeRedirectTarget(raw: string | null): string {
  if (!raw) return "/data-preview";
  if (!raw.startsWith("/") || raw.startsWith("//")) return "/data-preview";
  if (raw.startsWith("/login")) return "/data-preview";
  return raw;
}

export function useLogin() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();

  return useMutation({
    mutationFn: (credentials: LoginRequest) =>
      apiClient.post<SessionResponse>("/api/v1/auth/login", credentials, {
        skipRefresh: true,
      }),
    onSuccess: (session) => {
      queryClient.setQueryData(sessionKey, session.user);
      router.replace(safeRedirectTarget(searchParams.get("next")));
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useMutation<void, Error, boolean>({
    mutationFn: (allSessions) =>
      apiClient.post<void>("/api/v1/auth/logout", { allSessions }, { skipRefresh: true }),
    // Runs whether or not the call succeeded: if the session is already gone the user
    // still expects to end up signed out rather than stuck.
    onSettled: () => {
      queryClient.clear();
      useUiStore.getState().setIndustryOverride(null);
      router.replace("/login");
    },
  });
}

/**
 * The industry this session is looking at.
 *
 * A per-tab override takes precedence over the saved default, so switching industry is
 * immediate and does not write to the database on every toggle.
 */
export function useActiveIndustry(): Industry {
  const { data: user } = useSession();
  const override = useUiStore((state) => state.industryOverride);
  return override ?? user?.defaultIndustry ?? "insurance";
}

export function useSetDefaultIndustry() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (industry: Industry) =>
      apiClient.patch<UserProfile>("/api/v1/auth/me/preferences", {
        defaultIndustry: industry,
      }),
    onSuccess: (user) => {
      queryClient.setQueryData(sessionKey, user);
      useUiStore.getState().setIndustryOverride(null);
    },
  });
}
