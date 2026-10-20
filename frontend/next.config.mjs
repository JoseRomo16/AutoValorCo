/**
 * Static export, because a static site is the only frontend that is free on Render.
 *
 * `output: "export"` means there is no Node server at all: the build writes HTML, CSS and
 * JS into `out/` and Render serves those files from a CDN. Everything dynamic therefore
 * happens in one of two places — at build time (the market tables and the served model's
 * own metrics, read from the repository) or in the browser (the valuation form, which
 * calls the API). There is no third option here, and that constraint is deliberate: a
 * server-rendered page would need a paid plan.
 *
 * `trailingSlash` makes the export write `valorar/index.html` instead of `valorar.html`,
 * which is what a static host serves correctly without rewrite rules.
 */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  // No image optimizer exists without a server; the site ships plain files anyway.
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
