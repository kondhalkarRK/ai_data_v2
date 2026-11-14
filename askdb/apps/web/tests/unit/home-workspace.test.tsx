import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ push: vi.fn(), get: vi.fn(), industry: "automotive" as "automotive" | "insurance" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("@/lib/api-client", () => ({ apiClient: { get: mocks.get } }));
vi.mock("@/hooks/use-session", () => ({
  useSession: () => ({ data: { id: "user-1", fullName: "Rahul Test", username: "rahul" } }),
  useActiveIndustry: () => mocks.industry,
  useRegionAccess: () => ({ unrestricted: false, hideRegionFilter: false, label: "West" }),
}));
import { HomeWorkspace } from "@/components/home/home-workspace";

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><HomeWorkspace /></QueryClientProvider>);
}
beforeEach(() => {
  mocks.push.mockReset(); mocks.get.mockReset(); mocks.industry = "automotive";
  mocks.get.mockImplementation(async (url: string) => {
    if (url.endsWith("/industries")) return { industries: [{ id: "automotive", label: "Automotive", databaseAvailable: true, semanticPackLoaded: true }] };
    if (url === "/ready") return { status: "ready", checkedAt: "2026-11-14T09:00:00Z", dependencies: [] };
    throw new Error(`Unexpected API: ${url}`);
  });
});

describe("Home workspace", () => {
  it("greets the user and submits suggestions through the existing chat flow", async () => {
    const user = userEvent.setup(); mount();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/Good (morning|afternoon|evening), Rahul/);
    await user.click(screen.getByRole("button", { name: "Revenue by month" }));
    expect(mocks.push).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(mocks.push).toHaveBeenCalledTimes(1); expect(mocks.push).toHaveBeenCalledWith("/chat?q=Revenue%20by%20month");
  });
  it("shows checked statuses, opens scoped details and refreshes both existing checks", async () => {
    const user = userEvent.setup(); mount();
    const chip = await screen.findByRole("button", { name: "PostgreSQL · Connected" });
    expect(screen.queryByRole("region", { name: "Connection details" })).not.toBeInTheDocument();
    await user.click(chip);
    expect(screen.getByRole("region", { name: "Connection details" })).toHaveTextContent("West");
    expect(screen.getByRole("button", { name: "API · Ready" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Last checked");
    mocks.get.mockClear();
    await user.click(screen.getByRole("button", { name: "Refresh connections" }));
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("Start with a task")).not.toBeInTheDocument();
    expect(screen.queryByText("Continue your work")).not.toBeInTheDocument();
  });
  it("never presents failed checks as connected and keeps questions usable", async () => {
    mocks.get.mockRejectedValue(new Error("API unavailable")); mount();
    await screen.findByRole("button", { name: "PostgreSQL · Unavailable" });
    expect(screen.getByRole("button", { name: "API · Unavailable" })).toBeInTheDocument();
    expect(screen.queryByText(/Last checked/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "  Claims by region  " } });
    fireEvent.submit(screen.getByRole("textbox").closest("form")!);
    expect(mocks.push).toHaveBeenCalledWith("/chat?q=Claims%20by%20region");
  });
  it("shows disconnected and degraded states and insurance suggestions", async () => {
    mocks.industry = "insurance";
    mocks.get.mockImplementation(async (url: string) => url === "/ready" ? { status: "degraded", dependencies: [] } : { industries: [{ id: "insurance", databaseAvailable: false }] });
    mount();
    await screen.findByRole("button", { name: "PostgreSQL · Disconnected" });
    expect(screen.getByRole("button", { name: "API · Degraded" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Insurance · Active" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Premium by month" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revenue by month" })).not.toBeInTheDocument();
  });
});

