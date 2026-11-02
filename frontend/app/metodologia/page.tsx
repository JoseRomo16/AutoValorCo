import type { Metadata } from "next";
import { PageTitle } from "@/components/PageTitle";
import { copy } from "@/lib/i18n";

import { Methodology } from "@/components/Methodology";
import { PageIntro } from "@/components/PageIntro";
import { labelGate, manifest, segmentError, servedModels } from "@/lib/results";

export const metadata: Metadata = {
  title: "Metodología",
  description:
    "Cómo se calculan los precios: de dónde salen los datos, qué modelo los estima, cuánto se equivoca y cuándo el sitio se abstiene de etiquetar.",
};

/**
 * The metrics on this page come from each vertical's `model.json` under
 * `artifacts/models/` at build time — the very files the API image serves — so the page
 * cannot quote a MAPE the deployed model does not have, and no number here is typed by
 * hand.
 */
export default function MethodologyPage() {
  return (
    <>
      <PageTitle title={copy.titles.method} />
      <PageIntro page="method" />
      <div className="mx-auto w-full max-w-[1120px] px-5 pb-20 sm:px-6">
      <Methodology
        models={servedModels()}
        manifest={manifest()}
        segments={segmentError()}
        gate={labelGate()}
      />
      </div>
    </>
  );
}
