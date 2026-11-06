import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/use-session", () => ({ useActiveIndustry: () => "automotive" }));

import { HomeStory } from "@/components/home/home-story";

describe("Home product story", () => {
  it("moves through three truthful, keyboard-accessible chapters", async () => {
    const user = userEvent.setup();
    render(<HomeStory />);
    expect(screen.getByRole("heading", { name: "Ask naturally. Understand precisely." })).toBeInTheDocument();
    expect(screen.getByText(/Illustrative product walkthrough/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show Auto Report" }));
    expect(screen.getByRole("heading", { name: "Turn one question into a report worth sharing." })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Ask naturally. Understand precisely." })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next chapter" }));
    expect(screen.getByRole("heading", { name: "See the change. Check the evidence. Decide." })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Executive Intelligence/ })).toHaveAttribute("href", "/dashboard");
    expect(screen.getByRole("link", { name: "Explore Data Trust" })).toHaveAttribute("href", "/data-quality");
  });
});
