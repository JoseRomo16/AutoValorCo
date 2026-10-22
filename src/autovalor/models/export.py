"""``make export-model`` — train the served model and write it to ``artifacts/models/``.

Separate from ``make train`` on purpose. ``train`` is a measurement: it fits several models
on several verticals, prints a comparison table and is judged on whether the numbers are
honest. This is a build step: it fits exactly what the API serves — the tuned LightGBM and
its calibrated band, per vertical — and writes it where the Docker build can copy it.

The version string defaults to the date plus the lake's row count, so two bundles built
from different lakes cannot claim to be the same model. ``/model-info`` reports it.

Examples:
    uv run python -m autovalor.models.export
    uv run python -m autovalor.models.export --trials 0 --version dev
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from autovalor.config import get_settings
from autovalor.models.bundle import ARTIFACTS_DIR, save_bundle
from autovalor.models.catalog import build_catalog
from autovalor.models.dataset import (
    DEFAULT_SEED,
    VEHICLE_TYPES,
    SplitNotPossibleError,
    VehicleType,
    load_split,
    temporal_span_days,
)
from autovalor.models.train import BASELINE_KIND, BASELINE_VARIANT, INTERVAL_KIND, train_model

logger = logging.getLogger("autovalor.models")


def default_version(total_rows: int) -> str:
    """Return a version string that cannot collide across lakes.

    Args:
        total_rows: Gold rows the bundle was trained on.

    Returns:
        Something like ``2026-10-06.11691``: the build date and the size of the lake
        behind it. A model retrained on a bigger lake is a different model, and the
        version should say so without anyone having to remember to bump it.
    """
    return f"{datetime.now(UTC):%Y-%m-%d}.{total_rows}"


def temporal_metrics(
    vehicle_type: VehicleType,
    *,
    n_trials: int | None,
    seed: int,
    duckdb_path: Path | None,
) -> dict[str, float] | None:
    """Measure the same model family on a time-ordered partition.

    A second measurement, never the published one. The served model is fitted on the
    grouped random split, because that is the partition every published figure was taken
    on and swapping it would make the numbers incomparable. What this answers is the
    question the random split cannot: how the model scores when it trains on the past and
    is tested on the future, which is the shape of the job it actually does.

    Args:
        vehicle_type: Vertical to measure.
        n_trials: Optuna budget, the same one the served fit uses.
        seed: Partition and fit seed.
        duckdb_path: Database written by dbt.

    Returns:
        The held-out error, or ``None`` when the lake does not span enough days for the
        partition to separate past from future honestly. ``None`` rather than an
        exception: this is an extra measurement, and a lake too young for it must not stop
        the model being exported.
    """
    try:
        dataset = load_split(vehicle_type, strategy="temporal", seed=seed, duckdb_path=duckdb_path)
    except SplitNotPossibleError as error:
        logger.warning("%s: no temporal measurement - %s", vehicle_type, error)
        return None

    result = train_model(
        dataset, INTERVAL_KIND, n_trials=n_trials, seed=seed, intervals=False, explain=False
    )
    logger.info(
        "%s temporal - MAPE %.1f%% on %d rows held out by date",
        vehicle_type,
        result.test_report.mape * 100,
        result.test_report.n,
    )
    return {
        "mape": result.test_report.mape,
        "median_ape": result.test_report.median_ape,
        "sigma_log": result.test_report.sigma_log,
        "r2_log": result.test_report.r2_log,
        "n_train": float(dataset.n_train),
        "n_test": float(result.test_report.n),
        "span_days": round(temporal_span_days(dataset.test), 3),
    }


def export(
    vehicle_types: Sequence[VehicleType] = VEHICLE_TYPES,
    *,
    directory: Path = ARTIFACTS_DIR,
    n_trials: int | None = None,
    seed: int = DEFAULT_SEED,
    version: str | None = None,
    duckdb_path: Path | None = None,
    temporal: bool = True,
) -> list[Path]:
    """Fit and write one bundle per vertical.

    Args:
        vehicle_types: Verticals to export.
        directory: Root to write bundles into, one subdirectory per vertical.
        n_trials: Optuna budget; ``None`` uses the tuned default so the served model is the
            one the published metrics describe.
        seed: Partition and fit seed, the same one ``make train`` uses.
        version: Version string; defaults to :func:`default_version`.
        duckdb_path: Database written by dbt.
        temporal: Whether to also measure the time-ordered partition. On by default
            because the methodology page shows it next to the published figure; off is for
            a quick rebuild, and the field then reads ``null`` rather than stale.

    Returns:
        The manifest paths written.
    """
    results = []
    total_rows = 0
    for vehicle_type in vehicle_types:
        dataset = load_split(vehicle_type, seed=seed, duckdb_path=duckdb_path)
        total_rows += dataset.n_train + dataset.n_test
        # explain=False: SHAP at export time would measure what is already measured by
        # `make train`, and /explain computes its attributions per request anyway.
        result = train_model(
            dataset, INTERVAL_KIND, n_trials=n_trials, seed=seed, intervals=True, explain=False
        )
        # The OLS reference, on the same partition. Cheap next to the tree search, and the
        # only way "LightGBM beats the baseline by N points" can be a figure the site reads
        # instead of a sentence somebody typed.
        baseline = train_model(
            dataset,
            BASELINE_KIND,
            feature_set=BASELINE_VARIANT,
            seed=seed,
            intervals=False,
            explain=False,
        )
        temporal_result = (
            temporal_metrics(vehicle_type, n_trials=n_trials, seed=seed, duckdb_path=duckdb_path)
            if temporal
            else None
        )
        results.append((dataset, result, baseline, temporal_result))

    stamp = version or default_version(total_rows)
    written: list[Path] = []
    for dataset, result, baseline, temporal_result in results:
        if result.interval_model is None or result.interval is None or result.label is None:
            msg = f"no band was fitted for {result.vehicle_type}; cannot export a served model"
            raise RuntimeError(msg)
        written.append(
            save_bundle(
                directory / result.vehicle_type,
                vehicle_type=result.vehicle_type,
                version=stamp,
                point=result.model,  # type: ignore[arg-type]
                interval=result.interval_model,
                label=result.label,
                metrics={
                    "mape": result.test_report.mape,
                    "median_ape": result.test_report.median_ape,
                    "sigma_log": result.test_report.sigma_log,
                    "r2_log": result.test_report.r2_log,
                    "n_test": float(result.test_report.n),
                    "interval_coverage": result.interval.coverage,
                    "interval_mean_relative_width": result.interval.mean_relative_width,
                    "baseline_mape": baseline.test_report.mape,
                    "baseline_sigma_log": baseline.test_report.sigma_log,
                    "baseline_r2_log": baseline.test_report.r2_log,
                },
                uncalibrated=result.interval_uncalibrated,
                metrics_temporal=temporal_result,
                lake={
                    "rows": dataset.n_train + dataset.n_test,
                    "n_train": dataset.n_train,
                    "n_test": dataset.n_test,
                    "split_seed": seed,
                    "capture_span_days": round(temporal_span_days(dataset.test), 3),
                },
                # Built from the training rows, not the whole lake: the lists /catalog
                # publishes have to be the levels this model was actually fitted on.
                catalog=build_catalog(dataset.train, vehicle_type=result.vehicle_type),
            )
        )
    return written


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the export command."""
    parser = argparse.ArgumentParser(
        prog="autovalor-export-model",
        description="Train the served model and write it to artifacts/models/.",
    )
    parser.add_argument(
        "--vehicle-type",
        action="append",
        choices=VEHICLE_TYPES,
        default=None,
        help="Vertical to export; repeatable. Defaults to both.",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=None,
        help="Optuna budget. Omit for the tuned default, which is what ships.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Partition and fit seed (default: {DEFAULT_SEED}).",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Version string for /model-info; defaults to the date plus the lake size.",
    )
    parser.add_argument(
        "--no-temporal",
        action="store_true",
        help=(
            "Skip the time-ordered measurement. It doubles the search, and the field "
            "reads null rather than stale when it is skipped."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ARTIFACTS_DIR,
        help=f"Where to write the bundles (default: {ARTIFACTS_DIR}).",
    )
    parser.add_argument(
        "--duckdb-path",
        type=Path,
        default=None,
        help="Database written by dbt (default: the configured AUTOVALOR_DUCKDB_PATH).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``make export-model``.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` on success, ``1`` if the lake cannot support the partition.
    """
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        written = export(
            args.vehicle_type or VEHICLE_TYPES,
            directory=args.output_dir,
            n_trials=args.trials,
            seed=args.seed,
            version=args.version,
            duckdb_path=args.duckdb_path,
            temporal=not args.no_temporal,
        )
    except (SplitNotPossibleError, FileNotFoundError) as error:
        logger.error("%s", error)
        return 1

    for path in written:
        sys.stdout.write(f"wrote {path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
