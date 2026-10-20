import type { Metadata } from "next";

import { Methodology } from "@/components/Methodology";
import { PageIntro } from "@/components/PageIntro";
import { manifest, servedModels } from "@/lib/results";

export const metadata: Metadata = { title: "Metodología" };

/**
 * The metrics on this page come from each vertical's `model.json` under
 * `artifacts/models/` at build time — the very files the API image serves — so the page
 * cannot quote a MAPE the deployed model does not have, and no number here is typed by
 * hand.
 */
export default function MethodologyPage() {
  return (
    <>
      <PageIntro page="method" />
      <Methodology models={servedModels()} manifest={manifest()} />
    </>
  );
}
