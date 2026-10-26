"use client";

/**
 * The market dashboard: four findings, each with the chart and the sentence that says what
 * it means in money.
 *
 * Every section follows the same rule — a chart is not a finding. The reading underneath
 * each one is the point of the page, and it names the magnitude in pesos or in points so a
 * reader who does not care about regressions still leaves with something usable. The data
 * arrives as props from a server component that read the committed result tables, so this
 * file never fetches anything.
 */

import { useLang } from "./LanguageProvider";
import { IntervalBars, type BarItem } from "./charts/IntervalBars";
import { RetainedCurves, type Curve } from "./charts/RetainedCurves";
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
import { copy, fill } from "@/lib/i18n";
import {
  cop,
  copMillions,
  decimal,
  integer,
  isoDate,
  isoDay,
  percent,
  points,
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

/**
 * Pick the makes a retained-value chart shows.
 *
 * Three, not the first five in the file. The file is sorted by depreciation, so taking the
 * head showed the five makes that hold value best and left out every steep curve, which is
 * the opposite of what the section is about. The make that holds most, the one that holds
 * least and the reference are the three that carry the shape.
 */
function chooseCurves(brands: string[], referenceBrand: string | undefined): string[] {
  const first = brands[0];
  const last = brands[brands.length - 1];
  const chosen = [first, last, referenceBrand].filter(
    (brand): brand is string => brand !== undefined,
  );
  return [...new Set(chosen)];
}

/** Absolute pesos, for a figure whose sign is already carried by the sentence. */
function abs(value: number): number {
  return Math.abs(value);
}

function Section({
  title,
  help,
  reading,
  children,
}: {
  title: string;
  help: string;
  reading: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4 border-t border-slate-200 pt-8 dark:border-slate-800">
      <div className="max-w-3xl">
        <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{help}</p>
      </div>
      {children}
      <p className="max-w-3xl rounded-lg bg-slate-50 p-4 text-sm leading-relaxed text-slate-700 dark:bg-slate-900/60 dark:text-slate-300">
        {reading}
      </p>
    </section>
  );
}

function VerticalHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
      {children}
    </h3>
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
  const verticalName = (vertical: VehicleType): string =>
    t(vertical === "car" ? copy.form.car : copy.form.motorcycle);

  const notSignificant = t(copy.market.notSignificant);

  function depreciationBars(vertical: VehicleType): BarItem[] {
    return depreciation
      .filter((row) => row.vehicle_type === vertical)
      .sort((a, b) => a.annual_depreciation_pct - b.annual_depreciation_pct)
      .map((row) => ({
        label: row.brand,
        value: row.annual_depreciation_pct,
        low: row.ci_low_pct,
        high: row.ci_high_pct,
        valueText: percent(row.annual_depreciation_pct, lang),
        intervalText: `${percent(row.ci_low_pct, lang)} – ${percent(row.ci_high_pct, lang)}`,
        note: row.significant ? undefined : notSignificant,
        muted: !row.significant,
      }));
  }

  function retainedCurves(vertical: VehicleType): Curve[] {
    const brands = [
      ...new Set(retained.filter((row) => row.vehicle_type === vertical).map((row) => row.brand)),
    ];
    const reference = depreciation.find(
      (row) => row.vehicle_type === vertical && row.is_reference,
    )?.brand;
    return chooseCurves(brands, reference).map((brand) => ({
      label: brand,
      points: retained
        .filter((row) => row.vehicle_type === vertical && row.brand === brand)
        .sort((a, b) => a.age_years - b.age_years)
        .map((row) => ({ age: row.age_years, retained: row.retained_value_pct })),
    }));
  }

  function segmentLabel(row: MileageRow): string {
    const name =
      row.segment === "all"
        ? t(copy.market.mileage.segmentAll)
        : fill(copy.market.mileage.quartile, lang, { n: row.segment.replace("Q", "") });
    return `${verticalName(row.vehicle_type)} · ${name}`;
  }

  const mileageBars: BarItem[] = mileage
    .slice()
    .sort((a, b) => a.cop_per_step - b.cop_per_step)
    .map((row) => ({
      label: segmentLabel(row),
      value: row.cop_per_step,
      low: row.cop_ci_low,
      high: row.cop_ci_high,
      valueText: cop(row.cop_per_step, lang),
      intervalText: fill(copy.market.mileage.medianLabel, lang, {
        amount: copMillions(row.median_price_cop, lang),
      }),
      note: row.significant ? undefined : notSignificant,
      muted: !row.significant,
    }));

  function regionalBars(vertical: VehicleType): BarItem[] {
    return regional
      .filter((row) => row.vehicle_type === vertical)
      .sort((a, b) => b.pct_change - a.pct_change)
      .map((row) => ({
        label: row.department,
        value: row.pct_change,
        low: row.is_reference ? undefined : row.pct_ci_low,
        high: row.is_reference ? undefined : row.pct_ci_high,
        valueText: row.is_reference ? "—" : signedPercent(row.pct_change, lang),
        intervalText: row.is_reference
          ? undefined
          : `${signedPercent(row.pct_ci_low, lang)} – ${signedPercent(row.pct_ci_high, lang)}`,
        note: row.is_reference
          ? t(copy.market.reference)
          : row.significant
            ? undefined
            : notSignificant,
        muted: row.is_reference || !row.significant,
      }));
  }

  const shares: Share[] = contrast.map((row) => ({
    label: verticalName(row.vehicle_type),
    note: `${t(copy.market.catalogue.identity)} / ${t(copy.market.catalogue.condition)} = ${decimal(row.identity_over_condition, lang)}×`,
    segments: [
      { label: t(copy.market.catalogue.identity), value: row.identity_share_pct, tone: "identity" },
      { label: t(copy.market.catalogue.condition), value: row.condition_share_pct, tone: "condition" },
      { label: t(copy.market.catalogue.other), value: row.other_share_pct, tone: "other" },
    ],
  }));

  /*
   * Every figure the readings quote, derived here from the same tables the charts draw.
   *
   * These sentences used to carry the numbers as text, and the retrain made nine of them
   * false at once: "~216.000 pesos" had become 231.075, "60 puntos" had become 51,7. A
   * reading that reads its own chart cannot drift from it.
   */
  const byDepreciation = (vertical: VehicleType) =>
    depreciation
      .filter((row) => row.vehicle_type === vertical && row.significant)
      .sort((a, b) => a.annual_depreciation_pct - b.annual_depreciation_pct);

  const carRates = byDepreciation("car");
  const motoRates = byDepreciation("motorcycle");
  const motoReference = depreciation.find(
    (row) => row.vehicle_type === "motorcycle" && row.is_reference,
  );
  const medianPrice = (vertical: VehicleType) =>
    mileage.find((row) => row.vehicle_type === vertical && row.segment === "all")
      ?.median_price_cop ?? 0;

  const retainedAtOldest = (vertical: VehicleType) => {
    const oldest = Math.max(
      ...retained.filter((row) => row.vehicle_type === vertical).map((row) => row.age_years),
      0,
    );
    return retained
      .filter((row) => row.vehicle_type === vertical && row.age_years === oldest)
      .sort((a, b) => b.retained_value_pct - a.retained_value_pct);
  };
  const oldestAge = Math.max(...retained.map((row) => row.age_years), 0);
  const carRetained = retainedAtOldest("car")[0];
  const motoRetained = retainedAtOldest("motorcycle")[0];

  const carQuartiles = mileage.filter(
    (row) => row.vehicle_type === "car" && row.segment !== "all",
  );
  const carMileageAll = mileage.find(
    (row) => row.vehicle_type === "car" && row.segment === "all",
  );
  const dearestQuartile = carQuartiles
    .slice()
    .sort((a, b) => b.median_price_cop - a.median_price_cop)[0];

  const byRegion = (vertical: VehicleType) =>
    regional
      .filter((row) => row.vehicle_type === vertical)
      .sort((a, b) => b.pct_change - a.pct_change);
  const carRegions = byRegion("car");
  const motoRegions = byRegion("motorcycle");
  const ratioOf = (vertical: VehicleType) =>
    contrast.find((row) => row.vehicle_type === vertical)?.identity_over_condition ?? 0;

  const dataDate = manifest.capture_dates.at(-1);

  // The readings, assembled before the markup: a sentence that reads its own chart needs
  // several lookups, and a lookup can come back empty on a lake too thin for a segment.
  const carSlowest = carRates.at(0);
  const carFastest = carRates.at(-1);
  const motoFastest = motoRates.at(-1);
  const carMedian = medianPrice("car");

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

  const carDearest = carRegions.at(0);
  const carCheapest = carRegions.at(-1);
  const motoDearest = motoRegions.at(0);
  const motoCheapest = motoRegions.at(-1);

  const regionalReading = [
    carDearest && carCheapest
      ? fill(copy.market.regional.insightCar, lang, {
          spread: points(carDearest.pct_change - carCheapest.pct_change, lang),
          median: copMillions(carMedian, lang),
          amount: copMillions(
            ((carDearest.pct_change - carCheapest.pct_change) / 100) * carMedian,
            lang,
          ),
        })
      : "",
    motoDearest && motoCheapest
      ? fill(copy.market.regional.insightMoto, lang, {
          spread: points(motoDearest.pct_change - motoCheapest.pct_change, lang),
          high: percent(motoDearest.pct_change, lang),
          highDept: motoDearest.department,
          low: percent(abs(motoCheapest.pct_change), lang),
          lowDept: motoCheapest.department,
        })
      : "",
  ]
    .filter((sentence) => sentence !== "")
    .join(" ");

  return (
    <div className="space-y-10">
      <p className="text-sm text-slate-500 dark:text-slate-400">
        {fill(copy.market.measuredOn, lang, {
          cars: integer(manifest.gold_rows.car, lang),
          motorcycles: integer(manifest.gold_rows.motorcycle, lang),
          date: dataDate ? isoDay(dataDate, lang) : isoDate(manifest.generated_at, lang),
        })}
      </p>

      <Section
        title={t(copy.market.depreciation.title)}
        help={t(copy.market.depreciation.lead)}
        reading={depreciationReading}
      >
        <div className="space-y-8">
          <div>
            <VerticalHeading>{verticalName("car")}</VerticalHeading>
            <IntervalBars items={depreciationBars("car")} />
          </div>
          <div>
            <VerticalHeading>{verticalName("motorcycle")}</VerticalHeading>
            <IntervalBars items={depreciationBars("motorcycle")} signed />
          </div>
        </div>
      </Section>

      <Section
        title={t(copy.market.retained.title)}
        help={`${fill(copy.market.retained.lead, lang, { age: oldestAge })} ${t(
          copy.market.retained.curveNote,
        )}`}
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
      >
        {/* min-w-0 on the columns: a grid item's automatic minimum size is its content,
            so without this the chart's own min-width stretches the column past the
            viewport and the page scrolls sideways instead of the chart. */}
        <div className="grid gap-8 lg:grid-cols-2">
          <div className="min-w-0">
            <VerticalHeading>{verticalName("car")}</VerticalHeading>
            <RetainedCurves
              curves={retainedCurves("car")}
              axisLabelX={t(copy.market.retained.axisAge)}
              axisLabelY={t(copy.market.retained.axisRetained)}
            />
          </div>
          <div className="min-w-0">
            <VerticalHeading>{verticalName("motorcycle")}</VerticalHeading>
            <RetainedCurves
              curves={retainedCurves("motorcycle")}
              axisLabelX={t(copy.market.retained.axisAge)}
              axisLabelY={t(copy.market.retained.axisRetained)}
            />
          </div>
        </div>
      </Section>

      <Section
        title={t(copy.market.mileage.title)}
        help={`${t(copy.market.mileage.lead)} ${t(copy.market.mileage.leadDetail)}`}
        reading={
          carMileageAll && dearestQuartile
            ? fill(copy.market.mileage.insight, lang, {
                median: cop(abs(carMileageAll.cop_per_step), lang),
                top: cop(abs(dearestQuartile.cop_per_step), lang),
                flatCount: carQuartiles.filter((row) => !row.significant).length,
              })
            : ""
        }
      >
        <IntervalBars items={mileageBars} signed />
      </Section>

      <Section
        title={t(copy.market.regional.title)}
        help={`${t(copy.market.regional.lead)} ${t(copy.market.regional.caveat)}`}
        reading={regionalReading}
      >
        <div className="space-y-8">
          <div>
            <VerticalHeading>{verticalName("car")}</VerticalHeading>
            <IntervalBars items={regionalBars("car")} signed />
          </div>
          <div>
            <VerticalHeading>{verticalName("motorcycle")}</VerticalHeading>
            <IntervalBars items={regionalBars("motorcycle")} signed />
          </div>
        </div>
      </Section>

      <Section
        title={t(copy.market.catalogue.title)}
        help={t(copy.market.catalogue.lead)}
        reading={fill(copy.market.catalogue.insight, lang, {
          motoRatio: decimal(ratioOf("motorcycle"), lang),
          carRatio: decimal(ratioOf("car"), lang),
        })}
      >
        <ShareBar shares={shares} />
      </Section>
    </div>
  );
}
