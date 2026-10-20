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
import { copy } from "@/lib/i18n";
import type { Localized } from "@/lib/i18n";
import { cop, copCompact, integer, isoDate, percent, signedPercent } from "@/lib/format";

type Props = {
  manifest: Manifest;
  depreciation: DepreciationRow[];
  retained: RetainedRow[];
  mileage: MileageRow[];
  regional: RegionalRow[];
  contrast: CatalogueContrastRow[];
};

/** How many makes a retained-value chart shows before it becomes a hairball. */
const MAX_CURVES = 5;

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
    const brands = [...new Set(retained.filter((row) => row.vehicle_type === vertical).map((row) => row.brand))];
    return brands.slice(0, MAX_CURVES).map((brand) => ({
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
        : `${t(copy.market.mileage.quartile)} ${row.segment.replace("Q", "")}`;
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
      intervalText: `${t(copy.market.mileage.medianPrice)} ${copCompact(row.median_price_cop, lang)}`,
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
    note: `${t(copy.market.catalogue.identity)} / ${t(copy.market.catalogue.condition)} = ${row.identity_over_condition.toFixed(1)}×`,
    segments: [
      { label: t(copy.market.catalogue.identity), value: row.identity_share_pct, tone: "identity" },
      { label: t(copy.market.catalogue.condition), value: row.condition_share_pct, tone: "condition" },
      { label: t(copy.market.catalogue.other), value: row.other_share_pct, tone: "other" },
    ],
  }));

  const measured: Localized = {
    es: `${t(copy.market.measuredOn)} ${integer(manifest.gold_rows.car, "es")} ${t(copy.form.car).toLowerCase()}s y ${integer(manifest.gold_rows.motorcycle, "es")} ${t(copy.form.motorcycle).toLowerCase()}s`,
    en: `${t(copy.market.measuredOn)} ${integer(manifest.gold_rows.car, "en")} cars and ${integer(manifest.gold_rows.motorcycle, "en")} motorcycles`,
  };

  return (
    <div className="space-y-10">
      <p className="text-sm text-slate-500 dark:text-slate-400">
        {measured[lang]} · {t(copy.market.generated)} {isoDate(manifest.generated_at, lang)}
      </p>

      <Section
        title={t(copy.market.depreciation.title)}
        help={t(copy.market.depreciation.help)}
        reading={`${t(copy.market.depreciation.readingCar)} ${t(copy.market.depreciation.readingMoto)}`}
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
        help={t(copy.market.retained.help)}
        reading={t(copy.market.retained.reading)}
      >
        {/* min-w-0 on the columns: a grid item's automatic minimum size is its content,
            so without this the chart's own min-width stretches the column past the
            viewport and the page scrolls sideways instead of the chart. */}
        <div className="grid gap-8 lg:grid-cols-2">
          <div className="min-w-0">
            <VerticalHeading>{verticalName("car")}</VerticalHeading>
            <RetainedCurves
              curves={retainedCurves("car")}
              axisLabelX={t(copy.market.retained.age)}
              axisLabelY={t(copy.market.retained.retainedPct)}
            />
          </div>
          <div className="min-w-0">
            <VerticalHeading>{verticalName("motorcycle")}</VerticalHeading>
            <RetainedCurves
              curves={retainedCurves("motorcycle")}
              axisLabelX={t(copy.market.retained.age)}
              axisLabelY={t(copy.market.retained.retainedPct)}
            />
          </div>
        </div>
      </Section>

      <Section
        title={t(copy.market.mileage.title)}
        help={t(copy.market.mileage.help)}
        reading={t(copy.market.mileage.reading)}
      >
        <IntervalBars items={mileageBars} signed />
      </Section>

      <Section
        title={t(copy.market.regional.title)}
        help={t(copy.market.regional.help)}
        reading={`${t(copy.market.regional.readingCar)} ${t(copy.market.regional.readingMoto)}`}
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
        help={t(copy.market.catalogue.help)}
        reading={t(copy.market.catalogue.reading)}
      >
        <ShareBar shares={shares} />
      </Section>
    </div>
  );
}
