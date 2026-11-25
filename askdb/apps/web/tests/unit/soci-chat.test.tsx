import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  profile: { id: "owner", fullName: "Anita Sharma", role: "admin", regionAccess: { unrestricted: true, zones: [] }, capabilities: { ragEnabled: true } },
  get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));
vi.mock("@/hooks/use-session", () => ({ useActiveIndustry: () => "automotive", useSession: () => ({ data: mocks.profile }) }));
vi.mock("@/lib/api-client", () => ({ apiClient: { get: mocks.get, post: mocks.post, put: mocks.put, delete: mocks.delete }, API_BASE_URL: "", ApiError: class extends Error {} }));
vi.mock("@/components/governance/chat-quota-widget", () => ({ ChatQuotaWidget: () => null }));

import { ChatModeShell } from "@/components/chat/chat-mode-shell";
import { chatGreeting } from "@/lib/chat-greeting";
import { BrandWordmark } from "@/components/brand/wordmark";

const frames = [
  { event: "stage", data: { stage: "accepted", historyId: "response-1" } },
  { event: "token", data: { token: "Hello Anita" } },
  { event: "meta", data: { rowCount: 0 } },
  { event: "done", data: { historyId: "response-1", conversationId: "conversation-1" } },
];
beforeEach(() => {
  window.localStorage.clear(); window.sessionStorage.clear();
  mocks.profile = { id: "owner", fullName: "Anita Sharma", role: "admin", regionAccess: { unrestricted: true, zones: [] }, capabilities: { ragEnabled: true } };
  mocks.get.mockReset().mockImplementation(async (path: string) => {
    if (path === "/api/v1/chat/conversations") return { items: [{ id: "conversation-1", title: "Earlier chat", updatedAt: "2026-11-23T10:00:00Z" }], hasMore: false };
    if (path === "/api/v1/chat/conversations/conversation-1") return { id: "conversation-1", hasMore: false, turns: [{ responseId: "response-1", question: "Hello", canRate: true, rating: { rating: "up", reason: null, note: null }, events: frames }] };
    return { feedback: null };
  });
  mocks.post.mockReset().mockResolvedValue({ events: frames });
  mocks.put.mockReset().mockImplementation(async (_path, value) => ({ feedback: value }));
  mocks.delete.mockReset().mockResolvedValue({ feedback: null });
});

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><ChatModeShell enabled /></QueryClientProvider>);
  return { ...view, client, user: userEvent.setup(), renderAgain: () => view.rerender(<QueryClientProvider client={client}><ChatModeShell enabled /></QueryClientProvider>) };
}

it("renders Scio as one word and derives greetings only from the authenticated name", () => {
  render(<BrandWordmark />);
  expect(screen.getByLabelText("Scio").textContent).toBe("Scio");
  expect(chatGreeting("  Anita  Sharma ")).toBe("Hi, Anita");
  expect(chatGreeting(" ")).toBe("Hi there.");
  expect(chatGreeting(null)).toBe("Hi there.");
});

it("shares conversation, draft, mode choices and ratings across layouts", async () => {
  const e = setup();
  expect(await screen.findByText("Hi, Anita")).toBeInTheDocument();
  const input = screen.getByRole("textbox", { name: "Ask a question" });
  await e.user.type(input, "Hello");
  await e.user.click(screen.getByRole("checkbox", { name: "Web retrieval" }));
  await e.user.click(screen.getByRole("button", { name: "Ask" }));
  expect(await screen.findByText("Hello Anita")).toBeInTheDocument();
  expect(screen.queryByTestId("chat-greeting")).not.toBeInTheDocument();
  expect(mocks.post.mock.calls[0]![1].webRetrieval).toBe(true);
  await e.user.type(screen.getByRole("textbox"), "Unsent draft");
  await e.user.click(await screen.findByRole("button", { name: "Thumbs up" }));
  await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(1));
  await e.user.click(screen.getByRole("button", { name: "New" }));
  expect(screen.getByText("Hello Anita")).toBeInTheDocument();
  expect(screen.getByRole("textbox")).toHaveValue("Unsent draft");
  expect(screen.getByRole("checkbox", { name: "Web retrieval" })).toBeChecked();
  expect(screen.getByRole("button", { name: "Thumbs up" })).toHaveAttribute("aria-pressed", "true");
  expect(mocks.post).toHaveBeenCalledTimes(1);
});

