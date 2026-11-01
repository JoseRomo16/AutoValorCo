import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { THEME_SCRIPT, ThemeProvider, useTheme } from "@/components/ThemeProvider";

/**
 * The theme in its three states, and the one combination that was broken in production:
 * "Auto" with the system in dark.
 *
 * What makes that case worth a test rather than a screenshot is that it fails invisibly.
 * The tokens come out dark either way — dark is the `:root` default — so the page looks
 * almost right; what breaks is every `dark:` utility in the older components, because the
 * variant keys off `[data-theme="dark"]` and "Auto" used to leave the attribute off. So
 * the assertion is on the attribute, not on any colour: the attribute is the contract
 * between the provider and the stylesheet.
 */

const STORAGE_KEY = "autovalor.theme";

type Scheme = "light" | "dark";

/**
 * jsdom ships no `matchMedia`, so one is installed here — and it has to be a real fake,
 * not a stub returning `false`: half of what is under test is whether the provider follows
 * the system *after* the first paint.
 */
function installMatchMedia(initial: Scheme) {
  let scheme: Scheme = initial;
  const lists = new Set<{ query: string; notify: Set<(event: MediaQueryListEvent) => void> }>();

  const matches = (query: string): boolean =>
    query.includes("dark") ? scheme === "dark" : scheme === "light";

  window.matchMedia = ((query: string) => {
    const notify = new Set<(event: MediaQueryListEvent) => void>();
    const entry = { query, notify };
    lists.add(entry);
    const list = {
      get matches() {
        return matches(query);
      },
      media: query,
      onchange: null,
      addEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) =>
        notify.add(listener),
      removeEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) =>
        notify.delete(listener),
      // The pre-2018 API, because the inline head script uses whatever is shortest.
      addListener: (listener: (event: MediaQueryListEvent) => void) => notify.add(listener),
      removeListener: (listener: (event: MediaQueryListEvent) => void) => notify.delete(listener),
      dispatchEvent: () => true,
    };
    return list as unknown as MediaQueryList;
  }) as typeof window.matchMedia;

  return {
    set(next: Scheme) {
      scheme = next;
      for (const entry of lists) {
        const event = { matches: matches(entry.query), media: entry.query } as MediaQueryListEvent;
        for (const listener of entry.notify) listener(event);
      }
    },
  };
}

function Probe() {
  const { theme, resolved } = useTheme();
  return (
    <>
      <span data-testid="preference">{theme}</span>
      <span data-testid="resolved">{resolved}</span>
    </>
  );
}

function stamped() {
  const root = document.documentElement;
  return { theme: root.dataset.theme, preference: root.dataset.themePref };
}

beforeEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
  delete document.documentElement.dataset.themePref;
});

afterEach(() => {
  window.localStorage.clear();
});

describe("ThemeProvider", () => {
  it("stamps an explicit light choice and ignores the system", () => {
    installMatchMedia("dark");
    window.localStorage.setItem(STORAGE_KEY, "light");

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(stamped()).toEqual({ theme: "light", preference: "light" });
    expect(screen.getByTestId("resolved")).toHaveTextContent("light");
  });

  it("stamps an explicit dark choice and ignores the system", () => {
    installMatchMedia("light");
    window.localStorage.setItem(STORAGE_KEY, "dark");

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(stamped()).toEqual({ theme: "dark", preference: "dark" });
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark");
  });

  // The regression: "Auto" is the default, so this is what most visitors got.
  it("resolves auto to dark when the system is dark", () => {
    installMatchMedia("dark");
    window.localStorage.setItem(STORAGE_KEY, "auto");

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(stamped()).toEqual({ theme: "dark", preference: "auto" });
    // The toggle still has to read "Auto": resolving the theme is not choosing one.
    expect(screen.getByTestId("preference")).toHaveTextContent("auto");
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark");
  });

  it("resolves auto to light when the system is light", () => {
    installMatchMedia("light");
    window.localStorage.setItem(STORAGE_KEY, "auto");

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(stamped()).toEqual({ theme: "light", preference: "auto" });
  });

  it("defaults to auto with nothing stored, and still stamps a real theme", () => {
    installMatchMedia("dark");

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(screen.getByTestId("preference")).toHaveTextContent("auto");
    expect(stamped().theme).toBe("dark");
  });

  it("follows the system while on auto, after the first paint", () => {
    const media = installMatchMedia("dark");
    window.localStorage.setItem(STORAGE_KEY, "auto");

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(stamped().theme).toBe("dark");

    act(() => media.set("light"));

    expect(stamped()).toEqual({ theme: "light", preference: "auto" });
    expect(screen.getByTestId("resolved")).toHaveTextContent("light");
  });

  it("ignores a system change once a theme was chosen explicitly", () => {
    const media = installMatchMedia("dark");
    window.localStorage.setItem(STORAGE_KEY, "dark");

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    act(() => media.set("light"));

    expect(stamped().theme).toBe("dark");
  });

  it("never leaves data-theme empty, whichever preference is stored", () => {
    for (const preference of ["light", "auto", "dark", "nonsense"]) {
      installMatchMedia("dark");
      window.localStorage.setItem(STORAGE_KEY, preference);

      const view = render(
        <ThemeProvider>
          <Probe />
        </ThemeProvider>,
      );

      expect(stamped().theme, `preference ${preference}`).toMatch(/^(light|dark)$/);
      view.unmount();
    }
  });
});

describe("THEME_SCRIPT", () => {
  /**
   * The inline script is a string, so neither `tsc` nor ESLint ever looks at it, and it is
   * the only thing that runs before the first paint: if it disagrees with the provider the
   * page flashes the wrong theme on every load. These tests are the only check it has.
   */
  const run = () => {
    new Function(THEME_SCRIPT)();
  };

  it("stamps the resolved theme for auto before React runs", () => {
    installMatchMedia("dark");
    window.localStorage.setItem(STORAGE_KEY, "auto");

    run();

    expect(stamped()).toEqual({ theme: "dark", preference: "auto" });
  });

  it("stamps an explicit choice", () => {
    installMatchMedia("dark");
    window.localStorage.setItem(STORAGE_KEY, "light");

    run();

    expect(stamped()).toEqual({ theme: "light", preference: "light" });
  });

  it("stamps a real theme on a first visit", () => {
    installMatchMedia("light");

    run();

    expect(stamped()).toEqual({ theme: "light", preference: "auto" });
  });

  it("survives localStorage throwing, as it does in private mode", () => {
    installMatchMedia("dark");
    const original = window.localStorage.getItem;
    window.localStorage.getItem = () => {
      throw new Error("denied");
    };

    expect(run).not.toThrow();
    window.localStorage.getItem = original;
  });
});
