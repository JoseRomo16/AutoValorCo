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
from autovalor.models.dataset import (
    DEFAULT_SEED,
    VEHICLE_TYPES,
    SplitNotPossibleError,
    VehicleType,
    load_split,
    temporal_span_days,
)
from autovalor.models.train import INTERVAL_KIND, train_model

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


def export(
    vehicle_types: Sequence[VehicleType] = VEHICLE_TYPES,
    *,
    directory: Path = ARTIFACTS_DIR,
    n_trials: int | None = None,
    seed: int = DEFAULT_SEED,
    version: str | None = None,
    duckdb_path: Path | None = None,
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
        results.append((dataset, result))

    stamp = version or default_version(total_rows)
    written: list[Path] = []
    for dataset, result in results:
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
                },
                lake={
                    "rows": dataset.n_train + dataset.n_test,
                    "n_train": dataset.n_train,
                    "n_test": dataset.n_test,
                    "split_seed": seed,
                    "capture_span_days": round(temporal_span_days(dataset.test), 3),
                },
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
        )
    except (SplitNotPossibleError, FileNotFoundError) as error:
        logger.error("%s", error)
        return 1

    for path in written:
        sys.stdout.write(f"wrote {path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
