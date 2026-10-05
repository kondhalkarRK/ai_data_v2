import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  AiGovernancePanel,
  AuditCenterPanel,
  GovernanceDashboardPanel,
  LlmUsagePanel,
  SemanticAdminPanel,
  TrustAdminPanel,
} from "@/components/admin/admin-panels";
import { EntityCatalogAdminPanel } from "@/components/admin/entity-catalog-admin";
import type * as apiClientModule from "@/lib/api-client";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/admin",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/components/shell/industry-switcher", () => ({ IndustrySwitcher: () => null }));

const get = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof apiClientModule>();
  return { ...actual, apiClient: { ...actual.apiClient, get } };
});

const CURRENT = {
  provider: "openai",
  providerLabel: "OpenAI",
  model: "openai.gpt-5-mini",
  temperature: 0.2,
  maxTokens: 600,
  updatedAt: null,
  updatedBy: null,
};

const WEEK_USAGE = {
  days: 7,
  kpis: { totalLlmCalls: 3, totalTokens: 20000, mostUsedModel: "openai.gpt-5-mini", activeUsers: 1 },
  topUsers: [],
  users: [
    {
      userId: "u1",
      user: "admin",
      role: "admin",
      calls: 14,
      llmCalls: 3,
      tokens: 20000,
      avgResponseMs: 900,
      weekTokens: 20000,
      weekCalls: 14,
      tokenLimit: 60000,
      callLimit: 100,
    },
  ],
  models: [],
};

const RESPONSES: Record<string, unknown> = {
  "/api/v1/auth/me": { id: "u1", username: "admin", role: "admin", defaultIndustry: "automotive" },
  "/api/v1/auth/me/usage": {
    tokenLimit: 60000,
    tokensUsed: 18250,
    tokensRemaining: 41750,
    callLimit: 100,
    callsUsed: 14,
    callsRemaining: 86,
    unlimited: false,
    weekStart: "2026-10-05T00:00:00Z",
    resetsAt: "2026-10-12T00:00:00Z",
  },
  "/api/v1/admin/usage?days=7": WEEK_USAGE,
  "/api/v1/admin/llm": {
    current: CURRENT,
    providers: [
      {
        id: "openai",
        label: "OpenAI",
        configured: true,
        models: [
          { id: "openai.gpt-5-mini", label: "GPT-5 mini", tier: "medium", inputUsdPer1m: 0.25, outputUsdPer1m: 2 },
        ],
      },
      {
        id: "ollama",
        label: "Ollama",
        configured: true,
        models: [{ id: "llama3.1", label: "Llama 3.1", tier: "small", inputUsdPer1m: 0, outputUsdPer1m: 0 }],
      },
    ],
    pricing: {
      inputTokensPerQuestion: 2000,
      outputTokensPerQuestion: 500,
      monthlyBudgetUsd: 50,
      source: "config/llm_catalog.py",
    },
  },
  "/api/v1/admin/governance?days=30": {
    days: 30,
    kpis: {
      totalQuestions: 3,
      schemaQueries: 1,
      llmQueries: 1,
      hybridQueries: 1,
      cachedQueries: 0,
      avgResponseMs: 1200,
    },
    distribution: [
      { mode: "SCHEMA", count: 1 },
      { mode: "LLM", count: 1 },
      { mode: "HYBRID", count: 1 },
      { mode: "CACHE", count: 0 },
    ],
    dailyTrend: [{ date: "2026-10-05", SCHEMA: 1, LLM: 1, HYBRID: 1, CACHE: 0 }],
    byUser: [{ user: "admin", total: 3, SCHEMA: 1, LLM: 1, HYBRID: 1, CACHE: 0 }],
    recent: [
      {
        id: "r1",
        user: "admin",
        question: "Top 5 dealers",
        mode: "SCHEMA",
        responseMs: 900,
        createdAt: "2026-10-05T06:00:00Z",
      },
    ],
    llm: CURRENT,
  },
  "/api/v1/admin/usage?days=30": {
    days: 30,
    kpis: { totalLlmCalls: 1, totalTokens: 2500, mostUsedModel: "openai.gpt-5-mini", activeUsers: 1 },
    topUsers: [],
    users: [
      {
        userId: "u2",
        user: "user1",
        role: "user",
        calls: 2,
        llmCalls: 1,
        tokens: 2500,
        avgResponseMs: 1500,
        weekTokens: 2500,
        weekCalls: 2,
        tokenLimit: 60000,
        callLimit: 50,
      },
    ],
    models: [{ model: "openai.gpt-5-mini", calls: 1 }],
  },
  "/api/v1/admin/audit": {
    items: [{ id: "a1", user: "admin", action: "USER_LOGIN", details: null, createdAt: "2026-10-05T06:00:00Z" }],
    counts: { logins: 1 },
    categories: ["logins"],
  },
  "/api/v1/admin/dq/rules": [
    { id: "r1", name: "Not null", dimension: "completeness", dataset: "fact_sales", severity: "high", enabled: true, custom: false },
  ],
  "/api/v1/catalog/summary": {
    industry: "automotive",
    lastRefresh: null,
    lastCompleted: { finishedAt: "2026-10-05T05:00:00Z", status: "completed", newValueCount: 2 },
    catalogVersion: 3,
    rowsProcessed: 100,
    lastLoadId: "load-42",
    totalEntities: 2,
    totalValues: 30,
    newValues: 2,
    schemaDrift: { status: "stable", label: "Stable", count: 0 },
    aiCoverage: 1,
    entityReadiness: {},
    available: true,
    unavailableReason: null,
  },
  "/api/v1/catalog/entities": [
    { key: "make", label: "Make", group: "Vehicle", distinctValues: 18, newValues: 2, lastUpdated: "2026-10-05T05:00:00Z" },
    { key: "city", label: "City", group: "Geography", distinctValues: 70, newValues: 0, lastUpdated: null },
  ],
};

