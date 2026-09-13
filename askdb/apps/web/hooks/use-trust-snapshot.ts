"use client";

import { useQuery } from "@tanstack/react-query";

import type { TrustSnapshot } from "@/components/trust/types";
import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";

export function useTrustSnapshot(enabled = true) {
  const industry = useActiveIndustry();
  return useQuery({
    queryKey: ["trust-snapshot", industry],
    enabled,
    staleTime: 60_000,
    queryFn: () => apiClient.get<TrustSnapshot>("/api/v1/trust/snapshot", { industry }),
  });
}
