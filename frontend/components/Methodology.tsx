"use client";

/**
 * The methodology page: data, the model, out-of-sample results, the label rule and the
 * scope, after `docs/design/metodologia.html`.
 *
 * The scope section is not boilerplate and is not softened. A valuation site that does not
 * say "these are asking prices" is overclaiming, and the one figure a visitor is most likely
 * to misread, a motorcycle estimate with no label, is explained here rather than left as a
 * missing badge.
 *
 * **Every number comes from a file.** The served bundles' own manifests, their catalogues
 * and the results manifest are passed in by the page, so the figures move when the model
 * moves. The page once stated four of them as prose, and a retrain made all four wrong.
 * Every colour is a theme token: no `dark:` utility, no palette class.
 */

import { useEffect, useState } from "react";

import { useLang } from "./LanguageProvider";
import { Term, fillNodes } from "./Term";
import { IntervalBars } from "./charts/IntervalBars";
import type { LabelGate, Manifest, SegmentErrorRow, ServedModelInfo } from "@/lib/results";
import {
  API_DOCS_URL,
  DATA_BRANCH_URL,
  DECISIONS_URL,
  LINKEDIN_URL,
  MODEL_INFO_URL,
  REPO_URL,
  STATUS_URL,
} from "@/lib/links";
import { copy, fill } from "@/lib/i18n";
import type { Lang, Localized } from "@/lib/i18n";
import { LOW_DATA_LISTINGS, isThin } from "@/lib/listings";
import { decimal, integer, isoDay, isoMonth, modelDate, percent, points } from "@/lib/format";

/** Section anchors, in page order; the table of contents is built from this list. */
const SECTIONS = [
  { id: "datos", label: copy.method.toc.data },
  { id: "modelo", label: copy.method.toc.model },
  { id: "resultados", label: copy.method.toc.results },
  { id: "etiqueta", label: copy.method.toc.rule },
  { id: "alcance", label: copy.method.toc.scope },
  { id: "detalle", label: copy.method.toc.links },
] as const;

/** The gate's two criteria, read off the failure codes rather than from local thresholds. */
function criteria(model: ServedModelInfo): { coverage: boolean; width: boolean } {
  const codes = model.label_failure_codes.map((entry) => entry.code);
  return {
    coverage: !codes.some((code) => code.startsWith("coverage_")),
    width: !codes.includes("width_above_max"),
  };
}

const FAILURE_COPY: Record<string, Localized> = {
  width_above_max: copy.result.precision.widthAboveMax,
  coverage_below_min: copy.result.precision.coverageBelowMin,
  coverage_above_max: copy.result.precision.coverageAboveMax,
};

/** The section the reader is in, for the sticky table of contents. */
function useCurrentSection(ids: readonly string[]): string {
  const [current, setCurrent] = useState<string>(ids[0] ?? "");
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setCurrent(visible[0].target.id);
      },
      // A section counts once its top passes the upper third of the viewport.
      { rootMargin: "-25% 0px -65% 0px" },
    );
    for (const id of ids) {
      const node = document.getElementById(id);
      if (node) observer.observe(node);
    }
    return () => observer.disconnect();
  }, [ids]);
  return current;
}

function Badge({ published, lang }: { published: boolean; lang: Lang }) {
  return published ? (
    <span className="inline-block whitespace-nowrap rounded bg-good-bg px-2 py-1 font-mono text-caption text-good">
      {copy.method.results.published[lang]}
    </span>
  ) : (
    <span className="inline-block whitespace-nowrap rounded border border-line-strong px-2 py-1 font-mono text-caption text-neutral">
      {copy.method.results.withheld[lang]}
    </span>
  );
}

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-24 border-t border-line pt-14">
      <h2
        id={`${id}-title`}
        className="font-display text-step-h2 font-extrabold leading-tight tracking-[-0.01em] text-ink [font-stretch:112%]"
      >
        {title}
      </h2>
      <div className="mt-5 space-y-5">{children}</div>
    </section>
  );
}

