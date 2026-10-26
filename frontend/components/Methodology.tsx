"use client";

/**
 * The methodology page: data, the model, out-of-sample results, the label rule and the
 * scope.
 *
 * The scope section is not boilerplate and is not softened. A valuation site that does not
 * say "these are asking prices" is overclaiming, and the one figure a visitor is most likely
 * to misread, a motorcycle estimate with no label, is explained here rather than left as a
 * missing badge.
 *
 * **Every number comes from a file.** The served bundles' own manifests and the results
 * manifest are passed in by the page, so the figures move when the model moves. The page
 * used to state four of them as prose, and a retrain made all four wrong at once.
 */

import { useLang } from "./LanguageProvider";
import { API_DOCS_URL, REPO_URL } from "./SiteChrome";
import type { LabelGate, Manifest, SegmentErrorRow, ServedModelInfo } from "@/lib/results";
import { copy, fill } from "@/lib/i18n";
import type { Localized } from "@/lib/i18n";
import { integer, isoDay, isoMonth, modelDate, percent, points } from "@/lib/format";

const DATA_BRANCH_URL = `${REPO_URL}/tree/data`;
const MODEL_INFO_URL = "https://autovalor-api.onrender.com/model-info";
const DECISIONS_URL = `${REPO_URL}/tree/main/docs/adr`;
const STATUS_URL = `${REPO_URL}/blob/main/docs/STATUS.md`;
const LINKEDIN_URL = "https://www.linkedin.com/in/jose-luis-romo";

/** The gate's two criteria, read off the failure codes rather than from local thresholds. */
function criteria(model: ServedModelInfo): { coverage: boolean; width: boolean } {
  const codes = model.label_failure_codes.map((entry) => entry.code);
  return {
    coverage: !codes.some((code) => code.startsWith("coverage_")),
    width: !codes.includes("width_above_max"),
  };
}

function Block({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      className="space-y-3 border-t border-slate-200 pt-8 scroll-mt-24 dark:border-slate-800"
    >
      <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
      <div className="max-w-3xl space-y-3 text-slate-700 dark:text-slate-300">{children}</div>
    </section>
  );
}

function Figure({ label, value, caption }: { label: string; value: string; caption: string }) {
  return (
    <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <p className="text-2xl font-semibold tracking-tight tnum">{value}</p>
      <p className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{caption}</p>
    </div>
  );
}

/** One scope card: what happens, what it does to the estimate, and what is planned. */
function ScopeCard({
  what,
  effect,
  plan,
}: {
  what: string;
  effect: string;
  plan: string;
}) {
  const { t } = useLang();
  return (
    <div className="space-y-2 rounded-xl border border-slate-200 p-4 text-sm dark:border-slate-800">
      <p className="font-medium text-slate-900 dark:text-slate-100">{what}</p>
      <p className="text-slate-600 dark:text-slate-400">
        <span className="font-medium">{t(copy.method.scope.effect)}:</span> {effect}
      </p>
      <p className="text-slate-600 dark:text-slate-400">
        <span className="font-medium">{t(copy.method.scope.plan)}:</span> {plan}
      </p>
    </div>
  );
}

