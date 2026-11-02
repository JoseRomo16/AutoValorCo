import type { Metadata } from "next";

import { NotFoundContent } from "@/components/NotFoundContent";

/**
 * The 404, served by the static export for every unmatched path.
 *
 * Split in two for one reason: a client component cannot export `metadata`, and the page
 * needs both -- translated copy, which needs the client, and a title of its own in the
 * HTML, which needs the server. The body lives in `NotFoundContent`.
 */
export const metadata: Metadata = {
  title: "Página no encontrada",
  description: "La página que buscas no existe. Vuelve a Valorar, Mercado o Metodología.",
  // A 404 is not a page to index, whatever the site-wide default says.
  robots: { index: false, follow: true },
};

export default function NotFound() {
  return <NotFoundContent />;
}