function Body({ children }: { children: React.ReactNode }) {
  return <p className="max-w-[66ch] text-lg leading-relaxed text-muted">{children}</p>;
}

function Subtitle({ children }: { children: React.ReactNode }) {
  return <h3 className="pt-2 text-lg font-semibold text-ink">{children}</h3>;
}

/** A key figure: big mono number, its unit small in the accent, a short label, a sentence. */
function Figure({
  number,
  unit,
  label,
  caption,
  extra,
}: {
  number: string;
  unit?: string;
  label: string;
  caption: string;
  extra?: string;
}) {
  return (
    <div className="min-w-0 border-line py-2 sm:px-6 sm:first:pl-0 lg:border-l lg:first:border-l-0">
      <p className="whitespace-nowrap font-mono text-step-figure font-medium leading-none tracking-[-0.04em] text-ink tnum">
        {number}
        {unit && <small className="ml-1 text-[0.52em] tracking-normal text-accent-text">{unit}</small>}
      </p>
      <p className="mt-4 font-display text-detail font-bold uppercase tracking-[0.04em] text-ink [font-stretch:110%]">
        {label}
      </p>
      <p className="mt-2 text-detail text-muted">{caption}</p>
      {extra && <p className="mt-1 text-detail text-muted">{extra}</p>}
    </div>
  );
}

