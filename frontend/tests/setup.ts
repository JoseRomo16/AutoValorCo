import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

/**
 * Testing Library unmounts between tests on its own only when `afterEach` is a global.
 * Tests here import their hooks, so the teardown is registered once from here instead —
 * without it, every render would stack another `<html>` mutation on the previous one and
 * the theme assertions would read a stale attribute.
 */
afterEach(cleanup);
