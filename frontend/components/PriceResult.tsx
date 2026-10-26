"use client";

/**
 * The answer: a price, its range, the verdict when the vertical earned one, and the five
 * factors that moved it.
 *
 * **The range carries the same visual weight as the price.** A single number for a used
 * vehicle is false precision, and the whole project is built around publishing the
 * interval; a layout that whispered it would undo that in CSS. They sit side by side in one
 * bordered pair, at the same size.
 *
 * **The range bar is grey, always.** It used to run green to amber, which told a reader
 * "cheap on the left, expensive on the right" even for motorcycles, where no verdict is
 * published at all. Green, neutral and terracotta are reserved for the verdict badge; the
 * bar shows a magnitude, and magnitudes are grey.
 *
 * **The empty state explains rather than demonstrates.** A worked example would mean a
 * price, a range and five factors invented in this file, and no figure on this site is
 * written by hand. So before the first valuation the panel says what will appear, with the
 * same shapes in the same order.
 *
 * The factors come back as multiplicative factors, which is what SHAP on a log-price model
 * actually produces, so they are shown as a percentage that raises or lowers the estimate:
 * exact, not an approximation dressed up as pesos.
 */

import { useEffect } from "react";

import { useLang } from "./LanguageProvider";
import { type ExplainResponse, type PredictResponse, type PriceLabel } from "@/lib/api";
import { copy, fill, pick } from "@/lib/i18n";
import type { Lang, Localized } from "@/lib/i18n";
import { cop, copMillions, factorAsPercent, modelDate, percent } from "@/lib/format";

const VERDICT: Record<PriceLabel, { title: Localized; why: Localized; tone: string }> = {
  bargain: { title: copy.result.bargain, why: copy.result.bargainWhy, tone: "bg-good-bg text-good" },
  fair: {
    title: copy.result.fair,
    why: copy.result.fairWhy,
    tone: "border border-line-strong text-neutral",
  },
  expensive: {
    title: copy.result.expensive,
    why: copy.result.expensiveWhy,
    tone: "bg-bad-bg text-bad",
  },
};

/** The gate's failure codes, as the exported model publishes them. */
const PRECISION_COPY: Record<string, Localized> = {
  width_above_max: copy.result.precision.widthAboveMax,
  coverage_below_min: copy.result.precision.coverageBelowMin,
  coverage_above_max: copy.result.precision.coverageAboveMax,
};

/**
 * Say in the reader's language why no verdict was published.
 *
 * The service also sends its own English sentence, and rendering that was how English text
 * ended up on the Spanish page. The codes carry the same two figures, so the sentence can
 * be written here instead. An older deployed image sends no codes, and a code this build
 * does not know is possible too; both fall back to the reason without the numbers rather
 * than to English.
 */
function precisionReason(prediction: PredictResponse, lang: Lang): string {
  const sentences = (prediction.precision_codes ?? []).flatMap((entry) => {
    const text = PRECISION_COPY[entry.code];
    if (text === undefined) return [];
    return [
      fill(text, lang, {
        value: percent(entry.value * 100, lang, 0),
        limit: percent(entry.limit * 100, lang, 0),
      }),
    ];
  });
  if (sentences.length === 0) return pick(copy.result.precision.unknown, lang);
  return sentences.join(" ");
}

function Panel({
  title,
  badge,
  children,
}: {
  title: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section
      aria-labelledby="result-title"
      aria-live="polite"
      className="rounded-lg border border-line bg-surface p-5 sm:p-7"
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2
          id="result-title"
          tabIndex={-1}
          className="font-mono text-xs uppercase tracking-[0.1em] text-muted outline-none"
        >
          {title}
        </h2>
        {badge}
      </div>
      {children}
    </section>
  );
}

