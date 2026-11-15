import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));
vi.mock("@/hooks/use-session", () => ({ useActiveIndustry: () => "automotive" }));
vi.mock("@/lib/api-client", () => ({
  apiClient: { post: mocks.post }, API_BASE_URL: "", ApiError: class extends Error {},
}));
import { useChatAsk } from "@/hooks/use-chat-ask";

beforeEach(() => mocks.post.mockReset().mockResolvedValue({ events: [] }));

it("defaults documents off and snapshots the mode on each submitted question", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const { result } = renderHook(() => useChatAsk(), { wrapper });
  await act(async () => { await result.current.runAsk("How do I escalate a delayed delivery?"); });
  expect(mocks.post.mock.calls[0]![1].useDocuments).toBe(false);
  act(() => result.current.setUseDocuments(true));
  await act(async () => { await result.current.runAsk("What does the policy say?"); });
  expect(mocks.post.mock.calls[1]![1].useDocuments).toBe(true);
  expect(result.current.messages.filter(m => m.role === "user").map(m => m.documentsEnabled)).toEqual([false, true]);
  expect(mocks.post.mock.calls[1]![2].signal).toBeInstanceOf(AbortSignal);
});
