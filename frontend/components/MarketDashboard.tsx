"use client";

/**
 * The market dashboard: four findings up top, then one section per finding, each with its
 * chart and the sentence that says what it means in money.
 *
 * A chart is not a finding. The reading under each one is the point of the page, and it
 * names the magnitude in pesos or in points so a reader who does not care about
 * regressions still leaves with something usable. The data arrives as props from a server
 * component that read the committed result tables, so this file never fetches anything,
 * and every figure a sentence quotes is derived here from the same rows its chart draws.
 */

import { useState } from "react";

import { useLang } from "./LanguageProvider";
import { VehicleTabs } from "./VehicleTabs";
import { IntervalBars, type BarItem } from "./charts/IntervalBars";
import { BrandPicker } from "./charts/BrandPicker";
import { RetainedCurves, axisFloor, type Curve } from "./charts/RetainedCurves";
import { ShareBar, type Share } from "./charts/ShareBar";
import type {
  CatalogueContrastRow,
  DepreciationRow,
  Manifest,
  MileageRow,
  RegionalRow,
  RetainedRow,
  VehicleType,
} from "@/lib/results";
import { copy, fill, type Localized } from "@/lib/i18n";
import { isThin, orderRegions } from "@/lib/listings";
import { currentBrands, setBrands, useBrandSelection } from "@/lib/brandSelection";
import {
  MAX_COMPARED,
  isWideInterval,
  mileageByQuartile,
  toggleBrand,
  withOrigin,
} from "@/lib/market";
import {
  cop,
  copMillions,
  decimal,
  integer,
  isoDate,
  isoDay,
  percent,
  points,
  signedCop,
  signedPercent,
} from "@/lib/format";

type Props = {
  manifest: Manifest;
  depreciation: DepreciationRow[];
  retained: RetainedRow[];
  mileage: MileageRow[];
  regional: RegionalRow[];
  contrast: CatalogueContrastRow[];
};

/** Section anchors, linked from the finding cards. */
const IDS = {
  depreciation: "depreciacion",
  retained: "valor-retenido",
  mileage: "kilometraje",
  regional: "regiones",
  catalogue: "marca-o-estado",
} as const;

/** The bordered "Reading" card: what a chart means, in one paragraph. */
function Reading({ label, text }: { label: string; text: string }) {
  if (!text) return null;
  return (
    <div data-reading className="mt-6 max-w-3xl rounded-lg border border-line p-4 sm:p-5">
      <p className="mb-1.5 font-mono text-caption uppercase tracking-[0.1em] text-accent-text">
        {label}
      </p>
      <p className="leading-relaxed text-ink">{text}</p>
    </div>
  );
}

/**
 * One finding. A section with Cars/Motorcycles tabs puts its reading inside the tab panel,
 * so the paragraph follows the vertical on screen; only the catalogue section, which
 * compares both verticals in one chart, passes its reading here.
 */
function Section({
  id,
  title,
  help,
  reading,
  readingLabel,
  children,
}: {
  id: string;
  title: string;
  help: string;
  reading?: string;
  readingLabel: string;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className="scroll-mt-24 space-y-6 border-t border-line pt-10"
    >
      <div className="max-w-3xl">
        <h2
          id={`${id}-title`}
          className="font-display text-2xl font-bold tracking-tight text-ink [font-stretch:112%]"
        >
          {title}
        </h2>
        <p className="mt-2 text-muted">{help}</p>
      </div>
      {children}
      {reading !== undefined && <Reading label={readingLabel} text={reading} />}
    </section>
  );
}

function FindingCard({
  figure,
  title,
  body,
  href,
  link,
}: {
  figure: string;
  title: string;
  body: string;
  href: string;
  link: string;
}) {
  return (
    <li className="flex flex-col rounded-lg border border-line p-5">
      <p className="font-mono text-3xl font-medium text-ink tnum">{figure}</p>
      <h2 className="mt-3 font-semibold leading-snug text-ink">{title}</h2>
      <p className="mt-2 flex-1 text-detail text-muted">{body}</p>
      <a
        href={href}
        className="mt-4 inline-flex min-h-6 items-center text-detail font-medium text-accent-text underline-offset-4 hover:underline"
      >
        {link} ›
      </a>
    </li>
  );
}

