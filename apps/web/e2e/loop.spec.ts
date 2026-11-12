import { expect, test, type Page } from "@playwright/test";

// E2E smoke test for the core loop. Uses the test-only seed hook
// (/v1/test/seed-plan) so we reach "has a plan" instantly WITHOUT calling Claude
// — fast, deterministic, free. Requires the AI service running with
// MISE_TEST_MODE=true and the local Supabase stack up.

const API = process.env.E2E_API_URL ?? "http://localhost:8000";

/** Sign up a fresh user, seed a household + draft plan via the test hook (no
 *  Claude), and land on the Plan tab with the seeded plan loaded. */
async function signUpAndSeed(page: Page): Promise<{ meal_plan_id: string }> {
  const email = `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@mise.test`;

  // Sign up through the UI. New users land on the (required) onboarding wizard.
  await page.goto("/");
  await page.getByTestId("login-email").fill(email);
  await page.getByTestId("login-password").fill("password123");
  await page.getByTestId("login-signup").click();
  await expect(page.getByTestId("onboarding-next")).toBeVisible();

  // Seed a household + plan deterministically via the test hook (also marks
  // onboarding complete), using the signed-in session token from the browser.
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

  // Reload — onboarding is complete, so the app loads. Confirm we're signed in,
  // select the seeded household, then open the Plan tab (its plan loads).
  await page.reload();
  await expect(page.getByTestId("user-email")).toHaveText(email);
  await page.getByTestId("household-select").selectOption({ label: "E2E Household" });
  await page.getByTestId("nav-plan").click();
  await expect(page.getByTestId("recipe-title")).toHaveText("E2E Test Dinner");
  return seeded;
}

test("sign up, seed a plan, see it, cook a meal", async ({ page }) => {
  await signUpAndSeed(page);
  // A freshly seeded plan is a draft.
  await expect(page.getByTestId("plan-status")).toHaveAttribute("data-status", "draft");

  // Cook the meal → it shows as cooked, and cooking started the plan.
  await page.getByTestId("cook").first().click();
  await expect(page.getByTestId("cooked").first()).toBeVisible();
  await expect(page.getByTestId("plan-status")).toHaveAttribute("data-status", "active");

  // Build the shopping list, open the Shopping tab → an estimated total appears.
  await page.getByTestId("build-shopping").click();
  await page.getByTestId("nav-shopping").click();
  await expect(page.getByTestId("shopping-list")).toBeVisible();
  await expect(page.getByTestId("estimated-total")).toContainText("$");
});

test("plan lifecycle: start a draft, then close it", async ({ page }) => {
  await signUpAndSeed(page);
  await expect(page.getByTestId("plan-draft-hint")).toBeVisible();

  await page.getByTestId("plan-activate").click();
  await expect(page.getByTestId("plan-status")).toHaveAttribute("data-status", "active");
  await expect(page.getByTestId("plan-activate")).toHaveCount(0);

  // Closing asks for confirmation, then the plan drops out of view.
  page.once("dialog", (d) => void d.accept());
  await page.getByTestId("plan-close").click();
  await expect(page.getByTestId("recipe-title")).toHaveCount(0);
  await expect(page.getByTestId("generate")).toBeVisible();
});
