import type { Metadata } from "next";

import { OfflineContent } from "@/components/OfflineContent";

/**
 * The offline fallback the service worker serves for a page it does not have. Never
 * linked from the site; split like the 404 so the copy can be translated on the client
 * while the title stays in the HTML.
 */
export const metadata: Metadata = {
  title: "Sin conexión",
  description: "Sin conexión. Mercado y Metodología funcionan sin red; Valorar necesita conexión.",
  robots: { index: false, follow: false },
};

export default function OfflinePage() {
  return <OfflineContent />;
}
