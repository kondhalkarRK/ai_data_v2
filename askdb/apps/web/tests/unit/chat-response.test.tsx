import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { InsightSummary } from "@/components/chat/insight-summary";
import { TrustIndicators } from "@/components/chat/trust-indicators";

function wrap(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("chat trust indicators", () => {
  it("shows grounded badges without a fabricated confidence score", () => {
    wrap(
      <TrustIndicators
        groundedOn={["Semantic Layer", "Business Glossary"]}
        ambiguityFlag={false}
      />,
    );
    expect(screen.getByText("Semantic Layer")).toBeInTheDocument();
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument();
  });

  it("surfaces ambiguity instead of silent certainty", async () => {
    const user = userEvent.setup();
    const onClarify = vi.fn();
    wrap(
      <TrustIndicators
        groundedOn={[]}
        ambiguityFlag
        alternates={["Show by region"]}
        onClarify={onClarify}
      />,
    );
    expect(screen.getByText(/ambiguous/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show by region" }));
    expect(onClarify).toHaveBeenCalledWith("Show by region");
  });
});

describe("insight depth toggle", () => {
  it("switches executive and analyst copy without refetch", async () => {
    const user = userEvent.setup();
    const onDepthChange = vi.fn();
    render(
      <InsightSummary
        executive="Exec summary"
        analyst="Analyst breakdown"
        depth="executive"
        onDepthChange={onDepthChange}
      />,
    );
    expect(screen.getByText("Exec summary")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "analyst" }));
    expect(onDepthChange).toHaveBeenCalledWith("analyst");
  });
});
