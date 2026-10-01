"use client";

import type { WeeklyUsage } from "@nql/shared-types";
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";

export const myUsageKey = ["my-usage"] as const;

/** The signed-in user's AI usage this week (Monday 00:00 UTC onwards). */
export function useMyUsage() {
  return useQuery({
    queryKey: myUsageKey,
    queryFn: () => apiClient.get<WeeklyUsage>("/api/v1/auth/me/usage"),
    staleTime: 15_000,
  });
}

function limit(value: unknown, fallback: number): string {
  return (typeof value === "number" ? value : fallback).toLocaleString("en-US");
}

/** The friendly message shown when the weekly allowance is spent. */
export function quotaMessage(details?: Record<string, unknown>): string {
  return [
    "Weekly AI quota reached.",
    `Token Limit: ${limit(details?.tokenLimit, 60_000)}/week`,
    `Call Limit: ${limit(details?.callLimit, 50)}/week`,
    "Please contact your administrator.",
  ].join("\n");
}
