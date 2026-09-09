"use client";

import type {
  OntologySnapshot,
  SemanticPackResponse,
  SemanticPackSummary,
} from "@nql/shared-types";
import { useQuery } from "@tanstack/react-query";

import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";

export function useSemanticPacks() {
  return useQuery({
    queryKey: ["semantic-packs"],
    queryFn: () => apiClient.get<SemanticPackSummary[]>("/api/v1/semantic/packs"),
  });
}

export function useSemanticPack() {
  const industry = useActiveIndustry();
  return useQuery({
    queryKey: ["semantic-pack", industry],
    queryFn: () =>
      apiClient.get<SemanticPackResponse>("/api/v1/semantic/pack", { industry }),
  });
}

export function useOntologySnapshot() {
  const industry = useActiveIndustry();
  return useQuery({
    queryKey: ["ontology-snapshot", industry],
    queryFn: () =>
      apiClient.get<OntologySnapshot>("/api/v1/semantic/ontology", { industry }),
    // This is an immutable deployment artifact. Industry is part of the key, so switching
    // back opens instantly without fetching or rebuilding.
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: 30 * 60_000,
  });
}
