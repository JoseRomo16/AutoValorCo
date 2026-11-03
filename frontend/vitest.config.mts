import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

/**
 * Unit tests for the front end.
 *
 * There was no JavaScript runner here until the theme bug: lint and `tsc` cannot catch a
 * provider that writes the wrong attribute. The scope stays narrow on purpose — behaviour
 * that lives in the browser and has no Python equivalent. Figures measured from a file are
 * still tested in pytest, where the rest of the suite is; the copy is checked here
 * (`tests/copy.test.ts`) because walking the `copy` object beats parsing TypeScript.
 *
 * `.mts` because package.json declares no module type, so a plain `.ts` config would be
 * read as CommonJS; the same reason `next.config.mjs` carries its extension.
 *
 * No `@vitejs/plugin-react`: that plugin exists for Fast Refresh, which a test run has no
 * use for, and esbuild already compiles the JSX from the `jsx` setting in tsconfig.
 */
export default defineConfig({
  resolve: {
    // The same `@/*` alias tsconfig publishes, so a test imports a component by the path
    // the component itself uses.
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
    setupFiles: ["./tests/setup.ts"],
    // Explicit imports instead of injected globals: one less thing that behaves
    // differently inside a test file than in the code under test.
    globals: false,
    restoreMocks: true,
  },
});
