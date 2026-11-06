import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/use-session", () => ({ useActiveIndustry: () => "automotive" }));

import { HomeStory } from "@/components/home/home-story";

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

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
  it("lets the answer sequence settle before auto-advancing", () => {
    vi.useFakeTimers();
    render(<HomeStory />);
    act(() => vi.advanceTimersByTime(9000));
    expect(screen.getByRole("heading", { name: "Ask naturally. Understand precisely." })).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(500));
    expect(screen.getByRole("heading", { name: "Turn one question into a report worth sharing." })).toBeInTheDocument();
  });
  it("keeps the final scene available without auto-advance for reduced motion", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    vi.useFakeTimers();
    render(<HomeStory />);
    expect(screen.getByRole("region", { name: "Ask Me product story" })).toHaveAttribute("data-story-paused", "true");
    expect(screen.getByText(/West 12% · South 8%/)).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(30000));
    expect(screen.getByRole("heading", { name: "Ask naturally. Understand precisely." })).toBeInTheDocument();
  });
  it("pauses on hover and resumes after the pointer leaves", () => {
    vi.useFakeTimers();
    render(<HomeStory />);
    const story = screen.getByRole("region", { name: "Ask Me product story" });
    fireEvent.mouseEnter(story);
    expect(story).toHaveAttribute("data-story-paused", "true");
    act(() => vi.advanceTimersByTime(15000));
    expect(screen.getByRole("heading", { name: "Ask naturally. Understand precisely." })).toBeInTheDocument();
    fireEvent.mouseLeave(story);
    expect(story).toHaveAttribute("data-story-paused", "false");
    act(() => vi.advanceTimersByTime(9500));
    expect(screen.getByRole("heading", { name: "Turn one question into a report worth sharing." })).toBeInTheDocument();
  });
  it("stays paused while a story control retains keyboard focus", () => {
    vi.useFakeTimers();
    render(<HomeStory />);
    const story = screen.getByRole("region", { name: "Ask Me product story" });
    fireEvent.mouseEnter(story);
    fireEvent.focus(screen.getByRole("button", { name: "Next chapter" }));
    fireEvent.mouseLeave(story);
    expect(story).toHaveAttribute("data-story-paused", "true");
    act(() => vi.advanceTimersByTime(15000));
    expect(screen.getByRole("heading", { name: "Ask naturally. Understand precisely." })).toBeInTheDocument();
  });
});
