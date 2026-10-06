"""``make results`` — run every economic analysis and export it.

One command so the numbers in ``docs/results/``, the figures in ``docs/figures/`` and the
notebook all come from the same run over the same lake. Re-running it is how a result gets
refreshed after a capture; nothing else writes those files.

The expensive part is not the regressions — those take seconds — but the LightGBM fit the
per-segment error table and the SHAP contrast need. It is tuned by default so the segment
figures reconcile with the MAPE ``make train`` publishes; ``--trials 0`` skips the search
for a quick look and says so in the manifest.

Examples:
    uv run python -m autovalor.analysis.cli
    uv run python -m autovalor.analysis.cli --trials 0 --no-figures
    uv run python -m autovalor.analysis.cli --vehicle-type car
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from autovalor.analysis import (
    catalogue,
    depreciation,
    figures,
    mileage,
    price_index,
    regional,
    segments,
)
from autovalor.analysis.export import (
    FIGURES_DIR,
    RESULTS_DIR,
    Manifest,
    now_utc,
    write_manifest,
    write_table,
)
from autovalor.config import get_settings
from autovalor.models.dataset import (
    DEFAULT_SEED,
    VEHICLE_TYPES,
    SplitNotPossibleError,
    VehicleType,
    load_gold,
    load_split,
    temporal_span_days,
)
from autovalor.models.train import train_model

logger = logging.getLogger("autovalor.analysis")


def collect(
    vehicle_types: Sequence[VehicleType],
    *,
    n_trials: int | None = None,
    seed: int = DEFAULT_SEED,
    duckdb_path: Path | None = None,
    with_model: bool = True,
) -> tuple[dict[str, pd.DataFrame], Manifest]:
    """Run every analysis over every requested vertical.

    Args:
        vehicle_types: Verticals to analyse.
        n_trials: Optuna budget for the LightGBM fit behind the segment and SHAP results.
        seed: Partition and fit seed, the same one ``make train`` uses by default, so the
            holdout here is the holdout there.
        duckdb_path: Database written by dbt. Defaults to the configured path.
        with_model: Whether to fit LightGBM at all. ``False`` keeps the pure-hedonic
            results and skips the segment error table and the catalogue contrast.

    Returns:
        The tables to export, keyed by file name, and the manifest describing the lake they
        were measured on.
    """
    tables: dict[str, list[pd.DataFrame]] = {}
    gold_rows: dict[str, int] = {}
    detail_coverage: dict[str, float] = {}
    spans: list[float] = []
    importances: dict[VehicleType, pd.DataFrame] = {}
    frames: dict[VehicleType, pd.DataFrame] = {}

    def add(name: str, frame: pd.DataFrame) -> None:
        tables.setdefault(name, []).append(frame)

    for vehicle_type in vehicle_types:
        frame = load_gold(vehicle_type, duckdb_path=duckdb_path)
        frames[vehicle_type] = frame
        gold_rows[vehicle_type] = len(frame)
        detail_coverage[vehicle_type] = float(frame["has_detail"].mean())
        spans.append(temporal_span_days(frame))

        curves = depreciation.depreciation_curves(frame, vehicle_type=vehicle_type)
        add("depreciation_by_brand", curves)
        add("retained_value_by_age", depreciation.depreciation_at_ages(curves))
        add("mileage_effect", mileage.mileage_effects(frame, vehicle_type=vehicle_type))
        add("regional_effect", regional.regional_effects(frame, vehicle_type=vehicle_type))

        if not with_model:
            continue

        dataset = load_split(vehicle_type, seed=seed, duckdb_path=duckdb_path)
        # Bands are the models' business, not this package's, and three extra quantile fits
        # would double the cost of a run that only needs the point model and its SHAP.
        result = train_model(
            dataset,
            "lightgbm",
            n_trials=n_trials,
            seed=seed,
            intervals=False,
            explain=True,
        )
        add("segment_error", segments.segment_errors(result, dataset))
        if result.importance is not None:
            importances[vehicle_type] = result.importance

    if importances:
        add("catalogue_contrast", catalogue.catalogue_contrast(importances, frames))

    skipped: dict[str, str] = {}
    for vehicle_type, frame in frames.items():
        try:
            add("price_index", price_index.hedonic_index(frame, vehicle_type=vehicle_type))
        except price_index.IndexNotPossibleError as error:
            # Expected until the weekly captures accumulate six months, so it is recorded
            # rather than raised: a run that produced everything else still succeeded, and
            # the manifest is where "why is there no index" belongs.
            skipped[f"price_index.{vehicle_type}"] = str(error)
            logger.info("no %s price index yet — %s", vehicle_type, error)

    manifest = Manifest(
        generated_at=now_utc(),
        gold_rows=gold_rows,
        capture_span_days=max(spans) if spans else 0.0,
        detail_coverage=detail_coverage,
        thresholds={
            "min_brand_listings": depreciation.MIN_BRAND_LISTINGS,
            "min_brand_model_years": depreciation.MIN_BRAND_MODEL_YEARS,
            "min_department_listings": regional.MIN_DEPARTMENT_LISTINGS,
            "min_segment_rows": segments.MIN_SEGMENT_ROWS,
            "mileage_step_km": mileage.MILEAGE_STEP_KM,
            "min_index_span_days": price_index.MIN_INDEX_SPAN_DAYS,
            "lightgbm_trials": -1 if n_trials is None else n_trials,
        },
        skipped=skipped,
    )
    return {name: pd.concat(parts, ignore_index=True) for name, parts in tables.items()}, manifest


def draw(tables: dict[str, pd.DataFrame], *, figures_dir: Path) -> list[Path]:
    """Render every figure the collected tables can support.

    Figures are skipped rather than failed when their table is missing: a ``--trials 0``
    run with no model still deserves its depreciation chart.

    Args:
        tables: Output of :func:`collect`.
        figures_dir: Directory to write the PNGs into.

    Returns:
        The paths written.
    """
    written: list[Path] = []
    for vehicle_type in VEHICLE_TYPES:

        def rows(name: str, vertical: VehicleType = vehicle_type) -> pd.DataFrame | None:
            frame = tables.get(name)
            if frame is None:
                return None
            subset = frame[frame["vehicle_type"] == vertical]
            return None if subset.empty else subset

        curves = rows("depreciation_by_brand")
        if curves is not None:
            written.append(
                figures.depreciation_figure(
                    curves, figures_dir / f"depreciation-{vehicle_type}.png"
                )
            )
        retained = rows("retained_value_by_age")
        if retained is not None:
            written.append(
                figures.retained_value_figure(
                    retained, figures_dir / f"retained-value-{vehicle_type}.png"
                )
            )
        effects = rows("mileage_effect")
        if effects is not None:
            written.append(
                figures.mileage_figure(effects, figures_dir / f"mileage-{vehicle_type}.png")
            )
        regions = rows("regional_effect")
        if regions is not None:
            written.append(
                figures.regional_figure(regions, figures_dir / f"regional-{vehicle_type}.png")
            )
        errors = rows("segment_error")
        if errors is not None:
            written.append(
                figures.segment_error_figure(
                    errors, figures_dir / f"segment-error-{vehicle_type}.png"
                )
            )
    return written


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the analysis command."""
    parser = argparse.ArgumentParser(
        prog="autovalor-results",
        description="Estimate the economic results and export them to docs/.",
    )
    parser.add_argument(
        "--vehicle-type",
        action="append",
        choices=VEHICLE_TYPES,
        default=None,
        help="Vertical to analyse; repeatable. Defaults to both.",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=None,
        help=(
            "Optuna budget for the LightGBM fit behind the segment errors and the SHAP "
            "contrast. Zero skips the search; omit for the tuned budget that matches "
            "`make train`."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Partition and fit seed (default: {DEFAULT_SEED}).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=RESULTS_DIR,
        help=f"Where the JSON and CSV go (default: {RESULTS_DIR}).",
    )
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=FIGURES_DIR,
        help=f"Where the PNGs go (default: {FIGURES_DIR}).",
    )
    parser.add_argument(
        "--duckdb-path",
        type=Path,
        default=None,
        help="Database written by dbt (default: the configured AUTOVALOR_DUCKDB_PATH).",
    )
    parser.add_argument(
        "--no-model",
        action="store_true",
        help=(
            "Skip the LightGBM fit, and with it the per-segment error table and the "
            "catalogue contrast. Leaves the hedonic results, which cost seconds."
        ),
    )
    parser.add_argument(
        "--no-figures",
        action="store_true",
        help="Export the tables without drawing the PNGs.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``make results``.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` on success, ``1`` if the lake cannot support the analysis.
    """
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        tables, manifest = collect(
            args.vehicle_type or VEHICLE_TYPES,
            n_trials=args.trials,
            seed=args.seed,
            duckdb_path=args.duckdb_path,
            with_model=not args.no_model,
        )
    except (SplitNotPossibleError, FileNotFoundError, ValueError) as error:
        logger.error("%s", error)
        return 1

    for name, frame in tables.items():
        write_table(frame, name, output_dir=args.output_dir, manifest=manifest)
    if not args.no_figures:
        draw(tables, figures_dir=args.figures_dir)
    write_manifest(manifest, output_dir=args.output_dir)

    sys.stdout.write(
        f"exported {len(tables)} tables to {args.output_dir} "
        f"over {sum(manifest.gold_rows.values())} gold rows\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