export function Methodology({
  models,
  manifest,
  segments,
  gate,
}: {
  models: ServedModelInfo[];
  manifest: Manifest;
  segments: SegmentErrorRow[];
  gate: LabelGate;
}) {
  const { lang, t } = useLang();

  const car = models.find((model) => model.vehicle_type === "car");
  const moto = models.find((model) => model.vehicle_type === "motorcycle");
  const version = car?.version ?? moto?.version ?? "";
  const firstCapture = manifest.capture_dates.at(0);
  const lastCapture = manifest.capture_dates.at(-1);

  // The worst car segment, which is what turns the missing-trim limitation from an
  // assertion into a measurement.
  const worstCarBrand = segments
    .filter((row) => row.vehicle_type === "car" && row.segment_kind === "brand")
    .sort((a, b) => b.mape_pct - a.mape_pct)
    .at(0);

  const indexReadyOn =
    manifest.skipped_codes["price_index.car"]?.ready_on ??
    manifest.skipped_codes["price_index.motorcycle"]?.ready_on;

  const verticalName = (model: ServedModelInfo): string =>
    t(model.vehicle_type === "car" ? copy.form.car : copy.form.motorcycle);

  return (
    <div className="space-y-10">
      <p className="text-sm text-slate-600 dark:text-slate-400">{t(copy.method.leadDetail)}</p>

      <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
        <span>{fill(copy.method.modelVersion, lang, { date: modelDate(version, lang) })}</span>
        {firstCapture && lastCapture && (
          <span>
            {fill(copy.method.captures, lang, {
              count: manifest.capture_dates.length,
              first: isoDay(firstCapture, lang),
              last: isoDay(lastCapture, lang),
            })}
          </span>
        )}
      </p>

      {car && moto && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Figure
            label={t(copy.method.cards.errorCarLabel)}
            value={percent(car.mape * 100, lang)}
            caption={fill(copy.method.cards.errorCarCaption, lang, {
              count: integer(car.n_test, lang),
            })}
          />
          <Figure
            label={t(copy.method.cards.errorMotoLabel)}
            value={percent(moto.mape * 100, lang)}
            caption={fill(copy.method.cards.errorMotoCaption, lang, {
              count: integer(moto.n_test, lang),
            })}
          />
          <Figure
            label={t(copy.method.cards.coverageLabel)}
            value={percent(car.interval_coverage * 100, lang)}
            caption={fill(copy.method.cards.coverageCaption, lang, {
              car: percent(car.interval_coverage * 100, lang),
              motorcycle: percent(moto.interval_coverage * 100, lang),
            })}
          />
          <Figure
            label={t(copy.method.cards.evaluatedLabel)}
            value={integer(car.n_test + moto.n_test, lang)}
            caption={fill(copy.method.cards.evaluatedCaption, lang, {
              car: integer(car.n_test, lang),
              motorcycle: integer(moto.n_test, lang),
            })}
          />
        </div>
      )}

      <Block id="datos" title={t(copy.method.data.title)}>
        <p>{t(copy.method.data.body)}</p>
        <p className="font-medium">{t(copy.method.data.askingTitle)}</p>
        <p>{t(copy.method.data.askingBody)}</p>
        <p>
          {t(copy.method.data.reproducible)}{" "}
          <a className="underline hover:no-underline" href={DATA_BRANCH_URL}>
            {t(copy.method.data.capturesLink)}
          </a>
        </p>
      </Block>

      <Block id="modelo" title={t(copy.method.model.title)}>
        <p>{t(copy.method.model.lead)}</p>
        {car && moto && car.baseline_mape > 0 && moto.baseline_mape > 0 && (
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {fill(copy.method.model.detail, lang, {
              car: points((car.baseline_mape - car.mape) * 100, lang),
              motorcycle: points((moto.baseline_mape - moto.mape) * 100, lang),
            })}
          </p>
        )}

        <h3 className="pt-2 font-medium">{t(copy.method.model.stepsTitle)}</h3>
        <ol className="space-y-2 rounded-xl border border-slate-200 p-4 text-sm dark:border-slate-800">
          {STEPS.map((step, index) => (
            <li key={step.title.en} className="flex gap-3">
              <span className="tnum font-medium text-slate-500 dark:text-slate-400">
                {index + 1}
              </span>
              <span>
                <span className="font-medium text-slate-900 dark:text-slate-100">
                  {t(step.title)}
                </span>
                <span className="block text-slate-600 dark:text-slate-400">{t(step.body)}</span>
              </span>
            </li>
          ))}
        </ol>

        <h3 className="pt-2 font-medium">{t(copy.method.model.bandTitle)}</h3>
        <p>{t(copy.method.model.bandBody)}</p>
        {car && moto && car.uncalibrated_coverage > 0 && moto.uncalibrated_coverage > 0 && (
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {fill(copy.method.model.bandDetail, lang, {
              car: percent(car.uncalibrated_coverage * 100, lang),
              motorcycle: percent(moto.uncalibrated_coverage * 100, lang),
            })}
          </p>
        )}
      </Block>

      <Block id="resultados" title={t(copy.method.results.title)}>
        <p>{t(copy.method.results.lead)}</p>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {t(copy.method.results.detail)}
        </p>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] border-collapse text-sm">
            <caption className="pb-2 text-left text-sm text-slate-600 dark:text-slate-400">
              {t(copy.method.results.tableCaption)}
            </caption>
            <thead>
              <tr className="border-b border-slate-300 text-left dark:border-slate-700">
                <th className="py-2 pr-4 font-semibold">{t(copy.method.results.columnType)}</th>
                <th className="py-2 pr-4 font-semibold">{t(copy.method.results.columnError)}</th>
                <th className="py-2 pr-4 font-semibold">
                  {t(copy.method.results.columnMedianError)}
                </th>
                <th className="py-2 pr-4 font-semibold">{t(copy.method.results.columnCoverage)}</th>
                <th className="py-2 pr-4 font-semibold">{t(copy.method.results.columnWidth)}</th>
                <th className="py-2 pr-4 font-semibold">
                  {t(copy.method.results.columnEvaluated)}
                </th>
                <th className="py-2 font-semibold">{t(copy.method.results.columnLabel)}</th>
              </tr>
            </thead>
            <tbody>
              {models.map((model) => (
                <tr
                  key={model.vehicle_type}
                  className="border-b border-slate-200 dark:border-slate-800"
                >
                  <td className="py-2 pr-4">{verticalName(model)}</td>
                  <td className="py-2 pr-4 text-right tnum">{percent(model.mape * 100, lang)}</td>
                  <td className="py-2 pr-4 text-right tnum">
                    {percent(model.median_ape * 100, lang)}
                  </td>
                  <td className="py-2 pr-4 text-right tnum">
                    {percent(model.interval_coverage * 100, lang)}
                  </td>
                  <td className="py-2 pr-4 text-right tnum">
                    {percent(model.interval_mean_relative_width * 100, lang, 0)}
                  </td>
                  <td className="py-2 pr-4 text-right tnum">{integer(model.n_test, lang)}</td>
                  <td className="py-2">
                    {model.publishes_label ? (
                      <span className="font-medium text-emerald-700 dark:text-emerald-400">
                        {t(copy.method.results.published)}
                      </span>
                    ) : (
                      <span className="text-slate-600 dark:text-slate-400">
                        {t(copy.method.results.withheld)}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {car?.temporal && moto?.temporal && (
          <>
            <h3 className="pt-2 font-medium">{t(copy.method.results.temporalTitle)}</h3>
            <p>
              {fill(copy.method.results.temporalBody, lang, {
                car: points((car.temporal.mape - car.mape) * 100, lang),
                motorcycle: points((moto.temporal.mape - moto.mape) * 100, lang),
              })}
            </p>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              {fill(copy.method.results.temporalCaveat, lang, {
                count: manifest.capture_dates.length,
              })}
            </p>
          </>
        )}

        {worstCarBrand && (
          <>
            <h3 className="pt-2 font-medium">{t(copy.method.results.brandErrorTitle)}</h3>
            <p>
              {fill(copy.method.results.brandErrorBody, lang, {
                brand: worstCarBrand.segment,
                value: percent(worstCarBrand.mape_pct, lang),
              })}
            </p>
          </>
        )}
      </Block>

      <Block id="etiqueta" title={t(copy.method.rule.title)}>
        <p>{t(copy.method.rule.lead)}</p>
        <p className="font-medium">
          {fill(copy.method.rule.coverageTitle, lang, {
            min: percent(gate.min_coverage * 100, lang, 0),
            max: percent(gate.max_coverage * 100, lang, 0),
          })}
        </p>
        <p className="text-sm text-slate-600 dark:text-slate-400">{t(copy.method.rule.coverageWhy)}</p>
        <p className="font-medium">
          {fill(copy.method.rule.widthTitle, lang, {
            max: percent(gate.max_relative_width * 100, lang, 0),
          })}
        </p>
        <p className="text-sm text-slate-600 dark:text-slate-400">{t(copy.method.rule.widthWhy)}</p>

        <h3 className="pt-2 font-medium">{t(copy.method.rule.stateTitle)}</h3>
        <ul className="space-y-2 text-sm">
          {models.map((model) => {
            const met = criteria(model);
            return (
              <li key={model.vehicle_type} className="flex flex-wrap gap-x-4">
                <span className="font-medium">{verticalName(model)}</span>
                <span>
                  {met.coverage ? "✓" : "✗"} {t(copy.method.results.columnCoverage)}{" "}
                  <span className="tnum">{percent(model.interval_coverage * 100, lang)}</span>
                </span>
                <span>
                  {met.width ? "✓" : "✗"} {t(copy.method.results.columnWidth)}{" "}
                  <span className="tnum">
                    {percent(model.interval_mean_relative_width * 100, lang, 0)}
                  </span>
                </span>
                <span className="text-slate-600 dark:text-slate-400">
                  {model.publishes_label
                    ? t(copy.method.results.published)
                    : t(copy.method.results.withheld)}
                </span>
              </li>
            );
          })}
        </ul>
        <p className="text-sm text-slate-600 dark:text-slate-400">{t(copy.method.rule.inArtifact)}</p>
      </Block>

      <Block id="alcance" title={t(copy.method.scope.title)}>
        <p>{t(copy.method.scope.lead)}</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <ScopeCard
            what={t(copy.method.scope.items.sourceWhat)}
            effect={t(copy.method.scope.items.sourceEffect)}
            plan={t(copy.method.scope.noPlan)}
          />
          <ScopeCard
            what={t(copy.method.scope.items.askingWhat)}
            effect={t(copy.method.scope.items.askingEffect)}
            plan={t(copy.method.scope.items.askingPlan)}
          />
          {worstCarBrand && (
            <ScopeCard
              what={t(copy.method.scope.items.trimWhat)}
              effect={fill(copy.method.scope.items.trimEffect, lang, {
                brand: worstCarBrand.segment,
                value: percent(worstCarBrand.mape_pct, lang),
              })}
              plan={t(copy.method.scope.noPlan)}
            />
          )}
          <ScopeCard
            what={fill(copy.method.scope.items.motoBrandWhat, lang, {
              pct: percent(manifest.unresolved_make.motorcycle * 100, lang),
            })}
            effect={t(copy.method.scope.items.motoBrandEffect)}
            plan={t(copy.method.scope.noPlan)}
          />
          <ScopeCard
            what={t(copy.method.scope.items.departmentWhat)}
            effect={t(copy.method.scope.items.departmentEffect)}
            plan={t(copy.method.scope.noPlan)}
          />
          <ScopeCard
            what={t(copy.method.scope.items.fasecoldaWhat)}
            effect={t(copy.method.scope.items.fasecoldaEffect)}
            plan={t(copy.method.scope.items.fasecoldaPlan)}
          />
          {indexReadyOn && (
            <ScopeCard
              what={t(copy.method.scope.items.indexWhat)}
              effect={t(copy.method.scope.items.indexEffect)}
              plan={fill(copy.method.scope.items.indexPlan, lang, {
                date: isoMonth(indexReadyOn, lang),
              })}
            />
          )}
          <ScopeCard
            what={t(copy.method.scope.items.timeWhat)}
            effect={t(copy.method.scope.items.timeEffect)}
            plan={t(copy.method.scope.items.timePlan)}
          />
        </div>
      </Block>

      <Block id="detalle" title={t(copy.method.links.title)}>
        <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
          {[
            { href: REPO_URL, label: copy.method.links.repo },
            { href: API_DOCS_URL, label: copy.method.links.api },
            { href: MODEL_INFO_URL, label: copy.method.links.modelInfo },
            { href: DECISIONS_URL, label: copy.method.links.decisions },
            { href: STATUS_URL, label: copy.method.links.status },
            { href: LINKEDIN_URL, label: copy.method.links.author },
          ].map((link) => (
            <li key={link.href}>
              <a className="underline hover:no-underline" href={link.href}>
                {t(link.label)}
              </a>
            </li>
          ))}
        </ul>
      </Block>
    </div>
  );
}

/** The pipeline, as the diagram in the design shows it. */
const STEPS: { title: Localized; body: Localized }[] = [
  { title: copy.method.model.steps.captureTitle, body: copy.method.model.steps.captureBody },
  { title: copy.method.model.steps.rawTitle, body: copy.method.model.steps.rawBody },
  { title: copy.method.model.steps.featuresTitle, body: copy.method.model.steps.featuresBody },
  { title: copy.method.model.steps.baselineTitle, body: copy.method.model.steps.baselineBody },
  { title: copy.method.model.steps.modelTitle, body: copy.method.model.steps.modelBody },
  {
    title: copy.method.model.steps.calibrationTitle,
    body: copy.method.model.steps.calibrationBody,
  },
  { title: copy.method.model.steps.serveTitle, body: copy.method.model.steps.serveBody },
];