export function MarketDashboard({
  manifest,
  depreciation,
  retained,
  mileage,
  regional,
  contrast,
}: Props) {
  const { lang, t } = useLang();
  const [highlight, setHighlight] = useState<string | null>(null);

  const notSignificant = t(copy.market.notSignificant);
  const verticalName = (vertical: VehicleType): string =>
    t(vertical === "car" ? copy.form.car : copy.form.motorcycle);

  function tooltip(label: string, value: string, interval?: string): string {
    return interval
      ? fill(copy.market.tooltip, lang, { label, value, interval })
      : fill(copy.market.tooltipNoInterval, lang, { label, value });
  }

  const columns = (label: Localized) => ({
    label: t(label),
    value: t(copy.market.columnValue),
    interval: t(copy.market.columnInterval),
  });

  // --- Depreciation -------------------------------------------------------------------

  const depreciationOf = (vertical: VehicleType) =>
    depreciation
      .filter((row) => row.vehicle_type === vertical)
      .sort((a, b) => a.annual_depreciation_pct - b.annual_depreciation_pct);

  function depreciationBars(vertical: VehicleType): BarItem[] {
    return depreciationOf(vertical).map((row) => {
      const interval = `${percent(row.ci_low_pct, lang)} – ${percent(row.ci_high_pct, lang)}`;
      const wide =
        row.significant &&
        isWideInterval(row.annual_depreciation_pct, row.ci_low_pct, row.ci_high_pct);
      return {
        label: row.brand,
        value: row.annual_depreciation_pct,
        low: row.ci_low_pct,
        high: row.ci_high_pct,
        valueText: percent(row.annual_depreciation_pct, lang),
        intervalText: interval,
        note: !row.significant ? notSignificant : wide ? t(copy.market.wideInterval) : undefined,
        muted: !row.significant,
        wide,
        tooltip: tooltip(row.brand, percent(row.annual_depreciation_pct, lang), interval),
      };
    });
  }

  function depreciationCaption(vertical: VehicleType): string {
    const rows = depreciationOf(vertical);
    const slow = rows.at(0);
    const fast = rows.at(-1);
    return slow && fast
      ? fill(copy.market.depreciation.caption, lang, {
          slowBrand: slow.brand,
          slowPct: percent(slow.annual_depreciation_pct, lang),
          fastBrand: fast.brand,
          fastPct: percent(fast.annual_depreciation_pct, lang),
        })
      : "";
  }

  // --- Retained value -----------------------------------------------------------------

  const oldestAge = Math.max(...retained.map((row) => row.age_years), 0);

  const retainedAtOldest = (vertical: VehicleType) => {
    const oldest = Math.max(
      ...retained.filter((row) => row.vehicle_type === vertical).map((row) => row.age_years),
      0,
    );
    return retained
      .filter((row) => row.vehicle_type === vertical && row.age_years === oldest)
      .sort((a, b) => b.retained_value_pct - a.retained_value_pct);
  };

  const retainedOf = (vertical: VehicleType, brand: string) =>
    withOrigin(
      retained
        .filter((row) => row.vehicle_type === vertical && row.brand === brand)
        .sort((a, b) => a.age_years - b.age_years)
        .map((row) => ({ age: row.age_years, retained: row.retained_value_pct })),
    );

  /**
   * What the chart opens with: the make that holds most, the one that holds least and the
   * regression's reference. Those carry the shape; the reader adds or removes from there.
   */
  function defaultBrands(vertical: VehicleType): string[] {
    const ranked = retainedAtOldest(vertical);
    const reference = depreciation.find(
      (row) => row.vehicle_type === vertical && row.is_reference,
    )?.brand;
    const picks = [ranked.at(0)?.brand, ranked.at(-1)?.brand, reference];
    return [...new Set(picks.filter((brand): brand is string => brand !== undefined))];
  }

  const brandSelection = useBrandSelection();

  /** A stored choice, or the defaults, minus any make the data no longer has. */
  function cleanBrands(vertical: VehicleType, stored: string[] | null): string[] {
    const known = new Set(retainedAtOldest(vertical).map((row) => row.brand));
    const chosen = stored ?? defaultBrands(vertical);
    return chosen.filter((brand) => known.has(brand)).slice(0, MAX_COMPARED);
  }

  const selectedBrands = (vertical: VehicleType) => cleanBrands(vertical, brandSelection[vertical]);

  function retainedCurves(vertical: VehicleType): Curve[] {
    const selected = selectedBrands(vertical);
    return retainedAtOldest(vertical).map((row) => {
      const slot = selected.indexOf(row.brand);
      return {
        label: row.brand,
        points: retainedOf(vertical, row.brand),
        slot: slot === -1 ? null : slot,
      };
    });
  }

  const flatBrands = (vertical: VehicleType) =>
    new Set(
      depreciation
        .filter((row) => row.vehicle_type === vertical && !row.significant)
        .map((row) => row.brand),
    );

  const listFormat = new Intl.ListFormat(lang === "es" ? "es" : "en", { type: "conjunction" });

  /** The comparison sentence for the chosen makes, highest first, from the data. */
  function retainedComparison(vertical: VehicleType): string {
    const selected = new Set(selectedBrands(vertical));
    const rows = retainedAtOldest(vertical).filter((row) => selected.has(row.brand));
    const first = rows.at(0);
    const last = rows.at(-1);
    if (!first || !last) return t(copy.market.retained.compareNone);
    const parts = [
      fill(copy.market.retained.compare, lang, {
        age: first.age_years,
        list: listFormat.format(
          rows.map((row) =>
            fill(copy.market.retained.compareItem, lang, {
              brand: row.brand,
              pct: percent(row.retained_value_pct, lang, 0),
            }),
          ),
        ),
      }),
    ];
    if (rows.length > 1) {
      parts.push(
        fill(copy.market.retained.compareSpread, lang, {
          // From the rounded shares the sentence prints, so "59 % … 37 %" reads as 22 points.
          spread: points(
            Math.round(first.retained_value_pct) - Math.round(last.retained_value_pct),
            lang,
            0,
          ),
        }),
      );
    }
    const flat = rows.filter((row) => flatBrands(vertical).has(row.brand));
    for (const row of flat) {
      parts.push(fill(copy.market.retained.flatNote, lang, { brand: row.brand }));
    }
    return parts.join(" ");
  }

  function retainedReading(vertical: VehicleType): string {
    const shape = vertical === "car" ? copy.market.retained.shapeCar : copy.market.retained.shapeMoto;
    return `${t(shape)} ${retainedComparison(vertical)}`;
  }

  // --- Mileage ------------------------------------------------------------------------

  function mileageBar(row: MileageRow, label: string, separatorAfter = false): BarItem {
    const interval = `${signedCop(row.cop_ci_low, lang)} – ${signedCop(row.cop_ci_high, lang)}`;
    return {
      label,
      value: row.cop_per_step,
      low: row.cop_ci_low,
      high: row.cop_ci_high,
      valueText: signedCop(row.cop_per_step, lang),
      intervalText: interval,
      detail: fill(copy.market.mileage.medianLabel, lang, {
        amount: copMillions(row.median_price_cop, lang),
      }),
      note: row.significant ? undefined : notSignificant,
      muted: !row.significant,
      separatorAfter,
      tooltip: tooltip(label, signedCop(row.cop_per_step, lang), interval),
    };
  }

  function mileageBars(vertical: VehicleType): BarItem[] {
    const { all, quartiles } = mileageByQuartile(mileage, vertical);
    return [
      ...(all ? [mileageBar(all, t(copy.market.mileage.segmentAll), true)] : []),
      ...quartiles.map((row) =>
        mileageBar(row, fill(copy.market.mileage.quartile, lang, { n: row.segment.replace("Q", "") })),
      ),
    ];
  }

  function mileageCaption(vertical: VehicleType): string {
    const { all, quartiles } = mileageByQuartile(mileage, vertical);
    const top = quartiles.at(-1);
    return all && top
      ? fill(copy.market.mileage.caption, lang, {
          all: signedCop(all.cop_per_step, lang),
          top: signedCop(top.cop_per_step, lang),
        })
      : "";
  }

  // --- Regions ------------------------------------------------------------------------

  function regionalBars(vertical: VehicleType): BarItem[] {
    return orderRegions(regional.filter((row) => row.vehicle_type === vertical)).map((row) => {
      const thin = isThin(row.listings);
      const interval = row.is_reference
        ? undefined
        : `${signedPercent(row.pct_ci_low, lang)} – ${signedPercent(row.pct_ci_high, lang)}`;
      return {
        label: row.department,
        value: row.pct_change,
        low: row.is_reference ? undefined : row.pct_ci_low,
        high: row.is_reference ? undefined : row.pct_ci_high,
        valueText: row.is_reference ? "—" : signedPercent(row.pct_change, lang),
        intervalText: interval,
        note: row.is_reference
          ? t(copy.market.reference)
          : thin
            ? t(copy.market.regional.fewListings)
            : row.significant
              ? undefined
              : notSignificant,
        reference: row.is_reference,
        muted: !row.is_reference && (thin || !row.significant),
        // Dearer than Bogotá is bad news for a buyer; cheaper is good news.
        tone: row.pct_change > 0 ? "bad" : "good",
        tooltip: row.is_reference
          ? undefined
          : tooltip(row.department, signedPercent(row.pct_change, lang), interval),
      };
    });
  }

  // The readings and captions quote extremes among well-covered departments only: the
  // thin ones are on the chart, last and flagged, but a region with a few dozen listings
  // is not the country's cheapest on the strength of them.
  const covered = (vertical: VehicleType) =>
    orderRegions(regional.filter((row) => row.vehicle_type === vertical)).filter(
      (row) => !isThin(row.listings),
    );

  function regionalCaption(vertical: VehicleType): string {
    const rows = covered(vertical);
    const high = rows.at(0);
    const low = rows.at(-1);
    return high && low
      ? fill(copy.market.regional.caption, lang, {
          high: signedPercent(high.pct_change, lang),
          highDept: high.department,
          low: signedPercent(low.pct_change, lang),
          lowDept: low.department,
        })
      : "";
  }

  // --- Catalogue ----------------------------------------------------------------------

  const shares: Share[] = contrast.map((row) => ({
    label: verticalName(row.vehicle_type),
    note: `${t(copy.market.catalogue.identity)} / ${t(copy.market.catalogue.condition)} = ${decimal(row.identity_over_condition, lang)}×`,
    segments: [
      {
        label: t(copy.market.catalogue.identity),
        value: row.identity_share_pct,
        valueText: percent(row.identity_share_pct, lang, 0),
        tone: "identity",
      },
      {
        label: t(copy.market.catalogue.condition),
        value: row.condition_share_pct,
        valueText: percent(row.condition_share_pct, lang, 0),
        tone: "condition",
      },
      {
        label: t(copy.market.catalogue.other),
        value: row.other_share_pct,
        valueText: percent(row.other_share_pct, lang, 0),
        tone: "other",
      },
    ],
  }));
  const ratioOf = (vertical: VehicleType) =>
    contrast.find((row) => row.vehicle_type === vertical)?.identity_over_condition ?? 0;

  // --- Readings -----------------------------------------------------------------------
  /*
   * One reading per vertical, shown inside its tab: the paragraph under a chart talks
   * about the vehicles the chart is showing, instead of folding cars and motorcycles into
   * one sentence. Every figure is derived from the same tables the charts draw; these
   * sentences once carried numbers as text, and a retrain made nine of them false at once.
   */
  const significantOf = (vertical: VehicleType) =>
    depreciationOf(vertical).filter((row) => row.significant);
  const motoSlowest = depreciationOf("motorcycle").at(0);
  const medianPrice = (vertical: VehicleType) =>
    mileage.find((row) => row.vehicle_type === vertical && row.segment === "all")
      ?.median_price_cop ?? 0;
  const yearlyGap = (low: DepreciationRow, high: DepreciationRow, median: number) =>
    copMillions(((high.annual_depreciation_pct - low.annual_depreciation_pct) / 100) * median, lang);

  function depreciationReading(vertical: VehicleType): string {
    const slowest = significantOf(vertical).at(0);
    const fastest = significantOf(vertical).at(-1);
    if (!slowest || !fastest) return "";
    const median = medianPrice(vertical);
    if (vertical === "car") {
      return fill(copy.market.depreciation.insightCar, lang, {
        lowBrand: slowest.brand,
        lowPct: percent(slowest.annual_depreciation_pct, lang),
        highBrand: fastest.brand,
        highPct: percent(fastest.annual_depreciation_pct, lang),
        median: copMillions(median, lang),
        gap: yearlyGap(slowest, fastest, median),
      });
    }
    const reference = depreciation.find(
      (row) => row.vehicle_type === "motorcycle" && row.is_reference,
    );
    return [
      reference
        ? fill(copy.market.depreciation.insightMoto, lang, {
            refBrand: reference.brand,
            refPct: percent(reference.annual_depreciation_pct, lang),
            highBrand: fastest.brand,
            highPct: percent(fastest.annual_depreciation_pct, lang),
          })
        : "",
      fill(copy.market.depreciation.insightMotoGap, lang, {
        median: copMillions(median, lang),
        lowBrand: slowest.brand,
        lowPct: percent(slowest.annual_depreciation_pct, lang),
        highBrand: fastest.brand,
        highPct: percent(fastest.annual_depreciation_pct, lang),
        gap: yearlyGap(slowest, fastest, median),
      }),
    ]
      .filter((sentence) => sentence !== "")
      .join(" ");
  }

  function mileageReading(vertical: VehicleType): string {
    const { all, quartiles } = mileageByQuartile(mileage, vertical);
    const top = quartiles.at(-1);
    if (!all || !top) return "";
    return fill(
      vertical === "car" ? copy.market.mileage.insightCar : copy.market.mileage.insightMoto,
      lang,
      {
        price: copMillions(all.median_price_cop, lang),
        median: cop(Math.abs(all.cop_per_step), lang),
        top: cop(Math.abs(top.cop_per_step), lang),
        flatCount: quartiles.filter((row) => !row.significant).length,
      },
    );
  }

  function regionalReading(vertical: VehicleType): string {
    const rows = covered(vertical);
    const highest = rows.at(0);
    const cheapest = rows.at(-1);
    if (!highest || !cheapest) return "";
    const spread = highest.pct_change - cheapest.pct_change;
    const main =
      vertical === "car"
        ? fill(copy.market.regional.insightCar, lang, {
            spread: points(spread, lang),
            median: copMillions(medianPrice("car"), lang),
            amount: copMillions((spread / 100) * medianPrice("car"), lang),
          })
        : fill(copy.market.regional.insightMoto, lang, {
            spread: points(spread, lang),
            high: percent(highest.pct_change, lang),
            highDept: highest.department,
            low: percent(Math.abs(cheapest.pct_change), lang),
            lowDept: cheapest.department,
          });
    const thin = regional
      .filter((row) => row.vehicle_type === vertical && isThin(row.listings))
      .map((row) => row.department);
    const note =
      thin.length === 0
        ? ""
        : fill(
            thin.length === 1 ? copy.market.regional.thinOne : copy.market.regional.thinMany,
            lang,
            { departments: listFormat.format(thin) },
          );
    return [main, note].filter((sentence) => sentence !== "").join(" ");
  }

  const { all: carMileageAll } = mileageByQuartile(mileage, "car");
  const motoHighest = covered("motorcycle").at(0);

  const dataDate = manifest.capture_dates.at(-1);
  const readingLabel = t(copy.market.insightLabel);
  const findings = copy.market.findings;
  const sections = copy.market.sections;

  return (
    // No browser scroll anchoring here: VehicleTabs compensates the jump itself, and two
    // corrections for one change would overshoot.
    <div className="space-y-12 [overflow-anchor:none]">
      <p className="font-mono text-detail text-muted">
        {fill(copy.market.measuredOn, lang, {
          cars: integer(manifest.gold_rows.car, lang),
          motorcycles: integer(manifest.gold_rows.motorcycle, lang),
          date: dataDate ? isoDay(dataDate, lang) : isoDate(manifest.generated_at, lang),
        })}
      </p>

      <section aria-label={t(copy.market.findingsTitle)}>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {motoSlowest && (
            <FindingCard
              figure={percent(motoSlowest.annual_depreciation_pct, lang)}
              title={t(findings.flatMotoTitle)}
              body={fill(
                motoSlowest.significant ? findings.flatMotoBodySignificant : findings.flatMotoBody,
                lang,
                {
                  brand: motoSlowest.brand,
                  pct: percent(motoSlowest.annual_depreciation_pct, lang),
                },
              )}
              href={`#${IDS.depreciation}`}
              link={t(sections.depreciation)}
            />
          )}
          {carMileageAll && (
            <FindingCard
              figure={signedCop(carMileageAll.cop_per_step, lang)}
              title={t(findings.mileageTitle)}
              body={fill(findings.mileageBody, lang, {
                amount: cop(Math.abs(carMileageAll.cop_per_step), lang),
                median: copMillions(carMileageAll.median_price_cop, lang),
              })}
              href={`#${IDS.mileage}`}
              link={t(sections.mileage)}
            />
          )}
          {motoHighest && (
            <FindingCard
              figure={signedPercent(motoHighest.pct_change, lang)}
              title={fill(findings.regionalTitle, lang, { department: motoHighest.department })}
              body={t(findings.regionalBody)}
              href={`#${IDS.regional}`}
              link={t(sections.regional)}
            />
          )}
          <FindingCard
            figure={`${decimal(ratioOf("motorcycle"), lang)}×`}
            title={t(findings.catalogueTitle)}
            body={fill(findings.catalogueBody, lang, {
              ratio: decimal(ratioOf("motorcycle"), lang),
            })}
            href={`#${IDS.catalogue}`}
            link={t(sections.catalogue)}
          />
        </ul>
      </section>

      <Section
        id={IDS.depreciation}
        title={t(copy.market.depreciation.title)}
        help={`${t(copy.market.depreciation.lead)} ${t(copy.market.depreciation.orderNote)}`}
        readingLabel={readingLabel}
      >
        <VehicleTabs id={IDS.depreciation}>
          {(vertical) => (
            <>
              <IntervalBars
                items={depreciationBars(vertical)}
                signed={vertical === "motorcycle"}
                caption={depreciationCaption(vertical)}
                columns={columns(copy.market.columnBrand)}
                highlight={highlight}
                onHighlight={setHighlight}
              />
              <Reading label={readingLabel} text={depreciationReading(vertical)} />
            </>
          )}
        </VehicleTabs>
      </Section>

      <Section
        id={IDS.retained}
        title={t(copy.market.retained.title)}
        help={`${fill(copy.market.retained.lead, lang, { age: oldestAge })} ${t(
          copy.market.retained.originNote,
        )}`}
        readingLabel={readingLabel}
      >
        <VehicleTabs id={IDS.retained}>
          {(vertical) => {
            const selected = selectedBrands(vertical);
            const flat = flatBrands(vertical);
            const curves = retainedCurves(vertical);
            return (
              <>
                <BrandPicker
                  brands={retainedAtOldest(vertical).map((row) => ({
                    label: row.brand,
                    valueText: percent(row.retained_value_pct, lang, 0),
                    note: flat.has(row.brand) ? notSignificant : undefined,
                  }))}
                  selected={selected}
                  max={MAX_COMPARED}
                  onToggle={(brand) =>
                    setBrands(
                      vertical,
                      toggleBrand(cleanBrands(vertical, currentBrands(vertical)), brand),
                    )
                  }
                  onReset={() => setBrands(vertical, null)}
                  onClear={() => setBrands(vertical, [])}
                  onHighlight={setHighlight}
                  text={{
                    group: t(copy.market.retained.picker.group),
                    help: fill(copy.market.retained.picker.help, lang, { max: MAX_COMPARED }),
                    status: fill(copy.market.retained.picker.status, lang, {
                      count: selected.length,
                      max: MAX_COMPARED,
                    }),
                    full: fill(copy.market.retained.picker.full, lang, { max: MAX_COMPARED }),
                    reset: t(copy.market.retained.picker.reset),
                    clear: t(copy.market.retained.picker.clear),
                  }}
                />
                <div className="mt-5">
                  <RetainedCurves
                    curves={curves}
                    axisLabelX={t(copy.market.retained.axisAge)}
                    axisLabelY={t(copy.market.retained.axisRetained)}
                    formatValue={(value) => percent(value, lang, 0)}
                    formatAge={(age) => fill(copy.market.retained.atAge, lang, { age })}
                    caption={retainedComparison(vertical)}
                    brandColumn={t(copy.market.columnBrand)}
                    highlight={highlight}
                  />
                  {axisFloor(curves) > 0 && (
                    <p className="mt-2 text-caption text-muted">
                      {fill(copy.market.retained.axisNote, lang, { floor: axisFloor(curves) })}
                    </p>
                  )}
                </div>
                <Reading label={readingLabel} text={retainedReading(vertical)} />
              </>
            );
          }}
        </VehicleTabs>
      </Section>

      <Section
        id={IDS.mileage}
        title={t(copy.market.mileage.title)}
        help={`${t(copy.market.mileage.lead)} ${t(copy.market.mileage.leadDetail)}`}
        readingLabel={readingLabel}
      >
        <VehicleTabs id={IDS.mileage}>
          {(vertical) => (
            <>
              <IntervalBars
                items={mileageBars(vertical)}
                signed
                caption={mileageCaption(vertical)}
                columns={columns(copy.market.columnGroup)}
              />
              <Reading label={readingLabel} text={mileageReading(vertical)} />
            </>
          )}
        </VehicleTabs>
      </Section>

      <Section
        id={IDS.regional}
        title={t(copy.market.regional.title)}
        help={`${t(copy.market.regional.lead)} ${t(copy.market.regional.caveat)}`}
        readingLabel={readingLabel}
      >
        <VehicleTabs id={IDS.regional}>
          {(vertical) => (
            <>
              <IntervalBars
                items={regionalBars(vertical)}
                signed
                caption={regionalCaption(vertical)}
                columns={columns(copy.market.columnDepartment)}
              />
              <Reading label={readingLabel} text={regionalReading(vertical)} />
            </>
          )}
        </VehicleTabs>
        <p className="max-w-3xl text-detail text-muted">
          {t(copy.market.regional.modelNote)}
        </p>
      </Section>

      <Section
        id={IDS.catalogue}
        title={t(copy.market.catalogue.title)}
        help={t(copy.market.catalogue.lead)}
        reading={fill(copy.market.catalogue.insight, lang, {
          motoRatio: decimal(ratioOf("motorcycle"), lang),
          carRatio: decimal(ratioOf("car"), lang),
        })}
        readingLabel={readingLabel}
      >
        <ShareBar shares={shares} />
      </Section>
    </div>
  );
}
