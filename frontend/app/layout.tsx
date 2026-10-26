import type { Metadata } from "next";
import { Archivo, IBM_Plex_Sans, JetBrains_Mono } from "next/font/google";

import "./globals.css";
import { LanguageProvider } from "@/components/LanguageProvider";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { THEME_SCRIPT, ThemeProvider } from "@/components/ThemeProvider";
import { manifest, servedModels } from "@/lib/results";

/*
 * Three families with fixed jobs, self-hosted by `next/font` so there is no request to
 * Google at runtime and no layout shift when they arrive.
 *
 * Archivo carries the headlines at a stretched width, which is where the page gets its
 * voice: a condensed or normal-width grotesque here would read like any other dashboard.
 * Plex Sans runs the prose. JetBrains Mono takes every figure, because a price next to a
 * price has to line up digit for digit, and that is a job a proportional face cannot do.
 */
const archivo = Archivo({
  subsets: ["latin"],
  // No `weight`: asking for the width axis means asking for the variable font, and pinning
  // a static weight alongside it is a contradiction Next rejects at build. The headline
  // weight and width are then set in CSS, which is also where they belong — they are part
  // of the type treatment, not of which file gets downloaded.
  axes: ["wdth"],
  variable: "--font-archivo",
  display: "swap",
});

const plex = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  // Without this the Open Graph image resolves against localhost, so a shared link shows
  // no preview anywhere. The deployed origin is a constant for a static export.
  metadataBase: new URL("https://autovalor-web.onrender.com"),
  title: {
    default: "AutoValor CO, precios de carros y motos usados",
    template: "%s · AutoValor CO",
  },
  description:
    "Estima el precio de un carro o una moto usada en Colombia, con el rango en el que se publican vehículos parecidos y qué lo sube o lo baja.",
  openGraph: {
    title: "AutoValor CO",
    description:
      "Precio estimado, rango probable y los factores que lo mueven, para carros y motos usados en Colombia.",
    type: "website",
    locale: "es_CO",
    images: [{ url: "/og.svg", width: 1200, height: 630, alt: "AutoValor CO" }],
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // Read once, here, from files in the repository. Every page then shows the same two
  // dates in its footer, which is the cheapest way to stop them disagreeing.
  const captures = manifest().capture_dates;
  const dataDate = captures.at(-1);
  const modelVersion = servedModels()[0]?.version;

  // lang="es" because Spanish is the default; LanguageProvider rewrites it when a visitor
  // switches, so the attribute never disagrees with what is rendered.
  return (
    <html lang="es" className={`${archivo.variable} ${plex.variable} ${jetbrains.variable}`}>
      <head>
        {/* Before the first paint. React runs after parsing, so a React-based fix flashes. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>
          <LanguageProvider>
            <a
              href="#content"
              className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded focus:bg-accent focus:px-3 focus:py-2 focus:font-semibold focus:text-accent-ink"
            >
              Saltar al contenido / Skip to content
            </a>
            <SiteHeader />
            <main id="content">{children}</main>
            <SiteFooter dataDate={dataDate} modelVersion={modelVersion} />
          </LanguageProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
