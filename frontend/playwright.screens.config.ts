import { defineConfig } from "@playwright/test";

import base from "./playwright.config";

/**
 * The screenshot set: every view × theme × width, written to `screens-out/` (or
 * `SCREENS_DIR`). Separate from the e2e config so the regression job does not pay for
 * eighty full-page captures; CI runs it as its own step and uploads the set.
 */
export default defineConfig({
  ...base,
  testDir: "screens",
  retries: 0,
  reporter: "list",
});
