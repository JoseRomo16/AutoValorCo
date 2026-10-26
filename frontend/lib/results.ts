/**
 * The published results, read from the repository **at build time**.
 *
 * The market page could call `/market` and the methodology page could call `/model-info`,
 * and both would then take a minute to render whenever the free-tier API is asleep — for
 * numbers that are committed files in this very repository. So they are read from disk
 * while the static export is being generated and baked into the HTML. The pages are
 * instant, work with the API down, and cannot show a figure that disagrees with the commit
 * they were built from.
 *
 * The cost is that the site is as fresh as its last deploy. That is the right trade here:
 * `make results` and `make export-model` are commits, and a commit redeploys the site.
 *
 * Only ever imported from server components. `fs` in a client component is a build error,
 * which is the compiler enforcing exactly this boundary.
 */

import { readFileSync } from "node:fs";
import path from "node:path";

/** The repository root, from `frontend/` — the build runs with that as its cwd. */
const REPO_ROOT = path.join(process.cwd(), "..");
const RESULTS_DIR = path.join(REPO_ROOT, "docs", "results");
const MODELS_DIR = path.join(REPO_ROOT, "artifacts", "models");

function readJson<T>(file: string): T {
  return JSON.parse(readFileSync(file, "utf-8")) as T;
}

export type VehicleType = "car" | "motorcycle";

export type Manifest = {
  generated_at: string;
  gold_rows: Record<VehicleType, number>;
  capture_span_days: number;
  /** The dates the site was read, earliest first: the last one is how old the data is. */
  capture_dates: string[];
  detail_coverage: Record<VehicleType, number>;
  /** Share of each vertical whose title named no make the seeds know. */
  unresolved_make: Record<VehicleType, number>;
  skipped: Record<string, string>;
  /** The same refusals as data, so the reason can be written in Spanish. */
  skipped_codes: Record<string, { code: string; ready_on?: string; span_days?: number }>;
};

export type DepreciationRow = {
  vehicle_type: VehicleType;
  brand: string;
  is_reference: boolean;
  listings: number;
  annual_depreciation_pct: number;
  ci_low_pct: number;
  ci_high_pct: number;
  age_only_pct: number;
  half_life_years: number;
  significant: boolean;
};

export type RetainedRow = {
  vehicle_type: VehicleType;
  brand: string;
  age_years: number;
  retained_value_pct: number;
};

export type MileageRow = {
  vehicle_type: VehicleType;
  segment: string;
  n: number;
  median_price_cop: number;
  median_mileage_km: number;
  pct_per_step: number;
  cop_per_step: number;
  cop_ci_low: number;
  cop_ci_high: number;
  significant: boolean;
};

export type RegionalRow = {
  vehicle_type: VehicleType;
  department: string;
  pct_change: number;
  pct_ci_low: number;
  pct_ci_high: number;
  listings: number;
  is_reference: boolean;
  significant: boolean;
};

export type CatalogueContrastRow = {
  vehicle_type: VehicleType;
  identity_share_pct: number;
  condition_share_pct: number;
  other_share_pct: number;
  identity_over_condition: number;
  median_age_years: number;
  annual_depreciation_pct: number;
};

export type SegmentErrorRow = {
  vehicle_type: VehicleType;
  model: string;
  segment_kind: string;
  segment: string;
  n: number;
  mape_pct: number;
  median_ape_pct: number;
  sigma_log: number;
  within_10pct: number;
};

/** Why the label was withheld, as data rather than as an English sentence. */
export type LabelFailureCode = {
  code: string;
  value: number;
  limit: number;
  message: string;
};

/** The second measurement, on a partition ordered by date. Null while the lake is young. */
export type TemporalMetrics = {
  mape: number;
  median_ape: number;
  n_train: number;
  n_test: number;
  span_days: number;
} | null;

