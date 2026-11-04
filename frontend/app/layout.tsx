import type { Metadata, Viewport } from "next";
import { Archivo, IBM_Plex_Sans, JetBrains_Mono } from "next/font/google";

import "./globals.css";
import { LANG_SCRIPT, LanguageProvider } from "@/components/LanguageProvider";
import { SiteFooter, SiteHeader, SkipLink } from "@/components/SiteChrome";
import { ServiceWorker } from "@/components/Pwa";
import { THEME_SCRIPT, ThemeProvider } from "@/components/ThemeProvider";
import { SITE_URL } from "@/lib/links";
import { manifest, servedModels } from "@/lib/results";
import { readThemeTokens } from "@/scripts/tokens.mjs";

const tokens = readThemeTokens();

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
  metadataBase: new URL(SITE_URL),
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
    // A PNG, and at a path that ends in `.png`. It was an SVG, which LinkedIn, WhatsApp
    // and Facebook all decline to render, so a shared link previewed as nothing. Written
    // by `scripts/og.mjs` before every build; see that file for why it is not
    // `app/opengraph-image.tsx`.
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "AutoValor CO. Cuánto vale tu carro o tu moto usada: precio estimado, rango probable y qué lo mueve.",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "AutoValor CO",
    description:
      "Precio estimado, rango probable y los factores que lo mueven, para carros y motos usados en Colombia.",
    images: ["/og.png"],
  },
  robots: { index: true, follow: true },
  // The installable app (ADR 0007). Manifest and icons are written by
  // scripts/pwa-assets.mjs before every build, from the same tokens as below.
  manifest: "/manifest.webmanifest",
  // Declaring `icons` replaces the file convention, so app/icon.svg has to be listed here
  // too or the tab loses its favicon (it did, in #40).
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/icons/icon-192.png", type: "image/png", sizes: "192x192" },
    ],
    apple: "/icons/apple-touch-icon.png",
  },
  appleWebApp: { capable: true, title: "AutoValor", statusBarStyle: "black-translucent" },
};

/** The browser chrome's colour per system theme, from the stylesheet's own grounds. */
export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: tokens.light.ground ?? "" },
    { media: "(prefers-color-scheme: dark)", color: tokens.dark.ground ?? "" },
  ],
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
    <html
      lang="es"
      // LANG_SCRIPT and THEME_SCRIPT write lang and data-theme before React hydrates.
      suppressHydrationWarning
      className={`${archivo.variable} ${plex.variable} ${jetbrains.variable}`}>
      <head>
        {/* Before the first paint. React runs after parsing, so a React-based fix flashes. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <script dangerouslySetInnerHTML={{ __html: LANG_SCRIPT }} />
        {/* "off" only in the emergency build (NEXT_PUBLIC_SW_KILL=1, ADR 0007). */}
        <meta name="autovalor-sw" content={process.env.NEXT_PUBLIC_SW_KILL === "1" ? "off" : "on"} />
      </head>
      <body>
        <ThemeProvider>
          <LanguageProvider>
            <SkipLink />
            <SiteHeader />
            <main id="content">{children}</main>
            <SiteFooter dataDate={dataDate} modelVersion={modelVersion} />
            <ServiceWorker />
          </LanguageProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
