"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";
import type {
  CatalogChange,
  CatalogRefreshResult,
  CatalogSummary,
  EntityDetail,
  EntityRow,
  RefreshScope,
} from "@/lib/entity-catalog/types";

export function useCatalogSummary() {
  const industry = useActiveIndustry();
  return useQuery({
    queryKey: ["entity-catalog", industry, "summary"],
    queryFn: () => apiClient.get<CatalogSummary>("/api/v1/catalog/summary", { industry }),
  });
}

export function useCatalogEntities() {
  const industry = useActiveIndustry();
  return useQuery({
    queryKey: ["entity-catalog", industry, "entities"],
    queryFn: () => apiClient.get<EntityRow[]>("/api/v1/catalog/entities", { industry }),
  });
}

export function useCatalogEntity(key: string | null) {
  const industry = useActiveIndustry();
  return useQuery({
    queryKey: ["entity-catalog", industry, "entity", key],
    queryFn: () =>
      apiClient.get<EntityDetail>(`/api/v1/catalog/entities/${encodeURIComponent(key ?? "")}`, {
        industry,
      }),
    enabled: Boolean(key),
  });
}

export function useCatalogChanges() {
  const industry = useActiveIndustry();
  return useQuery({
    queryKey: ["entity-catalog", industry, "changes"],
    queryFn: () => apiClient.get<CatalogChange[]>("/api/v1/catalog/changes", { industry }),
  });
}

/** Refresh, then drop everything the catalog feeds: glossary, model and graph views. */
export function useCatalogRefresh() {
  const industry = useActiveIndustry();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (scope: RefreshScope) =>
      apiClient.post<CatalogRefreshResult>(
        "/api/v1/catalog/refresh",
        { scope, trigger: "manual" },
        { industry },
      ),
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["entity-catalog", industry] }),
        queryClient.invalidateQueries({ queryKey: ["semantic-pack", industry] }),
        queryClient.invalidateQueries({ queryKey: ["ontology-snapshot", industry] }),
      ]);
    },
  });
}
