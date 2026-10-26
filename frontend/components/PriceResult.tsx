"use client";

/**
 * The answer: a price, its range, the label when the vertical earned one, and the five
 * factors that moved it.
 *
 * The range is as prominent as the price on purpose. A single number for a used vehicle is
 * false precision, and the whole project is built around publishing the interval; a layout
 * that whispered it would undo that in CSS. Where the label cannot be published — today
 * motorcycles, because the band's mean width is 81 % of the estimate against a 60 % ceiling
 * — the API sends a precision notice and it is rendered in the label's place rather than
 * leaving an empty slot.
 *
 * The factors come back as multiplicative factors, which is what SHAP on a log-price model
 * actually produces, so they are shown as "raises / lowers by X %" — exact, not an
 * approximation dressed up as pesos.
 */

import { useLang } from "./LanguageProvider";
import {
  type ExplainResponse,
  type PredictResponse,
  type PriceLabel,
} from "@/lib/api";
import { copy, fill, pick } from "@/lib/i18n";
import type { Lang, Localized } from "@/lib/i18n";
import { cop, factorAsPercent, modelDate, percent } from "@/lib/format";

const LABEL_COPY: Record<PriceLabel, { title: Localized; why: Localized; tone: string }> = {
  bargain: {
    title: copy.result.bargain,
    why: copy.result.bargainWhy,
    tone: "border-emerald-400 bg-emerald-50 dark:border-emerald-700 dark:bg-emerald-950/30",
  },
  fair: {
    title: copy.result.fair,
    why: copy.result.fairWhy,
    tone: "border-sky-400 bg-sky-50 dark:border-sky-700 dark:bg-sky-950/30",
  },
  expensive: {
    title: copy.result.expensive,
    why: copy.result.expensiveWhy,
    tone: "border-amber-400 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/30",
  },
};

/** The gate's failure codes, as the exported model publishes them. */
const PRECISION_COPY: Record<string, Localized> = {
  width_above_max: copy.result.precision.widthAboveMax,
  coverage_below_min: copy.result.precision.coverageBelowMin,
  coverage_above_max: copy.result.precision.coverageAboveMax,
};

