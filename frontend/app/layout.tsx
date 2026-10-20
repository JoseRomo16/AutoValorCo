import type { Metadata } from "next";

import "./globals.css";
import { LanguageProvider } from "@/components/LanguageProvider";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";

export const metadata: Metadata = {
  title: {
    default: "AutoValor CO — valoración de carros y motos usados",
    template: "%s · AutoValor CO",
  },
  description:
    "Estima el precio de mercado de un carro o una moto usada en Colombia, con rango P10–P90 y la explicación de cada factor. Used vehicle valuation for the Colombian market.",
  openGraph: {
    title: "AutoValor CO",
    description:
      "Valoración de carros y motos usados en Colombia, con rango P10–P90 y explicación por factores.",
    type: "website",
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // lang="es" because Spanish is the default; LanguageProvider rewrites it when a visitor
  // switches, so the attribute never disagrees with what is rendered.
  return (
    <html lang="es">
      <body>
        <LanguageProvider>
          <a
            href="#content"
            className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-slate-900 focus:px-3 focus:py-2 focus:text-white"
          >
            Saltar al contenido / Skip to content
          </a>
          <SiteHeader />
          <main id="content" className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
            {children}
          </main>
          <SiteFooter />
        </LanguageProvider>
      </body>
    </html>
  );
}
