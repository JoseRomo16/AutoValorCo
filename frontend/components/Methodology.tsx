"use client";

/**
 * The methodology page: data, models, out-of-sample metrics, the label rule and the
 * limitations.
 *
 * The limitations section is not boilerplate and is not softened. A valuation site that
 * does not say "these are asking prices, not sale prices" is overclaiming, and the one
 * figure a visitor is most likely to misread — a motorcycle estimate without a label — is
 * explained here rather than left as a missing badge.
 *
 * The metrics table is rendered from the served bundles' own manifests, passed in by the
 * page, so it moves when the model moves.
 */

import { useLang } from "./LanguageProvider";
import { REPO_URL } from "./SiteChrome";
import type { Manifest, ServedModelInfo } from "@/lib/results";
import { copy } from "@/lib/i18n";
import { integer, percent } from "@/lib/format";

const LIMITS = [
  copy.method.limitsList.source,
  copy.method.limitsList.asking,
  copy.method.limitsList.department,
  copy.method.limitsList.trim,
  copy.method.limitsList.motoBrand,
  copy.method.limitsList.fasecolda,
  copy.method.limitsList.index,
  copy.method.limitsList.time,
] as const;

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 border-t border-slate-200 pt-8 dark:border-slate-800">
      <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
      <div className="max-w-3xl space-y-3 text-slate-700 dark:text-slate-300">{children}</div>
    </section>
  );
}

export function Methodology({
  models,
  manifest,
}: {
  models: ServedModelInfo[];
  manifest: Manifest;
}) {
  const { lang, t } = useLang();

  return (
    <div className="space-y-10">
      <Block title={t(copy.method.data)}>
        <p>{t(copy.method.dataBody)}</p>
        <p className="font-medium">{t(copy.method.dataCaveat)}</p>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {t(copy.market.measuredOn)} {integer(manifest.gold_rows.car, lang)} /{" "}
          {integer(manifest.gold_rows.motorcycle, lang)} · {models[0]?.version}
        </p>
      </Block>

      <Block title={t(copy.method.models)}>
        <p>{t(copy.method.modelsBody)}</p>
        <p>{t(copy.method.bandBody)}</p>
      </Block>

      <Block title={t(copy.method.metrics)}>
        <p>{t(copy.method.metricsBody)}</p>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-300 text-left dark:border-slate-700">
                <th className="py-2 pr-4 font-semibold">{t(copy.method.vertical)}</th>
                <th className="py-2 pr-4 font-semibold">{t(copy.method.mape)}</th>
                <th className="py-2 pr-4 font-semibold">{t(copy.method.coverage)}</th>
                <th className="py-2 pr-4 font-semibold">{t(copy.method.width)}</th>
                <th className="py-2 pr-4 font-semibold">{t(copy.method.trainedOn)}</th>
                <th className="py-2 font-semibold">{t(copy.method.label)}</th>
              </tr>
            </thead>
            <tbody>
              {models.map((model) => (
                <tr key={model.vehicle_type} className="border-b border-slate-200 dark:border-slate-800">
                  <td className="py-2 pr-4">
                    {t(model.vehicle_type === "car" ? copy.form.car : copy.form.motorcycle)}
                  </td>
                  <td className="py-2 pr-4 tnum">{percent(model.mape * 100, lang)}</td>
                  <td className="py-2 pr-4 tnum">{percent(model.interval_coverage * 100, lang)}</td>
                  <td className="py-2 pr-4 tnum">
                    {percent(model.interval_mean_relative_width * 100, lang, 0)}
                  </td>
                  <td className="py-2 pr-4 tnum">{integer(model.trained_on_rows, lang)}</td>
                  <td className="py-2">
                    {model.publishes_label ? (
                      <span className="font-medium text-emerald-700 dark:text-emerald-400">
                        {t(copy.method.published)}
                      </span>
                    ) : (
                      <span className="text-slate-600 dark:text-slate-400">
                        {t(copy.method.withheld)}
                        {model.label_failures.length > 0 && (
                          <span className="block text-xs">{model.label_failures.join("; ")}</span>
                        )}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Block>

      <Block title={t(copy.method.rule)}>
        <p>{t(copy.method.ruleBody)}</p>
        <p>{t(copy.method.ruleCode)}</p>
      </Block>

      <Block title={t(copy.method.limits)}>
        <ul className="list-disc space-y-2 pl-5">
          {LIMITS.map((limit) => (
            <li key={limit.en}>{t(limit)}</li>
          ))}
        </ul>
      </Block>

      <section className="border-t border-slate-200 pt-8 dark:border-slate-800">
        <a
          className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-4 py-2 text-sm font-medium transition hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
          href={REPO_URL}
        >
          {t(copy.method.repo)} →
        </a>
      </section>
    </div>
  );
}