/** What the served bundle says about itself, the same numbers `/model-info` returns. */
export type ServedModelInfo = {
  vehicle_type: VehicleType;
  version: string;
  mape: number;
  median_ape: number;
  /** The OLS reference fitted on the same partition. The gap is what the ensemble buys. */
  baseline_mape: number;
  interval_coverage: number;
  interval_mean_relative_width: number;
  /** What the three quantile models covered before the conformal widening. */
  uncalibrated_coverage: number;
  crossing_rate: number;
  n_test: number;
  n_calibration: number;
  publishes_label: boolean;
  label_failures: string[];
  label_failure_codes: LabelFailureCode[];
  temporal: TemporalMetrics;
  trained_on_rows: number;
  n_train: number;
  catalogue_makes: number;
};

type BundleManifest = {
  vehicle_type: VehicleType;
  version: string;
  metrics: {
    mape: number;
    median_ape: number;
    n_test: number;
    interval_coverage: number;
    interval_mean_relative_width: number;
    baseline_mape?: number;
  };
  interval: {
    crossing_rate: number;
    n_calibration: number;
    uncalibrated_coverage?: number;
  };
  metrics_temporal?: TemporalMetrics;
  label: { publishes_label: boolean; failures: string[]; failure_codes?: LabelFailureCode[] };
  lake: { rows: number; n_train: number };
};

type BundleCatalog = { brands: unknown[] };

export function manifest(): Manifest {
  return readJson<Manifest>(path.join(RESULTS_DIR, "manifest.json"));
}

export function depreciation(): DepreciationRow[] {
  return readJson<DepreciationRow[]>(path.join(RESULTS_DIR, "depreciation_by_brand.json"));
}

export function retainedValue(): RetainedRow[] {
  return readJson<RetainedRow[]>(path.join(RESULTS_DIR, "retained_value_by_age.json"));
}

export function mileageEffect(): MileageRow[] {
  return readJson<MileageRow[]>(path.join(RESULTS_DIR, "mileage_effect.json"));
}

export function regionalEffect(): RegionalRow[] {
  return readJson<RegionalRow[]>(path.join(RESULTS_DIR, "regional_effect.json"));
}

export function catalogueContrast(): CatalogueContrastRow[] {
  return readJson<CatalogueContrastRow[]>(path.join(RESULTS_DIR, "catalogue_contrast.json"));
}

/**
 * Read both served bundles' own manifests.
 *
 * Straight from `artifacts/models/`, which is what the API image serves, so the
 * methodology page cannot quote a MAPE the deployed model does not have.
 */
export function servedModels(): ServedModelInfo[] {
  return (["car", "motorcycle"] as const).map((vehicleType) => {
    const directory = path.join(MODELS_DIR, vehicleType);
    const bundle = readJson<BundleManifest>(path.join(directory, "model.json"));
    const catalog = readJson<BundleCatalog>(path.join(directory, "catalog.json"));
    return {
      vehicle_type: bundle.vehicle_type,
      version: bundle.version,
      mape: bundle.metrics.mape,
      median_ape: bundle.metrics.median_ape,
      // Format 1 bundles carry neither figure. Reading them as zero would print "0 %" on
      // the page, so the sections that need them check for it and say nothing instead.
      baseline_mape: bundle.metrics.baseline_mape ?? 0,
      interval_coverage: bundle.metrics.interval_coverage,
      interval_mean_relative_width: bundle.metrics.interval_mean_relative_width,
      uncalibrated_coverage: bundle.interval.uncalibrated_coverage ?? 0,
      crossing_rate: bundle.interval.crossing_rate,
      n_test: bundle.metrics.n_test,
      n_calibration: bundle.interval.n_calibration,
      publishes_label: bundle.label.publishes_label,
      label_failures: bundle.label.failures,
      label_failure_codes: bundle.label.failure_codes ?? [],
      temporal: bundle.metrics_temporal ?? null,
      trained_on_rows: bundle.lake.rows,
      n_train: bundle.lake.n_train,
      catalogue_makes: catalog.brands.length,
    };
  });
}

/**
 * Per-segment error, which is where the trim limitation stops being an assertion.
 *
 * The methodology page names the worst make and its error rather than claiming trim
 * matters, and both come from here.
 */
export function segmentError(): SegmentErrorRow[] {
  return readJson<SegmentErrorRow[]>(path.join(RESULTS_DIR, "segment_error.json"));
}
