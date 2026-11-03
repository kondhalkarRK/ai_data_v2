import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const setTheme = vi.fn();

vi.mock("next-themes", () => ({
  useTheme: () => ({ theme: "light", setTheme, resolvedTheme: "light" }),
}));

import { ThemeToggle } from "@/components/shell/theme-toggle";

describe("ThemeToggle", () => {
  beforeEach(() => {
    setTheme.mockClear();
  });

  it("exposes Light, Dark, and AI theme options", () => {
    render(<ThemeToggle />);
    expect(screen.getByRole("radio", { name: "Light theme" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Dark theme" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "AI theme" })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "System theme" })).not.toBeInTheDocument();
  });

  it("selects the AI theme without a page reload", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);
    await user.click(screen.getByRole("radio", { name: "AI theme" }));
    expect(setTheme).toHaveBeenCalledWith("ai");
  });
});
