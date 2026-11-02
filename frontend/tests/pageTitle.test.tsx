import { act, render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { LanguageProvider } from "@/components/LanguageProvider";
import { PageTitle } from "@/components/PageTitle";
import { copy } from "@/lib/i18n";
import type { Localized } from "@/lib/i18n";

function show(title: Localized = copy.titles.notFound) {
  return render(
    <LanguageProvider>
      <PageTitle title={title} />
    </LanguageProvider>,
  );
}

/** Switch the site the way the header does: the store, plus the event it listens to. */
function switchTo(lang: "es" | "en") {
  act(() => {
    window.localStorage.setItem("autovalor.lang", lang);
    window.dispatchEvent(new StorageEvent("storage", { key: "autovalor.lang" }));
  });
}

beforeEach(() => {
  window.localStorage.clear();
  document.title = "";
});

describe("the browser tab", () => {
  it("names the page and the site", () => {
    show();
    expect(document.title).toBe("Página no encontrada · AutoValor CO");
  });

  it("follows the language", async () => {
    show();
    switchTo("en");
    await waitFor(() => expect(document.title).toBe("Page not found · AutoValor CO"));
  });

  it("does not repeat the site name on the page named after it", () => {
    // "AutoValor CO · AutoValor CO" is not a title.
    show(copy.titles.value);
    expect(document.title).toBe(copy.site.documentTitle.es);
  });

  it("wins against something else writing the title afterwards", async () => {
    // The bug this component exists to survive: Next applies its own metadata title after
    // effects run, so a plain assignment lost the race and the tab stayed Spanish for an
    // English reader. Measured in the browser on 2026-11-02, invisible in a unit test
    // until it is written as one.
    show();
    act(() => {
      document.title = "whatever the router decided";
    });
    await waitFor(() => expect(document.title).toBe("Página no encontrada · AutoValor CO"));
  });

  it("stops correcting the title once it is gone", async () => {
    // Otherwise the observer outlives the page and fights the next one.
    const { unmount } = show();
    unmount();

    document.title = "the next page";
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(document.title).toBe("the next page");
  });
});
