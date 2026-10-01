import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/login-form";
import type * as apiClientModule from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";

type ApiClientModule = typeof apiClientModule;

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(),
}));

const login = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<ApiClientModule>();
  return { ...actual, apiClient: { ...actual.apiClient, post: login } };
});

function renderForm() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <LoginForm />
    </QueryClientProvider>,
  );
}

function apiError(status: number, code: string) {
  return new ApiError(status, { code, message: "internal detail", requestId: "r1", details: {} });
}

describe("LoginForm", () => {
  it("submits the trimmed username, the password as typed, and Remember me", async () => {
    login.mockResolvedValueOnce({ user: { id: "1" }, csrfToken: "t", accessExpiresAt: "" });
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText("Username"), "  user1  ");
    await user.type(screen.getByLabelText("Password"), " Pa55word! ");
    await user.click(screen.getByRole("button", { name: "Login" }));

    await waitFor(() => expect(login).toHaveBeenCalledTimes(1));
    expect(login).toHaveBeenCalledWith(
      "/api/v1/auth/login",
      // Whitespace around a username is a typing artefact; inside a password it is content.
      { username: "user1", password: " Pa55word! ", rememberMe: true },
      { skipRefresh: true },
    );
  });

  it("reports a bad password without revealing whether the account exists", async () => {
    login.mockRejectedValueOnce(apiError(401, "invalid_credentials"));
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText("Username"), "nobody");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Login" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Incorrect username or password.");
    expect(alert).not.toHaveTextContent("internal detail");
    expect(screen.getByLabelText("Username")).toHaveAttribute("aria-invalid", "true");
  });

  it("distinguishes rate limiting, because the user must wait rather than retype", async () => {
    login.mockRejectedValueOnce(apiError(429, "rate_limited"));
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText("Username"), "user1");
    await user.type(screen.getByLabelText("Password"), "Pa55word!");
    await user.click(screen.getByRole("button", { name: "Login" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
  });

  it("sends rememberMe false when the box is unticked", async () => {
    login.mockResolvedValueOnce({ user: { id: "1" }, csrfToken: "t", accessExpiresAt: "" });
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText("Username"), "admin");
    await user.type(screen.getByLabelText("Password"), "secret");
    await user.click(screen.getByLabelText("Remember me"));
    await user.click(screen.getByRole("button", { name: "Login" }));

    await waitFor(() => expect(login).toHaveBeenCalledTimes(1));
    expect(login.mock.calls[0]?.[1]).toMatchObject({ username: "admin", rememberMe: false });
  });

  it("toggles password visibility and announces the toggle state", async () => {
    const user = userEvent.setup();
    renderForm();

    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("type", "password");

    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");

    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
  });
});
