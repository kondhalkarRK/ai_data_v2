import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/chat/chat-workspace", () => ({
  ChatWorkspace: () => <div data-testid="classic" />,
}));
vi.mock("@/components/chat/new-chat-workspace", () => ({
  NewChatWorkspace: () => <div data-testid="new-chat" />,
}));

import { ChatModeShell } from "@/components/chat/chat-mode-shell";

describe("ChatModeShell", () => {
  beforeEach(() => window.localStorage.clear());

  it("flag off: only Classic, no toggle, stored preference ignored", () => {
    window.localStorage.setItem("askMeChatMode", "new");
    render(<ChatModeShell enabled={false} />);
    expect(screen.getByTestId("classic")).toBeInTheDocument();
    expect(screen.queryByTestId("new-chat")).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /chat experience/i })).not.toBeInTheDocument();
  });

  it("flag on: defaults to Classic and switches, remembering the choice", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<ChatModeShell enabled />);
    expect(await screen.findByTestId("classic")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New" }));
    expect(screen.getByTestId("new-chat")).toBeInTheDocument();
    expect(window.localStorage.getItem("askMeChatMode")).toBe("new");
    unmount();

    render(<ChatModeShell enabled />);
    expect(await screen.findByTestId("new-chat")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Classic" }));
    expect(screen.getByTestId("classic")).toBeInTheDocument();
  });
});
