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
import { RetainedCurves, type Curve, type CurveRole } from "./charts/RetainedCurves";
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
import { isWideInterval, mileageByQuartile, withOrigin, type CurvePoint } from "@/lib/market";
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
  reading: string;
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
      {reading && (
        <div className="max-w-3xl rounded-lg border border-line p-4 sm:p-5">
          <p className="mb-1.5 font-mono text-xs uppercase tracking-[0.1em] text-accent-text">
            {readingLabel}
          </p>
          <p className="leading-relaxed text-ink">{reading}</p>
        </div>
      )}
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
      <p className="mt-2 flex-1 text-sm leading-relaxed text-muted">{body}</p>
      <a
        href={href}
        className="mt-4 inline-flex min-h-6 items-center text-sm font-medium text-accent-text underline-offset-4 hover:underline"
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

  /**
   * Three curves, not the first five in the file: the make that holds most, the one that
   * holds least and the regression's reference. Those carry the shape; more lines only
   * crowd it. When the reference is also an extreme it keeps the extreme's role.
   */
  function retainedCurves(vertical: VehicleType): Curve[] {
    const ranked = retainedAtOldest(vertical);
    const reference = depreciation.find(
      (row) => row.vehicle_type === vertical && row.is_reference,
    )?.brand;
    const roles: [string | undefined, CurveRole][] = [
      [ranked.at(0)?.brand, "best"],
      [ranked.at(-1)?.brand, "worst"],
      [reference, "reference"],
    ];
    const seen = new Set<string>();
    return roles
      .filter((entry): entry is [string, CurveRole] => {
        const [brand] = entry;
        if (brand === undefined || seen.has(brand)) return false;
        seen.add(brand);
        return true;
      })
      .map(([brand, role]) => ({
        label: brand,
        role,
        points: withOrigin(
          retained
            .filter((row) => row.vehicle_type === vertical && row.brand === brand)
            .sort((a, b) => a.age_years - b.age_years)
            .map((row) => ({ age: row.age_years, retained: row.retained_value_pct })),
        ),
      }));
  }

  function retainedCaption(vertical: VehicleType): string {
    const ranked = retainedAtOldest(vertical);
    const best = ranked.at(0);
    const worst = ranked.at(-1);
    return best && worst
      ? fill(copy.market.retained.caption, lang, {
          bestBrand: best.brand,
          bestPct: percent(best.retained_value_pct, lang, 0),
          worstBrand: worst.brand,
          worstPct: percent(worst.retained_value_pct, lang, 0),
          age: best.age_years,
        })
      : "";
  }

  const retainedLegend = (point: CurvePoint): string =>
    fill(copy.market.retained.legendPoint, lang, {
      pct: percent(point.retained, lang, 0),
      age: point.age,
    });

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
   * Every figure the readings quote, derived from the same tables the charts draw. These
   * sentences used to carry the numbers as text, and a retrain made nine of them false at
   * once. A reading that reads its own chart cannot drift from it.
   */
  const significantOf = (vertical: VehicleType) =>
    depreciationOf(vertical).filter((row) => row.significant);
  const carSlowest = significantOf("car").at(0);
  const carFastest = significantOf("car").at(-1);
  const motoFastest = significantOf("motorcycle").at(-1);
  const motoSlowest = depreciationOf("motorcycle").at(0);
  const motoReference = depreciation.find(
    (row) => row.vehicle_type === "motorcycle" && row.is_reference,
  );
  const carMedian =
    mileage.find((row) => row.vehicle_type === "car" && row.segment === "all")?.median_price_cop ??
    0;

  const depreciationReading = [
    carSlowest && carFastest
      ? fill(copy.market.depreciation.insightCar, lang, {
          lowBrand: carSlowest.brand,
          lowPct: percent(carSlowest.annual_depreciation_pct, lang),
          highBrand: carFastest.brand,
          highPct: percent(carFastest.annual_depreciation_pct, lang),
          median: copMillions(carMedian, lang),
          gap: copMillions(
            ((carFastest.annual_depreciation_pct - carSlowest.annual_depreciation_pct) / 100) *
              carMedian,
            lang,
          ),
        })
      : "",
    motoReference && motoFastest
      ? fill(copy.market.depreciation.insightMoto, lang, {
          refBrand: motoReference.brand,
          refPct: percent(motoReference.annual_depreciation_pct, lang),
          highBrand: motoFastest.brand,
          highPct: percent(motoFastest.annual_depreciation_pct, lang),
        })
      : "",
  ]
    .filter((sentence) => sentence !== "")
    .join(" ");

  const carRetained = retainedAtOldest("car")[0];
  const motoRetained = retainedAtOldest("motorcycle")[0];

  const { all: carMileageAll, quartiles: carQuartiles } = mileageByQuartile(mileage, "car");
  const topQuartile = carQuartiles.at(-1);

  const carRegions = covered("car");
  const motoRegions = covered("motorcycle");
  const carHighest = carRegions.at(0);
  const carCheapest = carRegions.at(-1);
  const motoHighest = motoRegions.at(0);
  const motoCheapest = motoRegions.at(-1);

  const regionalReading = [
    carHighest && carCheapest
      ? fill(copy.market.regional.insightCar, lang, {
          spread: points(carHighest.pct_change - carCheapest.pct_change, lang),
          median: copMillions(carMedian, lang),
          amount: copMillions(
            ((carHighest.pct_change - carCheapest.pct_change) / 100) * carMedian,
            lang,
          ),
        })
      : "",
    motoHighest && motoCheapest
      ? fill(copy.market.regional.insightMoto, lang, {
          spread: points(motoHighest.pct_change - motoCheapest.pct_change, lang),
          high: percent(motoHighest.pct_change, lang),
          highDept: motoHighest.department,
          low: percent(Math.abs(motoCheapest.pct_change), lang),
          lowDept: motoCheapest.department,
        })
      : "",
  ]
    .filter((sentence) => sentence !== "")
    .join(" ");

  const dataDate = manifest.capture_dates.at(-1);
  const findings = copy.market.findings;
  const sections = copy.market.sections;

  return (
    <div className="space-y-12">
      <p className="font-mono text-sm text-muted">
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
        reading={depreciationReading}
        readingLabel={t(copy.market.insightLabel)}
      >
        <VehicleTabs id={IDS.depreciation}>
          {(vertical) => (
            <IntervalBars
              items={depreciationBars(vertical)}
              signed={vertical === "motorcycle"}
              caption={depreciationCaption(vertical)}
              columns={columns(copy.market.columnBrand)}
              highlight={highlight}
              onHighlight={setHighlight}
            />
          )}
        </VehicleTabs>
      </Section>

      <Section
        id={IDS.retained}
        title={t(copy.market.retained.title)}
        help={`${fill(copy.market.retained.lead, lang, { age: oldestAge })} ${t(
          copy.market.retained.curveNote,
        )} ${t(copy.market.retained.originNote)}`}
        reading={
          carRetained && motoRetained
            ? fill(copy.market.retained.insight, lang, {
                carBrand: carRetained.brand,
                carPct: percent(carRetained.retained_value_pct, lang, 0),
                motoBrand: motoRetained.brand,
                motoPct: percent(motoRetained.retained_value_pct, lang, 0),
                age: oldestAge,
              })
            : ""
        }
        readingLabel={t(copy.market.insightLabel)}
      >
        <VehicleTabs id={IDS.retained}>
          {(vertical) => (
            <RetainedCurves
              curves={retainedCurves(vertical)}
              axisLabelX={t(copy.market.retained.axisAge)}
              axisLabelY={t(copy.market.retained.axisRetained)}
              formatLastPoint={retainedLegend}
              formatValue={(value) => percent(value, lang, 0)}
              formatAge={(age) => fill(copy.market.retained.atAge, lang, { age })}
              caption={retainedCaption(vertical)}
              brandColumn={t(copy.market.columnBrand)}
              highlight={highlight}
              onHighlight={setHighlight}
            />
          )}
        </VehicleTabs>
      </Section>

      <Section
        id={IDS.mileage}
        title={t(copy.market.mileage.title)}
        help={`${t(copy.market.mileage.lead)} ${t(copy.market.mileage.leadDetail)}`}
        reading={
          carMileageAll && topQuartile
            ? fill(copy.market.mileage.insight, lang, {
                median: cop(Math.abs(carMileageAll.cop_per_step), lang),
                top: cop(Math.abs(topQuartile.cop_per_step), lang),
                flatCount: carQuartiles.filter((row) => !row.significant).length,
              })
            : ""
        }
        readingLabel={t(copy.market.insightLabel)}
      >
        <VehicleTabs id={IDS.mileage}>
          {(vertical) => (
            <IntervalBars
              items={mileageBars(vertical)}
              signed
              caption={mileageCaption(vertical)}
              columns={columns(copy.market.columnGroup)}
            />
          )}
        </VehicleTabs>
      </Section>

      <Section
        id={IDS.regional}
        title={t(copy.market.regional.title)}
        help={`${t(copy.market.regional.lead)} ${t(copy.market.regional.caveat)}`}
        reading={regionalReading}
        readingLabel={t(copy.market.insightLabel)}
      >
        <VehicleTabs id={IDS.regional}>
          {(vertical) => (
            <IntervalBars
              items={regionalBars(vertical)}
              signed
              caption={regionalCaption(vertical)}
              columns={columns(copy.market.columnDepartment)}
            />
          )}
        </VehicleTabs>
        <p className="max-w-3xl text-sm leading-relaxed text-muted">
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
        readingLabel={t(copy.market.insightLabel)}
      >
        <ShareBar shares={shares} />
      </Section>
    </div>
  );
}
