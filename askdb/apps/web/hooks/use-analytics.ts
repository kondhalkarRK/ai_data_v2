"use client";

import type {
  AnalyticsAssistResponse,
  AnalyticsRunResponse,
  AnalyticsSpec,
  FilterValuesResponse,
  SavedAnalysis,
} from "@nql/shared-types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";

export const EMPTY_SPEC: AnalyticsSpec = {
  metrics: [],
  dimensions: [],
  filters: [],
  analysis: "basic",
  limit: 25,
  orderDirection: "desc",
  timeGrain: null,
  viz: "auto",
};

export function useAnalyticsRun() {
  const industry = useActiveIndustry();
  return useMutation({
    mutationFn: (spec: AnalyticsSpec) =>
      apiClient.post<AnalyticsRunResponse>("/api/v1/analytics/run", { spec }, { industry }),
  });
}

export function useAnalyticsAssist() {
  const industry = useActiveIndustry();
  return useMutation({
    mutationFn: (prompt: string) =>
      apiClient.post<AnalyticsAssistResponse>(
        "/api/v1/analytics/assist",
        { prompt },
        { industry },
      ),
  });
}

export function useFilterValues(
  domain: string | null,
  opts?: { q?: string; parentDomain?: string; parentValues?: string[] },
) {
  const industry = useActiveIndustry();
  const params = new URLSearchParams();
  if (domain) params.set("domain", domain);
  if (opts?.q) params.set("q", opts.q);
  if (opts?.parentDomain) params.set("parent_domain", opts.parentDomain);
  for (const value of opts?.parentValues ?? []) {
    params.append("parent_values", value);
  }
  return useQuery({
    queryKey: ["analytics-filter-values", industry, domain, opts?.q, opts?.parentDomain, opts?.parentValues],
    enabled: Boolean(domain),
    queryFn: () =>
      apiClient.get<FilterValuesResponse>(
        `/api/v1/analytics/filter-values?${params.toString()}`,
        { industry },
      ),
    staleTime: 5 * 60_000,
  });
}

export function useSavedAnalyses() {
  const industry = useActiveIndustry();
  return useQuery({
    queryKey: ["saved-analyses", industry],
    queryFn: () =>
      apiClient.get<SavedAnalysis[]>("/api/v1/analytics/analyses", { industry }),
  });
}

export function useSavedAnalysisMutations() {
  const industry = useActiveIndustry();
  const client = useQueryClient();
  const invalidate = () =>
    void client.invalidateQueries({ queryKey: ["saved-analyses", industry] });

  const create = useMutation({
    mutationFn: (body: {
      title: string;
      spec: AnalyticsSpec;
      sqlSnapshot?: string | null;
      viz?: string;
    }) => apiClient.post<SavedAnalysis>("/api/v1/analytics/analyses", body, { industry }),
    onSuccess: invalidate,
  });

  const update = useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: string;
      title?: string;
      spec?: AnalyticsSpec;
      sqlSnapshot?: string | null;
      viz?: string;
    }) =>
      apiClient.patch<SavedAnalysis>(`/api/v1/analytics/analyses/${id}`, body, {
        industry,
      }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: string) =>
      apiClient.delete(`/api/v1/analytics/analyses/${id}`, { industry }),
    onSuccess: invalidate,
  });

  const duplicate = useMutation({
    mutationFn: (id: string) =>
      apiClient.post<SavedAnalysis>(
        `/api/v1/analytics/analyses/${id}/duplicate`,
        {},
        { industry },
      ),
    onSuccess: invalidate,
  });

  return { create, update, remove, duplicate };
}
