import type { Metadata } from "next";

import { MarketDashboard } from "@/components/MarketDashboard";
import { PageIntro } from "@/components/PageIntro";
import {
  catalogueContrast,
  depreciation,
  manifest,
  mileageEffect,
  regionalEffect,
  retainedValue,
} from "@/lib/results";

export const metadata: Metadata = { title: "Mercado" };

/**
 * Read at build time, not fetched.
 *
 * These tables are committed files (`docs/results/`, written by `make results`), so there
 * is nothing to gain from asking the API for them at runtime and a minute of cold start to
 * lose. The page is therefore instant and works with the service asleep.
 */
export default function MarketPage() {
  return (
    <>
      <PageIntro page="market" />
      <div className="mx-auto w-full max-w-[1120px] px-5 pb-20 sm:px-6">
      <MarketDashboard
        manifest={manifest()}
        depreciation={depreciation()}
        retained={retainedValue()}
        mileage={mileageEffect()}
        regional={regionalEffect()}
        contrast={catalogueContrast()}
      />
      </div>
    </>
  );
}
