import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ push: vi.fn(), get: vi.fn(), industry: "automotive" as "automotive" | "insurance" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("@/lib/api-client", () => ({ apiClient: { get: mocks.get } }));
vi.mock("@/hooks/use-session", () => ({
  useSession: () => ({ data: { id: "user-1", fullName: "Rahul Test", username: "rahul" } }),
  useActiveIndustry: () => mocks.industry,
  useRegionAccess: () => ({ unrestricted: false, zones: ["West"], hideRegionFilter: false, label: "West" }),
}));
vi.mock("@/components/home/home-story", () => ({ HomeStory: () => <div>Product tour scene</div> }));
vi.mock("@/components/home/connected-data-sources", () => ({ ConnectedDataSources: () => <div>Source details</div> }));

import { HomeWorkspace } from "@/components/home/home-workspace";

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><HomeWorkspace /></QueryClientProvider>);
}

beforeEach(() => {
  mocks.push.mockReset();
  mocks.get.mockReset();
  mocks.industry = "automotive";
  mocks.get.mockImplementation(async (url: string) => {
    if (url.endsWith("/industries")) return { industries: [{ id: "automotive", label: "Automotive", databaseAvailable: true }] };
    if (url === "/ready") return { status: "ready", checkedAt: "2026-11-10T09:00:00Z", dependencies: [] };
    if (url.endsWith("/trust/center")) return { dataAsOf: "2026-11-10T08:00:00Z", hero: { activeIncidents: 1 } };
    if (url.endsWith("/bi/capabilities")) return { enabled: true, engine: "askbi-v2", schemaVersion: 2 };
    if (url.endsWith("/questions")) return [{ id: "q1", title: "Regional sales", question: "Revenue by region", createdAt: "2026-11-09T12:00:00Z" }];
    if (url.endsWith("/bi/reports")) return [{ id: "r1", title: "CEO sales report" }];
    throw new Error(`Unexpected API: ${url}`);
  });
});
afterEach(() => vi.unstubAllEnvs());

describe("Home workspace", () => {
  it("sends a submitted question into the existing chat deep link once", async () => {
    const user = userEvent.setup();
    mount();
    expect(screen.queryByText("Product tour scene")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Revenue by month" }));
    expect(mocks.push).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: "Ask a question about your data" })).toHaveValue("Revenue by month");
    await user.click(screen.getByRole("button", { name: "Ask your data" }));
    expect(mocks.push).toHaveBeenCalledTimes(1);
    expect(mocks.push).toHaveBeenCalledWith("/chat?q=Revenue%20by%20month");
  });

  it("shows real context and owner-scoped saved work, with accurate destinations", async () => {
    vi.stubEnv("NEXT_PUBLIC_ASK_ME_ASKBI_ENABLED", "true");
    mount();
    expect((await screen.findAllByText("Database reachable")).length).toBe(2);
    expect(screen.getByText("Scope:")).toHaveTextContent("Scope:");
    expect(await screen.findByRole("link", { name: /Regional sales/ })).toHaveAttribute("href", "/chat?q=Revenue%20by%20region");
    expect(await screen.findByRole("link", { name: /CEO sales report/ })).toHaveAttribute("href", "/analytics-builder?mode=auto&askbiReport=r1");
    expect(screen.getByRole("link", { name: /Create a report/ })).toHaveAttribute("href", "/analytics-builder?mode=auto");
    expect(screen.getByRole("region", { name: "Data health" })).toHaveTextContent("Trust incidents1");
  });

  it("falls back to Custom Builder when the API disables AskBI", async () => {
    vi.stubEnv("NEXT_PUBLIC_ASK_ME_ASKBI_ENABLED", "true");
    const base = mocks.get.getMockImplementation()!;
    mocks.get.mockImplementation((url: string) => url.endsWith("/bi/capabilities") ? Promise.resolve({ enabled: false, engine: "askbi-v2", schemaVersion: 2 }) : base(url));
    mount();
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith("/api/v1/analytics/bi/capabilities", { industry: "automotive" }));
    expect(screen.getByRole("link", { name: /Create a report/ })).toHaveAttribute("href", "/analytics-builder");
    expect(mocks.get).not.toHaveBeenCalledWith("/api/v1/analytics/bi/reports", expect.anything());
  });

  it("keeps the tour optional and exposes source details only on request", async () => {
    const user = userEvent.setup();
    mount();
    expect(screen.queryByText("Product tour scene")).not.toBeInTheDocument();
    expect(screen.queryByText("Source details")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "See how Ask Me works" }));
    expect(screen.getByText("Product tour scene")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close product tour" }));
    expect(screen.queryByText("Product tour scene")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "View source details" }));
    expect(screen.getByText("Source details")).toBeInTheDocument();
  });

  it("keeps actions usable when readiness, trust and saved data fail", async () => {
    mocks.get.mockRejectedValue(new Error("API unavailable"));
    mount();
    await waitFor(() => expect(screen.getByText("Probe unavailable")).toBeInTheDocument());
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText(/Saved questions are unavailable/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Monitor performance/ })).toHaveAttribute("href", "/dashboard");
    fireEvent.change(screen.getByRole("textbox", { name: "Ask a question about your data" }), { target: { value: "  Claims by region  " } });
    fireEvent.submit(screen.getByRole("textbox", { name: "Ask a question about your data" }).closest("form")!);
    expect(mocks.push).toHaveBeenCalledWith("/chat?q=Claims%20by%20region");
  });
});
