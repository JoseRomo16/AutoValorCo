import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end regressions over the static export, against the real API.
 *
 * The API runs locally with the bundle committed in `artifacts/models/` rather than being
 * mocked: the cases under test (the floor and ranges from /catalog, the department
 * warning, a shared link re-running the model) are the service's rules, and a mock would
 * be a second copy of them that could drift without any test noticing.
 *
 * The site must be built with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` first;
 * `E2E_API_COMMAND` overrides how the API is started (CI and a local `uv` differ).
 */
const API = "http://localhost:8000";
const SITE = "http://localhost:3000";

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: { baseURL: SITE, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        process.env.E2E_API_COMMAND ??
        "uv run --no-sync uvicorn autovalor.api.main:app --port 8000",
      cwd: "..",
      url: `${API}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "node e2e/serve.mjs out",
      url: SITE,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
