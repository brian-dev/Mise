import { defineConfig, devices } from "@playwright/test";

// E2E config. Assumes the stack is already running in TEST MODE:
//   - local Supabase (auth)
//   - AI service on :8000 started with MISE_TEST_MODE=true  (mounts /v1/test/*)
//   - web on :3000
// Run everything with: `pnpm test:e2e` (see package.json) which starts the web
// server for you; the API + Supabase must be up (pnpm dev, with MISE_TEST_MODE).

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // Start the web client for the test run. The API (:8000, MISE_TEST_MODE=true)
  // and Supabase must already be running.
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
