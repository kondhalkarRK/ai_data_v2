"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";

export type ExecutionMode = "SCHEMA" | "LLM" | "HYBRID" | "CACHE";
export const EXECUTION_MODES: ExecutionMode[] = ["SCHEMA", "LLM", "HYBRID", "CACHE"];

export interface LlmConfig {
  provider: string;
  providerLabel: string;
  model: string;
  temperature: number;
  maxTokens: number;
  updatedAt: string | null;
  updatedBy: string | null;
}

export interface CatalogModel {
  id: string;
  label: string;
  tier: string;
  /** Indicative USD per 1M tokens; null when the model is not priced in the catalog. */
  inputUsdPer1m: number | null;
  outputUsdPer1m: number | null;
}

export interface ProviderOption {
  id: string;
  label: string;
  configured: boolean;
  models: CatalogModel[];
}

export interface LlmPricingAssumptions {
  inputTokensPerQuestion: number;
  outputTokensPerQuestion: number;
  /** Monthly AI budget from the API settings (LLM_MONTHLY_BUDGET_USD). */
  monthlyBudgetUsd: number;
  source: string;
}

export interface LlmSettingsResponse {
  current: LlmConfig;
  providers: ProviderOption[];
  pricing: LlmPricingAssumptions;
}

type ModeCounts = Record<ExecutionMode, number>;

export interface GovernanceOverview {
  days: number;
  kpis: {
    totalQuestions: number;
    schemaQueries: number;
    llmQueries: number;
    hybridQueries: number;
    cachedQueries: number;
    avgResponseMs: number | null;
  };
  distribution: Array<{ mode: ExecutionMode; count: number }>;
  dailyTrend: Array<{ date: string } & ModeCounts>;
  byUser: Array<{ user: string; total: number } & ModeCounts>;
  recent: Array<{
    id: string;
    user: string;
    question: string | null;
    mode: ExecutionMode;
    responseMs: number | null;
    createdAt: string;
  }>;
  llm: LlmConfig;
}

export interface UsageRow {
  userId: string;
  user: string;
  role: "admin" | "user";
  calls: number;
  llmCalls: number;
  tokens: number;
  avgResponseMs: number | null;
  weekTokens: number;
  weekCalls: number;
  tokenLimit: number | null;
  callLimit: number | null;
}

export interface UsageOverview {
  days: number;
  kpis: {
    totalLlmCalls: number;
    totalTokens: number;
    mostUsedModel: string | null;
    activeUsers: number;
  };
  topUsers: UsageRow[];
  users: UsageRow[];
  models: Array<{ model: string; calls: number }>;
}

export interface AuditItem {
  id: string;
  user: string | null;
  action: string;
  details: string | null;
  createdAt: string;
}

export interface AuditResponse {
  items: AuditItem[];
  counts: Record<string, number>;
  categories: string[];
}

export interface DqRule {
  id: string;
  name: string;
  dimension: string;
  dataset: string;
  severity: string;
  enabled: boolean;
  custom: boolean;
}

export interface AdminActionResult {
  ok: boolean;
  action: string;
  message: string;
}

const ADMIN = ["admin"] as const;

const DEFAULT_PRICING: LlmPricingAssumptions = {
  inputTokensPerQuestion: 2000,
  outputTokensPerQuestion: 500,
  monthlyBudgetUsd: 50,
  source: "config/llm_catalog.py",
};

type RawProvider = Omit<ProviderOption, "models"> & { models?: Array<CatalogModel | string> };
type RawLlmSettings = Omit<LlmSettingsResponse, "providers" | "pricing"> & {
  providers?: RawProvider[];
  pricing?: Partial<LlmPricingAssumptions>;
};

/** Fills gaps so the page renders even against an API that predates the catalog payload. */
export function normalizeLlmSettings(raw: RawLlmSettings): LlmSettingsResponse {
  return {
    current: raw.current,
    providers: (raw.providers ?? []).map((provider) => ({
      ...provider,
      models: (provider.models ?? []).map((model) =>
        typeof model === "string"
          ? { id: model, label: model, tier: "", inputUsdPer1m: null, outputUsdPer1m: null }
          : model,
      ),
    })),
    pricing: { ...DEFAULT_PRICING, ...raw.pricing },
  };
}

export function useLlmSettings() {
  return useQuery({
    queryKey: [...ADMIN, "llm"],
    queryFn: async () =>
      normalizeLlmSettings(await apiClient.get<RawLlmSettings>("/api/v1/admin/llm")),
  });
}

export function useUpdateLlmSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Pick<LlmConfig, "provider" | "model" | "temperature" | "maxTokens">) =>
      normalizeLlmSettings(await apiClient.put<RawLlmSettings>("/api/v1/admin/llm", body)),
    onSuccess: (data) => {
      queryClient.setQueryData([...ADMIN, "llm"], data);
      void queryClient.invalidateQueries({ queryKey: [...ADMIN, "audit"] });
      void queryClient.invalidateQueries({ queryKey: [...ADMIN, "governance"] });
    },
  });
}

export function useGovernance(days: number) {
  return useQuery({
    queryKey: [...ADMIN, "governance", days],
    queryFn: () =>
      apiClient.get<GovernanceOverview>(`/api/v1/admin/governance?days=${days}`),
    refetchInterval: 30_000,
  });
}

export function useUsageOverview(days: number) {
  return useQuery({
    queryKey: [...ADMIN, "usage", days],
    queryFn: () => apiClient.get<UsageOverview>(`/api/v1/admin/usage?days=${days}`),
    refetchInterval: 30_000,
  });
}

export function useAudit(category: string | null) {
  return useQuery({
    queryKey: [...ADMIN, "audit", category],
    queryFn: () =>
      apiClient.get<AuditResponse>(
        `/api/v1/admin/audit${category ? `?category=${encodeURIComponent(category)}` : ""}`,
      ),
  });
}

export function useDqRules() {
  const industry = useActiveIndustry();
  return useQuery({
    queryKey: [...ADMIN, "dq-rules", industry],
    queryFn: () => apiClient.get<DqRule[]>("/api/v1/admin/dq/rules", { industry }),
  });
}

/** Runs one admin action (refresh / toggle) and refreshes the views it affects. */
export function useAdminAction() {
  const industry = useActiveIndustry();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ path, body }: { key: string; path: string; body?: unknown }) =>
      apiClient.post<AdminActionResult>(`/api/v1/admin/${path}`, body ?? {}, { industry }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...ADMIN, "audit"] });
      void queryClient.invalidateQueries({ queryKey: [...ADMIN, "dq-rules", industry] });
      void queryClient.invalidateQueries({ queryKey: ["data-reliability", industry] });
      void queryClient.invalidateQueries({ queryKey: ["trust-snapshot", industry] });
    },
  });
}
