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

/**
 * Two browser APIs jsdom does not implement, stubbed so a component that merely *uses*
 * them can be rendered at all.
 *
 * Deliberately inert: both answer "no" or do nothing. Any test that actually cares what
 * they report installs its own — `theme.test.tsx` builds a real fake `matchMedia`, because
 * following the system after the first paint is the thing it is testing. These exist so
 * every other test does not have to.
 */
if (!window.matchMedia) {
  window.matchMedia = ((query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => true,
    }) as unknown as MediaQueryList) as typeof window.matchMedia;
}

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