/**
 * Say in the reader's language why no label was published.
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

type Props = {
  prediction: PredictResponse;
  explanation: ExplainResponse;
  askingPrice: number | null;
};

export function PriceResult({ prediction, explanation, askingPrice }: Props) {
  const { lang, t } = useLang();
  const { band } = prediction;

  // Where the asking price sits inside the band, for the marker on the range bar.
  const span = band.upper_cop - band.lower_cop || 1;
  const askingPosition =
    askingPrice === null
      ? null
      : Math.min(Math.max(((askingPrice - band.lower_cop) / span) * 100, 0), 100);
  const estimatePosition = ((band.estimate_cop - band.lower_cop) / span) * 100;

  const strongest = Math.max(...explanation.factors.map((factor) => Math.abs(factor.factor - 1)), 0.01);

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

  return (
    <section aria-labelledby="result" className="space-y-8">
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-5 sm:p-6 dark:border-slate-800 dark:bg-slate-900/50">
        <h2 id="result" className="text-sm font-medium text-slate-600 dark:text-slate-400">
          {t(copy.result.heading)}
        </h2>
        <p className="mt-1 text-4xl font-semibold tracking-tight tnum">
          {cop(band.estimate_cop, lang)}
        </p>

        <div className="mt-6">
          <div className="flex items-baseline justify-between gap-4 text-sm">
            <span className="font-medium text-slate-700 dark:text-slate-300">
              {t(copy.result.range)}
            </span>
            <span className="text-slate-500 tnum dark:text-slate-400">
              ±{percent((band.relative_width / 2) * 100, lang, 0)}
            </span>
          </div>

          <div
            aria-hidden="true"
            className="relative mt-2 h-9 rounded-md bg-gradient-to-r from-emerald-200 via-slate-200 to-amber-200 dark:from-emerald-900/50 dark:via-slate-700 dark:to-amber-900/50"
          >
            <span
              className="absolute inset-y-0 w-0.5 bg-slate-900 dark:bg-slate-100"
              style={{ left: `${estimatePosition}%` }}
            />
            {askingPosition !== null && (
              <span
                className="absolute -top-1 bottom-[-0.25rem] w-1 rounded bg-sky-600 dark:bg-sky-400"
                style={{ left: `${askingPosition}%` }}
              />
            )}
          </div>

          <div className="mt-1.5 flex justify-between text-sm tnum">
            <span>{cop(band.lower_cop, lang)}</span>
            <span>{cop(band.upper_cop, lang)}</span>
          </div>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{t(copy.result.rangeHelp)}</p>
        </div>

        {prediction.label !== null && (
          <div className={`mt-5 rounded-lg border p-4 ${LABEL_COPY[prediction.label].tone}`}>
            <p className="font-semibold">{t(LABEL_COPY[prediction.label].title)}</p>
            <p className="mt-0.5 text-sm text-slate-700 dark:text-slate-300">
              {t(LABEL_COPY[prediction.label].why)}
            </p>
          </div>
        )}

        {prediction.label === null && prediction.precision_notice !== null && (
          <div className="mt-5 rounded-lg border border-slate-300 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
            <p className="font-semibold">{t(copy.result.noLabelTitle)}</p>
            <p className="mt-0.5 text-sm text-slate-700 dark:text-slate-300">
              {t(copy.result.noLabelBody)}
            </p>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              {precisionReason(prediction, lang)}
            </p>
          </div>
        )}

        {askingPrice !== null && (
          <p className="mt-5 text-sm text-slate-700 dark:text-slate-300">
            <span className="font-medium">{t(copy.result.asking)}:</span>{" "}
            <span className="tnum">{cop(askingPrice, lang)}</span>{" "}
            <span className="text-slate-500 dark:text-slate-400">{askingComparison}</span>
          </p>
        )}

        <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
          {fill(copy.result.modelVersion, lang, {
            date: modelDate(prediction.model_version, lang),
          })}
        </p>
      </div>

      <div>
        <h3 className="text-lg font-semibold">{t(copy.result.factors)}</h3>
        <p className="mt-1 max-w-3xl text-sm text-slate-600 dark:text-slate-400">
          {t(copy.result.factorsHelp)}
        </p>

        <ul className="mt-4 space-y-2">
          {explanation.factors.map((factor) => {
            const pull = Math.abs(factor.factor - 1);
            const width = Math.max((pull / strongest) * 50, 1.5);
            const raises = factor.direction === "raises";
            return (
              <li
                key={factor.feature}
                className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 sm:grid-cols-[14rem_1fr_6rem]"
              >
                <span className="text-sm">
                  <span className="font-medium">{factor.label[lang]}</span>
                  <span className="block text-xs text-slate-500 dark:text-slate-400">
                    {factor.value_display[lang]}
                  </span>
                </span>

                <div
                  aria-hidden="true"
                  className="order-last col-span-2 h-5 sm:order-none sm:col-span-1"
                >
                  <div className="relative h-full">
                    <span className="absolute inset-y-0 left-1/2 w-px bg-slate-300 dark:bg-slate-600" />
                    <span
                      className={`absolute inset-y-1 rounded-sm ${raises ? "bg-emerald-600/80" : "bg-sky-500/80"}`}
                      style={
                        raises
                          ? { left: "50%", width: `${width}%` }
                          : { right: "50%", width: `${width}%` }
                      }
                    />
                  </div>
                </div>

                <span className="text-right text-sm font-medium tnum">
                  {factorAsPercent(factor.factor, lang)}
                  <span className="block text-xs font-normal text-slate-500 dark:text-slate-400">
                    {t(raises ? copy.result.raises : copy.result.lowers)}
                  </span>
                </span>
              </li>
            );
          })}
        </ul>

        <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
          {t(copy.result.basePrice)}: <span className="tnum">{cop(explanation.base_price_cop, lang)}</span>
        </p>
      </div>
    </section>
  );
}