function renderPanel(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  get.mockReset();
  get.mockImplementation(async (path: string) => {
    if (path in RESPONSES) return RESPONSES[path];
    throw new Error(`unexpected GET ${path}`);
  });
});

describe("Admin Center panels render without crashing", () => {
  it("LLM Settings shows model economics and the admin's weekly usage", async () => {
    renderPanel(<AiGovernancePanel />);
    expect(await screen.findByText("LLM Cost & Usage Intelligence")).toBeInTheDocument();
    // GPT-5 mini: (0.25 × 2,000 + 2 × 500) / 1M = $0.0015 per question.
    expect(screen.getByText("$0.0015")).toBeInTheDocument();
    expect(screen.getByText("~666")).toBeInTheDocument();
    expect(screen.getByText("~6,666")).toBeInTheDocument();
    expect(screen.getByText("~33,333")).toBeInTheDocument();
    expect(await screen.findByText("86")).toBeInTheDocument();
    expect(screen.getByText("41,750")).toBeInTheDocument();
    // 20,000 team tokens at the blended $0.60 / 1M.
    expect(await screen.findByText("$0.01")).toBeInTheDocument();
  });

  it("LLM Settings survives an API that predates the catalog payload", async () => {
    get.mockImplementation(async (path: string) =>
      path === "/api/v1/admin/llm"
        ? { current: CURRENT, providers: [{ id: "openai", label: "OpenAI", configured: true, models: ["openai.gpt-5-mini"] }] }
        : RESPONSES[path],
    );
    renderPanel(<AiGovernancePanel />);
    expect(await screen.findByText("Change LLM settings")).toBeInTheDocument();
    expect(screen.getByText(/has no pricing/)).toBeInTheDocument();
  });

  it("Hybrid AI dashboard", async () => {
    renderPanel(<GovernanceDashboardPanel />);
    expect(await screen.findByText("Top 5 dealers")).toBeInTheDocument();
  });

  it("LLM Usage", async () => {
    renderPanel(<LlmUsagePanel />);
    expect(await screen.findByText("user1")).toBeInTheDocument();
  });

  it("Audit Center", async () => {
    renderPanel(<AuditCenterPanel />);
    expect(await screen.findByText("USER_LOGIN")).toBeInTheDocument();
  });

  it("Data Trust Admin", async () => {
    renderPanel(<TrustAdminPanel />);
    expect(await screen.findByText("Not null")).toBeInTheDocument();
  });

  it("Semantic Admin", () => {
    renderPanel(<SemanticAdminPanel />);
    expect(screen.getByText("Refresh Knowledge Graph")).toBeInTheDocument();
  });

  it("Entity Catalog (Admin)", async () => {
    renderPanel(<EntityCatalogAdminPanel />);
    expect(await screen.findByText("Make")).toBeInTheDocument();
    expect(screen.getByText("load-42")).toBeInTheDocument();
    expect(screen.getByText("+2")).toBeInTheDocument();
  });
});