/** Two horizontal bars per vertical against a common scale, with an optional target. */
function Comparison({
  title,
  body,
  groups,
  max,
  target,
  targetLabel,
}: {
  title: string;
  body: string;
  groups: { label: string; rows: { label: string; value: number; text: string; strong: boolean }[] }[];
  max: number;
  target?: number;
  targetLabel?: string;
}) {
  const at = (value: number) => `${Math.min((value / max) * 100, 100)}%`;
  return (
    <figure className="m-0 rounded-lg border border-line bg-surface p-5 sm:p-6">
      <h3 className="text-lg font-semibold text-ink">{title}</h3>
      <p className="mb-5 mt-1 text-detail text-muted">{body}</p>
      <div className="space-y-4">
        {groups.map((group) => (
          <div key={group.label}>
            <p className="mb-2 text-detail font-semibold text-ink">{group.label}</p>
            {group.rows.map((row) => (
              <div
                key={row.label}
                className="mt-1.5 grid grid-cols-[7rem_minmax(0,1fr)_4.5rem] items-center gap-3"
              >
                <span className="text-caption text-muted">{row.label}</span>
                <span className="relative h-3.5 rounded-sm bg-grid">
                  <span
                    className={`absolute inset-y-0 left-0 rounded-sm ${row.strong ? "bg-ink" : "bg-bar-muted"}`}
                    style={{ width: at(row.value) }}
                  />
                  {target !== undefined && (
                    <span
                      aria-hidden="true"
                      className="absolute -inset-y-1.5 border-l-2 border-dashed border-accent-text"
                      style={{ left: at(target) }}
                    />
                  )}
                </span>
                <span className="text-right font-mono text-detail text-ink tnum">{row.text}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
      {targetLabel && (
        <p className="mt-4 flex items-center gap-2 font-mono text-caption text-muted">
          <span aria-hidden="true" className="inline-block h-3 border-l-2 border-dashed border-accent-text" />
          {targetLabel}
        </p>
      )}
    </figure>
  );
}

/** One scope card: what happens, what it does to the estimate, and what is planned. */
function ScopeCard({ what, effect, plan }: { what: string; effect: string; plan?: string }) {
  const { t } = useLang();
  return (
    <article className="grid content-start gap-3 rounded-lg border border-line bg-surface p-5 sm:p-6">
      <h3 className="font-semibold leading-snug text-ink">{what}</h3>
      <dl className="grid gap-3">
        <div>
          <dt className="font-mono text-caption uppercase tracking-[0.08em] text-muted">
            {t(copy.method.scope.effect)}
          </dt>
          <dd className="mt-1 text-detail text-muted">{effect}</dd>
        </div>
        {plan && (
          <div>
            <dt className="font-mono text-caption uppercase tracking-[0.08em] text-muted">
              {t(copy.method.scope.plan)}
            </dt>
            <dd className="mt-1 text-detail text-ink">{plan}</dd>
          </div>
        )}
      </dl>
    </article>
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
  const current = useCurrentSection(SECTIONS.map((section) => section.id));

  const car = models.find((model) => model.vehicle_type === "car");
  const moto = models.find((model) => model.vehicle_type === "motorcycle");
  const version = car?.version ?? moto?.version ?? "";
  const firstCapture = manifest.capture_dates.at(0);
  const lastCapture = manifest.capture_dates.at(-1);
  const lastCaptureText = lastCapture ? isoDay(lastCapture, lang) : "—";
  const listings = models.reduce((sum, model) => sum + model.trained_on_rows, 0);
  const spanDays = car?.temporal?.span_days ?? manifest.capture_span_days;
  const heldOutShare = car ? percent((car.n_test / car.trained_on_rows) * 100, lang, 0) : "";
  const nominal = (gate.min_coverage + gate.max_coverage) / 2;

  // The worst car segment, which turns the missing-trim limitation from an assertion into
  // a measurement.
  const carBrandErrors = segments
    .filter((row) => row.vehicle_type === "car" && row.segment_kind === "brand")
    .sort((a, b) => b.mape_pct - a.mape_pct);
  const worstCarBrand = carBrandErrors.at(0);

  const indexReadyOn =
    manifest.skipped_codes["price_index.car"]?.ready_on ??
    manifest.skipped_codes["price_index.motorcycle"]?.ready_on;

  // Departments: the union of both catalogues, the thin ones by the form's own line.
  const departments = [
    ...new Set(models.flatMap((model) => model.departments.map((entry) => entry.name))),
  ].sort((a, b) => a.localeCompare(b, "es"));
  const thinDepartments = departments.filter((name) =>
    models.some((model) => {
      const entry = model.departments.find((candidate) => candidate.name === name);
      return entry !== undefined && isThin(entry.listings);
    }),
  );
  const listFormat = new Intl.ListFormat(lang === "es" ? "es" : "en", { type: "conjunction" });

  const verticalName = (model: ServedModelInfo): string =>
    t(model.vehicle_type === "car" ? copy.form.cars : copy.form.motorcycles);

  const term = (key: keyof typeof copy.terms) => (
    <Term term={copy.terms[key].term} definition={copy.terms[key].definition} />
  );

  const steps: { title: Localized; body: string }[] = [
    {
      title: copy.method.model.steps.captureTitle,
      body: fill(copy.method.model.steps.captureBody, lang, { date: lastCaptureText }),
    },
    { title: copy.method.model.steps.rawTitle, body: t(copy.method.model.steps.rawBody) },
    { title: copy.method.model.steps.featuresTitle, body: t(copy.method.model.steps.featuresBody) },
    { title: copy.method.model.steps.baselineTitle, body: t(copy.method.model.steps.baselineBody) },
    { title: copy.method.model.steps.modelTitle, body: t(copy.method.model.steps.modelBody) },
    {
      title: copy.method.model.steps.calibrationTitle,
      body: t(copy.method.model.steps.calibrationBody),
    },
    { title: copy.method.model.steps.serveTitle, body: t(copy.method.model.steps.serveBody) },
  ];

  const tocLinks = (onDark = false) =>
    SECTIONS.map((section) => (
      <li key={section.id}>
        <a
          href={`#${section.id}`}
          aria-current={!onDark && current === section.id ? "true" : undefined}
          className={
            onDark
              ? "block border-t border-line py-2.5 text-detail text-ink no-underline"
              : `-ml-px block border-l-2 py-1.5 pl-3.5 text-detail no-underline transition-colors duration-150 ${
                  current === section.id
                    ? "border-accent font-medium text-ink"
                    : "border-transparent text-muted hover:text-ink"
                }`
          }
        >
          {t(section.label)}
        </a>
      </li>
    ));

  return (
    <div>
      <ul className="flex flex-wrap gap-2.5">
        <li className="rounded border border-accent-text px-2.5 py-2 font-mono text-caption text-accent-text">
          {fill(copy.method.modelVersion, lang, { date: modelDate(version, lang) })}
        </li>
        <li className="rounded border border-line px-2.5 py-2 font-mono text-caption text-muted">
          {fill(copy.method.chips.listings, lang, { count: integer(listings, lang) })}
        </li>
        {firstCapture && lastCapture && (
          <li className="rounded border border-line px-2.5 py-2 font-mono text-caption text-muted">
            {fill(copy.method.captures, lang, {
              count: manifest.capture_dates.length,
              first: isoDay(firstCapture, lang),
              last: isoDay(lastCapture, lang),
            })}
          </li>
        )}
        <li className="rounded border border-line px-2.5 py-2 font-mono text-caption text-muted">
          {t(copy.method.chips.rebuilt)}
        </li>
      </ul>
      <p className="mt-5 max-w-[66ch] text-base text-muted">{t(copy.method.leadDetail)}</p>

      <details className="mt-8 rounded-lg border border-line lg:hidden">
        <summary className="min-h-11 cursor-pointer px-4 py-3 font-mono text-detail text-muted">
          {t(copy.method.toc.label)}
        </summary>
        <ol className="px-4 pb-3">{tocLinks(true)}</ol>
      </details>

      {car && moto && (
        <section
          aria-label={t(copy.method.cards.errorCarLabel)}
          className="mt-10 grid gap-8 rounded-lg border border-line bg-band p-6 sm:grid-cols-2 sm:p-8 lg:grid-cols-4"
        >
          <Figure
            number={decimal(car.mape * 100, lang)}
            unit="%"
            label={t(copy.method.cards.errorCarLabel)}
            caption={fill(copy.method.cards.errorCarCaption, lang, {
              count: integer(car.n_test, lang),
            })}
            extra={
              car.temporal
                ? fill(copy.method.cards.temporalLine, lang, {
                    value: percent(car.temporal.mape * 100, lang),
                  })
                : undefined
            }
          />
          <Figure
            number={decimal(moto.mape * 100, lang)}
            unit="%"
            label={t(copy.method.cards.errorMotoLabel)}
            caption={fill(copy.method.cards.errorMotoCaption, lang, {
              count: integer(moto.n_test, lang),
            })}
            extra={
              moto.temporal
                ? fill(copy.method.cards.temporalLine, lang, {
                    value: percent(moto.temporal.mape * 100, lang),
                  })
                : undefined
            }
          />
          <Figure
            number={`${decimal(car.interval_coverage * 100, lang)} / ${decimal(
              moto.interval_coverage * 100,
              lang,
            )}`}
            unit="%"
            label={t(copy.method.cards.coverageLabel)}
            caption={t(copy.method.cards.coverageCaption)}
          />
          <Figure
            number={integer(car.n_test + moto.n_test, lang)}
            label={t(copy.method.cards.evaluatedLabel)}
            caption={fill(copy.method.cards.evaluatedCaption, lang, {
              car: integer(car.n_test, lang),
              motorcycle: integer(moto.n_test, lang),
            })}
          />
        </section>
      )}

      <div className="mt-4 grid items-start gap-14 lg:grid-cols-[12.5rem_minmax(0,1fr)]">
        <nav aria-label={t(copy.method.toc.label)} className="sticky top-24 hidden pt-14 lg:block">
          <p className="mb-3.5 font-mono text-caption uppercase tracking-[0.1em] text-muted">
            {t(copy.method.toc.label)}
          </p>
          <ol className="grid gap-0.5 border-l border-line">{tocLinks()}</ol>
        </nav>

        <div className="min-w-0 space-y-2 pb-6">
          <Section id="datos" title={t(copy.method.data.title)}>
            <Body>{t(copy.method.data.body)}</Body>
            <div className="max-w-[66ch] border-l-2 border-accent py-1 pl-4">
              <p className="font-semibold text-ink">{t(copy.method.data.askingTitle)}</p>
              <p className="mt-1 text-detail text-muted">{t(copy.method.data.askingBody)}</p>
            </div>
            <dl className="grid rounded-lg border border-line sm:grid-cols-2">
              {[
                {
                  term: copy.method.data.facts.source,
                  value: t(copy.method.data.facts.sourceValue),
                },
                {
                  term: copy.method.data.facts.capture,
                  value: fill(copy.method.data.facts.captureValue, lang, { date: lastCaptureText }),
                },
                {
                  term: copy.method.data.facts.listings,
                  value: fill(copy.method.data.facts.listingsValue, lang, {
                    cars: integer(car?.trained_on_rows ?? 0, lang),
                    motorcycles: integer(moto?.trained_on_rows ?? 0, lang),
                  }),
                },
              ].map((fact) => (
                <div key={fact.term.en} className="min-w-0 border-b border-line p-5 sm:odd:border-r">
                  <dt className="mb-2 font-mono text-caption uppercase tracking-[0.08em] text-muted">
                    {t(fact.term)}
                  </dt>
                  <dd className="text-ink">{fact.value}</dd>
                </div>
              ))}
              <div className="min-w-0 border-line p-5">
                <dt className="mb-2 font-mono text-caption uppercase tracking-[0.08em] text-muted">
                  {t(copy.method.data.facts.reproducible)}
                </dt>
                <dd className="text-ink">
                  {t(copy.method.data.reproducible)}{" "}
                  <a className="text-accent-text underline underline-offset-4 hover:no-underline" href={DATA_BRANCH_URL}>
                    {t(copy.method.data.capturesLink)}
                  </a>
                </dd>
              </div>
            </dl>
          </Section>

          <Section id="modelo" title={t(copy.method.model.title)}>
            <div className="grid items-start gap-10 xl:grid-cols-2">
              <div className="space-y-5">
                <Body>{t(copy.method.model.lead)}</Body>
                {car && moto && car.baseline_mape > 0 && moto.baseline_mape > 0 && (
                  <Body>
                    {fillNodes(copy.method.model.detail, lang, {
                      mape: term("averageError"),
                      car: points((car.baseline_mape - car.mape) * 100, lang),
                      motorcycle: points((moto.baseline_mape - moto.mape) * 100, lang),
                    })}
                  </Body>
                )}
                <Body>{fillNodes(copy.method.model.shap, lang, { shap: term("shap") })}</Body>
                <Subtitle>{t(copy.method.model.bandTitle)}</Subtitle>
                <Body>{fillNodes(copy.method.model.bandBody, lang, { range: term("range") })}</Body>
                {car && moto && car.uncalibrated_coverage > 0 && moto.uncalibrated_coverage > 0 && (
                  <Body>
                    {fillNodes(copy.method.model.bandDetail, lang, {
                      car: percent(car.uncalibrated_coverage * 100, lang),
                      motorcycle: percent(moto.uncalibrated_coverage * 100, lang),
                      conformal: term("calibration"),
                      heldOut: term("heldOut"),
                    })}
                  </Body>
                )}
              </div>
              <div>
                <Subtitle>{t(copy.method.model.stepsTitle)}</Subtitle>
                <ol className="mt-3 rounded-lg border border-line">
                  {steps.map((step, index) => (
                    <li
                      key={step.title.en}
                      className="flex items-center gap-4 border-b border-line px-5 py-4 last:border-b-0"
                    >
                      <span className="grid h-8 w-8 flex-none place-items-center rounded bg-accent font-mono text-detail font-medium text-accent-ink">
                        {index + 1}
                      </span>
                      <span>
                        <span className="block font-semibold text-ink">{t(step.title)}</span>
                        <span className="block text-detail text-muted">{step.body}</span>
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          </Section>

          <Section id="resultados" title={t(copy.method.results.title)}>
            <Body>
              {fillNodes(copy.method.results.lead, lang, {
                heldOut: term("heldOut"),
                share: heldOutShare,
              })}
            </Body>
            <Body>{t(copy.method.results.detail)}</Body>

            <div className="overflow-x-auto rounded-lg border border-line">
              <table className="w-full min-w-[42rem] border-collapse">
                <caption className="px-5 pt-4 text-left text-detail text-muted">
                  {t(copy.method.results.tableCaption)}
                </caption>
                <thead>
                  <tr>
                    {[
                      { label: copy.method.results.columnType, right: false },
                      { label: copy.method.results.columnError, right: true },
                      { label: copy.method.results.columnMedianError, right: true },
                      { label: copy.method.results.columnCoverage, right: true },
                      { label: copy.method.results.columnWidth, right: true },
                      { label: copy.method.results.columnEvaluated, right: true },
                      { label: copy.method.results.columnLabel, right: false },
                    ].map((column) => (
                      <th
                        key={column.label.en}
                        scope="col"
                        className={`whitespace-nowrap px-5 py-4 font-mono text-caption font-normal uppercase tracking-[0.08em] text-muted ${
                          column.right ? "text-right" : "text-left"
                        }`}
                      >
                        {t(column.label)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {models.map((model) => {
                    const failure = model.label_failure_codes[0];
                    const failureCopy = failure ? FAILURE_COPY[failure.code] : undefined;
                    return (
                      <tr key={model.vehicle_type}>
                        <th scope="row" className="border-t border-line px-5 py-4 text-left font-normal text-ink">
                          {verticalName(model)}
                        </th>
                        {[
                          percent(model.mape * 100, lang),
                          percent(model.median_ape * 100, lang),
                          percent(model.interval_coverage * 100, lang),
                          percent(model.interval_mean_relative_width * 100, lang, 0),
                          integer(model.n_test, lang),
                        ].map((value, index) => (
                          <td
                            key={index}
                            className="border-t border-line px-5 py-4 text-right font-mono text-ink tnum"
                          >
                            {value}
                          </td>
                        ))}
                        <td className="border-t border-line px-5 py-4 align-top">
                          <Badge published={model.publishes_label} lang={lang} />
                          {!model.publishes_label && failure && failureCopy && (
                            <span className="mt-1.5 block max-w-[22rem] text-caption text-muted">
                              {fill(failureCopy, lang, {
                                value: percent(failure.value * 100, lang, 0),
                                limit: percent(failure.limit * 100, lang, 0),
                              })}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {car?.temporal && moto?.temporal && (
              <>
                <Subtitle>{t(copy.method.results.errorsTitle)}</Subtitle>
                <div className="overflow-x-auto rounded-lg border border-line">
                  <table className="w-full min-w-[28rem] border-collapse">
                    <caption className="px-5 pt-4 text-left text-detail text-muted">
                      {t(copy.method.results.errorsCaption)}
                    </caption>
                    <thead>
                      <tr>
                        {[
                          { label: copy.method.results.columnType, right: false },
                          { label: copy.method.results.columnRandom, right: true },
                          { label: copy.method.results.columnTemporal, right: true },
                        ].map((column) => (
                          <th
                            key={column.label.en}
                            scope="col"
                            className={`whitespace-nowrap px-5 py-4 font-mono text-caption font-normal uppercase tracking-[0.08em] text-muted ${
                              column.right ? "text-right" : "text-left"
                            }`}
                          >
                            {t(column.label)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {[car, moto].map((model) => (
                        <tr key={model.vehicle_type}>
                          <th scope="row" className="border-t border-line px-5 py-4 text-left font-normal text-ink">
                            {verticalName(model)}
                          </th>
                          <td className="border-t border-line px-5 py-4 text-right font-mono font-medium text-ink tnum">
                            {percent(model.mape * 100, lang)}
                          </td>
                          <td className="border-t border-line px-5 py-4 text-right font-mono text-muted tnum">
                            {model.temporal ? percent(model.temporal.mape * 100, lang) : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Body>{fill(copy.method.results.randomDefinition, lang, { share: heldOutShare })}</Body>
                <Body>{t(copy.method.results.temporalDefinition)}</Body>
                <p className="max-w-[66ch] text-detail text-muted">
                  {fill(copy.method.results.temporalCaveat, lang, {
                    days: decimal(spanDays, lang),
                  })}
                </p>
              </>
            )}

            {car && moto && (
              <div className="grid gap-6 md:grid-cols-2">
                {car.uncalibrated_coverage > 0 && moto.uncalibrated_coverage > 0 && (
                  <Comparison
                    title={t(copy.method.results.calibrationTitle)}
                    body={t(copy.method.results.calibrationBody)}
                    max={100}
                    target={nominal * 100}
                    targetLabel={t(copy.method.results.calibrationTarget)}
                    groups={[car, moto].map((model) => ({
                      label: verticalName(model),
                      rows: [
                        {
                          label: t(copy.method.results.calibrationUncalibrated),
                          value: model.uncalibrated_coverage * 100,
                          text: percent(model.uncalibrated_coverage * 100, lang, 0),
                          strong: false,
                        },
                        {
                          label: t(copy.method.results.calibrationCalibrated),
                          value: model.interval_coverage * 100,
                          text: percent(model.interval_coverage * 100, lang),
                          strong: true,
                        },
                      ],
                    }))}
                  />
                )}
                {car.baseline_mape > 0 && moto.baseline_mape > 0 && (
                  <Comparison
                    title={t(copy.method.results.baselineTitle)}
                    body={t(copy.method.results.baselineBody)}
                    max={Math.max(car.baseline_mape, moto.baseline_mape) * 100 * 1.1}
                    groups={[car, moto].map((model) => ({
                      label: verticalName(model),
                      rows: [
                        {
                          label: t(copy.method.results.baselineLabel),
                          value: model.baseline_mape * 100,
                          text: percent(model.baseline_mape * 100, lang),
                          strong: false,
                        },
                        {
                          label: t(copy.method.results.servedLabel),
                          value: model.mape * 100,
                          text: percent(model.mape * 100, lang),
                          strong: true,
                        },
                      ],
                    }))}
                  />
                )}
              </div>
            )}

            {worstCarBrand && (
              <figure className="m-0 rounded-lg border border-line bg-surface p-5 sm:p-6">
                <h3 className="text-lg font-semibold text-ink">{t(copy.method.results.brandErrorTitle)}</h3>
                <p className="mb-5 mt-1 text-detail text-muted">
                  {fill(copy.method.results.brandErrorBody, lang, {
                    brand: worstCarBrand.segment,
                    value: percent(worstCarBrand.mape_pct, lang),
                  })}
                </p>
                <IntervalBars
                  items={carBrandErrors.map((row) => ({
                    label: row.segment,
                    value: row.mape_pct,
                    valueText: percent(row.mape_pct, lang),
                    detail: fill(copy.form.listingsCount, lang, { count: integer(row.n, lang) }),
                    tone: row.segment === worstCarBrand.segment ? "accent" : "data",
                  }))}
                  caption={fill(copy.method.results.brandErrorBody, lang, {
                    brand: worstCarBrand.segment,
                    value: percent(worstCarBrand.mape_pct, lang),
                  })}
                  columns={{
                    label: t(copy.market.columnBrand),
                    value: t(copy.method.results.columnError),
                    interval: t(copy.method.results.columnEvaluated),
                  }}
                />
              </figure>
            )}
          </Section>

          <Section id="etiqueta" title={t(copy.method.rule.title)}>
            <Body>{t(copy.method.rule.lead)}</Body>
            <Body>{t(copy.method.rule.coverageWhy)}</Body>
            <div className="grid gap-4 md:grid-cols-2">
              {models.map((model) => {
                const met = criteria(model);
                const rows = [
                  {
                    ok: met.coverage,
                    title: fill(copy.method.rule.coverageTitle, lang, {
                      min: percent(gate.min_coverage * 100, lang, 0),
                      max: percent(gate.max_coverage * 100, lang, 0),
                    }),
                    detail: fill(copy.method.rule.coverageDetail, lang, {
                      count: integer(model.n_test, lang),
                    }),
                    value: percent(model.interval_coverage * 100, lang),
                  },
                  {
                    ok: met.width,
                    title: fill(copy.method.rule.widthTitle, lang, {
                      max: percent(gate.max_relative_width * 100, lang, 0),
                    }),
                    detail: met.width
                      ? t(copy.method.rule.widthDetail)
                      : fill(copy.method.rule.widthPending, lang, {
                          max: percent(gate.max_relative_width * 100, lang, 0),
                        }),
                    value: percent(model.interval_mean_relative_width * 100, lang, 0),
                  },
                ];
                return (
                  <div key={model.vehicle_type} className="rounded-lg border border-line bg-surface p-5 sm:p-6">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <h3 className="font-display text-xl font-extrabold text-ink [font-stretch:112%]">
                        {verticalName(model)}
                      </h3>
                      <Badge published={model.publishes_label} lang={lang} />
                    </div>
                    {rows.map((row) => (
                      <div
                        key={row.title}
                        className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-baseline gap-2.5 border-t border-line py-3"
                      >
                        <span
                          className={`font-mono text-detail font-medium ${row.ok ? "text-good" : "text-bad"}`}
                          aria-label={t(row.ok ? copy.method.rule.statePass : copy.method.rule.stateFail)}
                          role="img"
                        >
                          {row.ok ? "✓" : "✗"}
                        </span>
                        <p className="text-detail text-ink">
                          {row.title}
                          <span className="mt-0.5 block text-caption text-muted">{row.detail}</span>
                        </p>
                        <span className="font-mono text-detail font-medium text-ink tnum">{row.value}</span>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
            <p className="max-w-[66ch] text-detail text-muted">{t(copy.method.rule.widthWhy)}</p>
            <p className="max-w-[66ch] text-detail text-muted">{t(copy.method.rule.inArtifact)}</p>
          </Section>

          <Section id="alcance" title={t(copy.method.scope.title)}>
            <Body>{t(copy.method.scope.lead)}</Body>
            <div className="grid gap-4 md:grid-cols-2">
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
              {departments.length > 0 && (
                <ScopeCard
                  what={fill(copy.method.scope.items.departmentsWhat, lang, {
                    count: departments.length,
                    list: listFormat.format(departments),
                  })}
                  effect={
                    thinDepartments.length > 0
                      ? fill(copy.method.scope.items.departmentsEffect, lang, {
                          min: LOW_DATA_LISTINGS,
                          thin: listFormat.format(thinDepartments),
                        })
                      : t(copy.method.scope.items.departmentEffect)
                  }
                />
              )}
              <ScopeCard
                what={t(copy.method.scope.items.otherWhat)}
                effect={t(copy.method.scope.items.otherEffect)}
              />
              <ScopeCard
                what={t(copy.method.scope.items.cityWhat)}
                effect={t(copy.method.scope.items.cityEffect)}
              />
              <ScopeCard
                what={t(copy.method.scope.items.unknownModelWhat)}
                effect={t(copy.method.scope.items.unknownModelEffect)}
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
          </Section>

          <Section id="detalle" title={t(copy.method.links.title)}>
            <ul className="flex flex-wrap gap-x-7 gap-y-3">
              {[
                { href: REPO_URL, label: copy.method.links.repo },
                { href: API_DOCS_URL, label: copy.method.links.api },
                { href: MODEL_INFO_URL, label: copy.method.links.modelInfo },
                { href: DECISIONS_URL, label: copy.method.links.decisions },
                { href: STATUS_URL, label: copy.method.links.status },
                { href: LINKEDIN_URL, label: copy.method.links.author },
              ].map((link) => (
                <li key={link.href}>
                  <a
                    className="inline-flex min-h-6 items-center text-accent-text underline underline-offset-4 hover:no-underline"
                    href={link.href}
                  >
                    {t(link.label)} ›
                  </a>
                </li>
              ))}
            </ul>
          </Section>
        </div>
      </div>
    </div>
  );
}
