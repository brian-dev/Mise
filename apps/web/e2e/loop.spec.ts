import { expect, test } from "@playwright/test";

// E2E smoke test for the core loop. Uses the test-only seed hook
// (/v1/test/seed-plan) so we reach "has a plan" instantly WITHOUT calling Claude
// — fast, deterministic, free. Requires the AI service running with
// MISE_TEST_MODE=true and the local Supabase stack up.

const API = process.env.E2E_API_URL ?? "http://localhost:8000";

test("sign up, seed a plan, see it, cook a meal", async ({ page }) => {
  const email = `e2e-${Date.now()}@mise.test`;

  // 1. Sign up through the UI. New users land on the (required) onboarding wizard.
  await page.goto("/");
  await page.getByTestId("login-email").fill(email);
  await page.getByTestId("login-password").fill("password123");
  await page.getByTestId("login-signup").click();
  await expect(page.getByTestId("onboarding-next")).toBeVisible();

  // 2. Seed a household + plan deterministically via the test hook (also marks
  //    onboarding complete), using the signed-in session token from the browser.
  const seeded = await page.evaluate(async (api) => {
    const raw = localStorage.getItem(
      Object.keys(localStorage).find((k) => k.endsWith("-auth-token"))!,
    )!;
    const token = JSON.parse(raw).access_token as string;
    const res = await fetch(`${api}/v1/test/seed-plan`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    return res.json();
  }, API);
  expect(seeded.meal_plan_id).toBeTruthy();

  // 3. Reload — onboarding is complete, so the app loads. Confirm we're signed in,
  //    select the seeded household, then open the Plan tab (its plan loads).
  await page.reload();
  await expect(page.getByTestId("user-email")).toHaveText(email);
  await page
    .getByTestId("household-select")
    .selectOption({ label: "E2E Household" });
  await page.getByTestId("nav-plan").click();
  await expect(page.getByTestId("recipe-title")).toHaveText("E2E Test Dinner");

  // 4. Cook the meal → it shows as cooked.
  await page.getByTestId("cook").first().click();
  await expect(page.getByTestId("cooked").first()).toBeVisible();

  // 5. Build the shopping list, open the Shopping tab → an estimated total appears.
  await page.getByTestId("build-shopping").click();
  await page.getByTestId("nav-shopping").click();
  await expect(page.getByTestId("shopping-list")).toBeVisible();
  await expect(page.getByTestId("estimated-total")).toContainText("$");
});
