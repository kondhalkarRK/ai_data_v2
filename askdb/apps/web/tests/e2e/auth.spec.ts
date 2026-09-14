import { expect, test, type Page } from "@playwright/test";

/**
 * Phase 1 acceptance (spec section 22): sign in, sign out, theme, and the shell.
 *
 * Requires a running API and a seeded account. Create one with:
 *   python askdb/scripts/create_admin.py --email e2e@nql.local --full-name "E2E"
 * then export E2E_EMAIL and E2E_PASSWORD.
 */
const EMAIL = process.env.E2E_EMAIL ?? "";
const PASSWORD = process.env.E2E_PASSWORD ?? "";

test.skip(!EMAIL || !PASSWORD, "E2E_EMAIL and E2E_PASSWORD must be set.");

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/home/);
}

test("an unauthenticated visitor is sent to the login page", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
  // The intended destination survives the redirect.
  expect(page.url()).toContain("next=%2Fdashboard");
});

test("signing in lands on the workspace and shows the shell", async ({ page }) => {
  await signIn(page);
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Workspace" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ask DB." })).toBeVisible();
});

test("a wrong password is rejected without saying which field was wrong", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill("definitely-not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("alert")).toHaveText("Incorrect email or password.");
  await expect(page).toHaveURL(/\/login/);
});

test("signing out clears the session and blocks the back button", async ({ page }) => {
  await signIn(page);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);

  await page.goBack();
  await expect(page).toHaveURL(/\/login/);
});

test("the theme toggle applies immediately and survives a reload", async ({ page }) => {
  await signIn(page);
  const html = page.locator("html");

  await page.getByRole("radio", { name: "Dark theme" }).first().click();
  await expect(html).toHaveClass(/dark/);

  await page.reload();
  await expect(html).toHaveClass(/dark/);
});

test("the theme toggle stays within the 50 ms interaction budget", async ({ page }) => {
  await signIn(page);
  const toggle = page.getByRole("radio", { name: "Dark theme" }).first();

  const elapsed = await page.evaluate(async () => {
    const button = document.querySelector<HTMLElement>('[role="radio"][aria-label="Dark theme"]');
    const started = performance.now();
    button?.click();
    // One frame is enough: the change is a class swap, not a re-render or a fetch.
    await new Promise((resolve) => requestAnimationFrame(resolve));
    return performance.now() - started;
  });

  await expect(toggle).toHaveAttribute("aria-checked", "true");
  expect(elapsed).toBeLessThan(50);
});

test("the sidebar collapses and the choice is remembered", async ({ page }) => {
  await signIn(page);
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible();
});