/** The grey blocks that hold the layout still while a request is in flight. */
function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded bg-grid ${className}`}
      style={{ animationDuration: "1.4s" }}
    />
  );
}

type Props = {
  prediction: PredictResponse | null;
  explanation: ExplainResponse | null;
  askingPrice: number | null;
  /** What was priced, as a classified reads it: make model · year · km · department. */
  spec: string | null;
  busy: boolean;
};

export function PriceResult({ prediction, explanation, askingPrice, spec, busy }: Props) {
  const { lang, t } = useLang();
  const arrived = prediction !== null && explanation !== null;

  // When a result lands, move focus to its heading so a screen reader reads the answer
  // instead of leaving the user on the button wondering whether anything happened. On a
  // phone the panel is below the form, so it also has to be brought into view.
  useEffect(() => {
    if (!arrived) return;
    const heading = document.getElementById("result-title");
    if (!heading) return;
    if (window.matchMedia("(max-width: 959px)").matches) {
      heading.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    heading.focus({ preventScroll: true });
  }, [arrived, prediction]);

  if (busy) {
    return (
      <Panel title={t(copy.result.heading)}>
        <Skeleton className="h-4 w-2/5" />
        <Skeleton className="mt-4 h-20 w-full" />
        <Skeleton className="mt-5 h-8 w-full" />
        <Skeleton className="mt-5 h-3 w-4/5" />
        <Skeleton className="mt-2 h-3 w-3/5" />
      </Panel>
    );
  }

  if (!arrived) {
    return (
      <Panel title={t(copy.result.emptyTitle)}>
        <p className="text-sm text-muted">{t(copy.result.emptyBody)}</p>
        {/* The shapes the answer will take, in the order it will take them. Unfilled on
            purpose: a worked example would need invented figures. */}
        <div aria-hidden className="mt-6 space-y-4 opacity-45">
          <div className="grid grid-cols-2 rounded-lg border border-line">
            <div className="border-r border-line p-4">
              <div className="h-2.5 w-16 rounded-full bg-grid" />
              <div className="mt-3 h-6 w-24 rounded bg-grid" />
            </div>
            <div className="p-4">
              <div className="h-2.5 w-16 rounded-full bg-grid" />
              <div className="mt-3 h-6 w-24 rounded bg-grid" />
            </div>
          </div>
          <div className="h-8 rounded bg-grid" />
          <div className="space-y-2.5">
            {[64, 52, 40].map((width) => (
              <div key={width} className="flex items-center gap-3">
                <div className="h-2.5 rounded-full bg-grid" style={{ width: `${width}%` }} />
                <div className="h-2.5 w-10 rounded-full bg-grid" />
              </div>
            ))}
          </div>
        </div>
      </Panel>
    );
  }

  const { band } = prediction;
  const span = band.upper_cop - band.lower_cop || 1;
  const estimateAt = ((band.estimate_cop - band.lower_cop) / span) * 100;
  const askingAt =
    askingPrice === null
      ? null
      : Math.min(Math.max(((askingPrice - band.lower_cop) / span) * 100, 0), 100);

  const strongest = Math.max(
    ...explanation.factors.map((factor) => Math.abs(factor.factor - 1)),
    0.01,
  );

  // "You are asking 8 % above the estimate" rather than a bare signed percentage, which
  // leaves the reader to work out which way the sign points.
  const gap =
    askingPrice === null ? 0 : ((askingPrice - band.estimate_cop) / band.estimate_cop) * 100;
  const askingComparison =
    Math.abs(gap) < 1
      ? t(copy.result.askingEqual)
      : fill(gap > 0 ? copy.result.askingAbove : copy.result.askingBelow, lang, {
          pct: percent(Math.abs(gap), lang, 0),
        });

  const verdict = prediction.label === null ? null : VERDICT[prediction.label];

  return (
    <Panel title={t(copy.result.heading)}>
      {spec && <p className="-mt-1 mb-5 text-sm text-muted">{spec}</p>}

      {/* Price and range, same size, one object. */}
      <dl className="grid grid-cols-1 rounded-lg border border-line sm:grid-cols-2">
        <div className="min-w-0 border-b border-line p-4 sm:border-b-0 sm:border-r">
          <dt className="mb-2 text-xs text-muted">{t(copy.result.heading)}</dt>
          <dd className="font-mono text-2xl leading-tight tracking-[-0.03em] tabular-nums">
            {copMillions(band.estimate_cop, lang)}
            <small className="mt-1.5 block font-sans text-xs font-normal tracking-normal text-muted">
              {cop(band.estimate_cop, lang)}
            </small>
          </dd>
        </div>
        <div className="min-w-0 p-4">
          <dt className="mb-2 text-xs text-muted">{t(copy.result.range)}</dt>
          <dd className="font-mono text-2xl leading-tight tracking-[-0.03em] tabular-nums">
            {`${copMillions(band.lower_cop, lang)}–${copMillions(band.upper_cop, lang)}`}
            <small className="mt-1.5 block font-sans text-xs font-normal tracking-normal text-muted">
              {t(copy.result.rangeHelp)}
            </small>
          </dd>
        </div>
      </dl>

      <div className="mt-5">
        <div aria-hidden className="relative h-8 rounded bg-grid">
          <span className="absolute inset-x-0 inset-y-2 rounded-sm bg-bar-muted ring-1 ring-bar-edge" />
          <span
            className="absolute inset-y-1 w-0.5 bg-ink"
            style={{ left: `${estimateAt}%` }}
          />
          {askingAt !== null && (
            // The asking marker is the one thing on this bar that is yellow. It carries a
            // ring in the ink colour because plate yellow on the light grid is 1.19:1 and
            // would otherwise vanish on paper.
            <span
              className="absolute -inset-y-1 w-1 rounded-sm bg-accent ring-2 ring-ink"
              style={{ left: `${askingAt}%` }}
            />
          )}
        </div>
        <div className="mt-2 flex justify-between font-mono text-xs text-muted">
          <span>
            <b className="block font-medium text-ink">{copMillions(band.lower_cop, lang)}</b>P10
          </span>
          <span className="text-right">
            <b className="block font-medium text-ink">{copMillions(band.upper_cop, lang)}</b>P90
          </span>
        </div>
      </div>

      {(verdict || prediction.precision_notice !== null) && (
        <div className="mt-5 grid grid-cols-[auto_1fr] items-baseline gap-x-3.5 gap-y-1 border-y border-line py-4">
          {verdict ? (
            <>
              <span
                className={`rounded px-2 py-1 font-mono text-xs leading-none ${verdict.tone}`}
              >
                {t(verdict.title)}
              </span>
              <p className="text-sm text-muted">{t(verdict.why)}</p>
            </>
          ) : (
            <>
              <span className="rounded border border-line-strong px-2 py-1 font-mono text-xs leading-none text-neutral">
                {t(copy.result.noLabelTitle)}
              </span>
              <p className="text-sm text-muted">{t(copy.result.noLabelBody)}</p>
              <p className="col-start-2 text-xs text-faint">{precisionReason(prediction, lang)}</p>
            </>
          )}
          {askingPrice !== null && (
            <p className="col-start-2 text-sm">
              <span className="font-mono tabular-nums">{cop(askingPrice, lang)}</span>{" "}
              <span className="text-muted">{askingComparison}</span>
            </p>
          )}
        </div>
      )}

      <div className="mt-5">
        <h3 className="font-medium">{t(copy.result.factors)}</h3>
        <p className="mt-1 text-sm text-muted">{t(copy.result.factorsHelp)}</p>

        <ul className="mt-3">
          {explanation.factors.map((factor) => {
            const width = Math.max((Math.abs(factor.factor - 1) / strongest) * 50, 1.5);
            const raises = factor.direction === "raises";
            return (
              <li
                key={factor.feature}
                className="grid grid-cols-[minmax(0,1fr)_90px_64px] items-center gap-3 border-b border-line py-2.5 last:border-b-0"
              >
                <div className="min-w-0">
                  <b className="block text-sm font-medium">{factor.label[lang]}</b>
                  <small className="font-mono text-xs text-faint">
                    {factor.value_display[lang]}
                  </small>
                </div>
                {/* Grey, with the side of the centre line carrying the direction. Colour
                    here would collide with the verdict's vocabulary. */}
                <div aria-hidden className="relative h-3.5">
                  <span className="absolute -inset-y-0.5 left-1/2 w-px bg-line-strong" />
                  <span
                    className="absolute inset-y-[3px] rounded-sm bg-bar"
                    style={raises ? { left: "50%", width: `${width}%` } : { right: "50%", width: `${width}%` }}
                  />
                </div>
                <span className="text-right font-mono text-sm font-medium tabular-nums">
                  {factorAsPercent(factor.factor, lang)}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm">
        <span className="font-mono text-xs text-faint">
          {fill(copy.result.modelVersion, lang, {
            date: modelDate(prediction.model_version, lang),
          })}
        </span>
        <a
          href="/metodologia/"
          className="font-semibold text-accent-text underline underline-offset-4 hover:opacity-80"
        >
          {t(copy.result.howItWorks)}
        </a>
      </div>
    </Panel>
  );
}