it("history is hidden initially, restores focus, keeps drafts and opens persisted ratings", async () => {
  window.localStorage.setItem("askMeChatMode", "new");
  const e = setup();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await e.user.type(screen.getByRole("textbox"), "Keep this draft");
  const trigger = screen.getByRole("button", { name: "Chat history" });
  await e.user.click(trigger);
  const panel = await screen.findByRole("dialog", { name: "Chat history" });
  expect(await within(panel).findByText("Earlier chat")).toBeInTheDocument();
  await e.user.keyboard("{Escape}");
  expect(trigger).toHaveFocus();
  expect(screen.getByRole("textbox")).toHaveValue("Keep this draft");
  await e.user.click(trigger);
  await e.user.click(await screen.findByRole("button", { name: /Earlier chat/ }));
  expect(await screen.findByText("Hello Anita")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Thumbs up" })).toHaveAttribute("aria-pressed", "true");
  await e.user.click(screen.getByRole("button", { name: "New chat" }));
  expect(screen.getByRole("textbox")).toHaveValue("Keep this draft");
  expect(mocks.post).not.toHaveBeenCalled();
});

it("thumbs down persists optional feedback, supports removal and rolls back failed saves", async () => {
  const e = setup();
  await e.user.type(screen.getByRole("textbox"), "Hello{Enter}");
  await e.user.click(await screen.findByRole("button", { name: "Thumbs down" }));
  const form = screen.getByRole("dialog", { name: "Help improve this answer" });
  await e.user.selectOptions(within(form).getByRole("combobox"), "incorrect");
  await e.user.type(within(form).getByRole("textbox"), "Check the total");
  await e.user.click(within(form).getByRole("button", { name: "Save feedback" }));
  await waitFor(() => expect(mocks.put).toHaveBeenCalledWith(expect.stringContaining("response-1"), { rating: "down", reason: "incorrect", note: "Check the total" }, { industry: "automotive" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  await e.user.click(screen.getByRole("button", { name: "Thumbs down" }));
  await e.user.click(screen.getByRole("button", { name: "Remove rating" }));
  await waitFor(() => expect(mocks.delete).toHaveBeenCalledTimes(1));
  mocks.put.mockRejectedValueOnce(new Error("offline"));
  await e.user.click(screen.getByRole("button", { name: "Thumbs up" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("could not be saved");
  expect(screen.getByRole("button", { name: "Thumbs up" })).toHaveAttribute("aria-pressed", "false");
  expect(mocks.post).toHaveBeenCalledTimes(1);
});

it("switching signed-in accounts clears the previous conversation and updates the greeting", async () => {
  const e = setup();
  await e.user.type(screen.getByRole("textbox"), "Hello{Enter}");
  expect(await screen.findByText("Hello Anita")).toBeInTheDocument();
  mocks.profile = { ...mocks.profile, id: "another-owner", fullName: "Bala Rao" };
  e.renderAgain();
  expect(await screen.findByText("Hi, Bala")).toBeInTheDocument();
  expect(screen.queryByText("Hello Anita")).not.toBeInTheDocument();
  mocks.profile = { ...mocks.profile, fullName: " " };
  e.renderAgain();
  expect(screen.getByText("Hi there.")).toBeInTheDocument();
});

it("keeps an in-flight request and the next draft when the layout changes", async () => {
  let finish!: () => void;
  mocks.post.mockReturnValueOnce(new Promise(resolve => { finish = () => resolve({ events: frames }); }));
  const e = setup();
  await e.user.type(screen.getByRole("textbox"), "Hello{Enter}");
  expect(await screen.findByRole("button", { name: "Cancel" })).toBeInTheDocument();
  await e.user.type(screen.getByRole("textbox"), "My next question");
  await e.user.click(screen.getByRole("button", { name: "New" }));
  expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  await act(async () => { finish(); });
  expect(await screen.findByText("Hello Anita")).toBeInTheDocument();
  expect(screen.getByRole("textbox")).toHaveValue("My next question");
  expect(mocks.post).toHaveBeenCalledTimes(1);
});
