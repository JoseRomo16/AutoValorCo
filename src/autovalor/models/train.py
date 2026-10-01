"""Train the valuation models and record honest out-of-sample metrics.

Today this trains the hedonic OLS baseline — the number every later ensemble is measured
against. Both metrics are reported for each run, in-sample and held out, because the
gap between them is the point: every sigma and MAPE produced during F1 was in-sample, and
quoting those as performance was the mistake this command exists to stop.

Examples:
    uv run python -m autovalor.models.train
    uv run python -m autovalor.models.train --vehicle-type car --no-mlflow
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, get_args

from autovalor.config import get_settings
from autovalor.models.dataset import (
    DEFAULT_SEED,
    DEFAULT_TEST_SIZE,
    VEHICLE_TYPES,
    Dataset,
    SplitNotPossibleError,
    SplitStrategy,
    VehicleType,
    load_split,
)
from autovalor.models.hedonic import (
    FEATURE_SETS,
    TARGET,
    FeatureSet,
    fit_hedonic,
    predict_log_price,
)
from autovalor.models.metrics import RegressionReport, regression_report

if TYPE_CHECKING:
    from sklearn.pipeline import Pipeline

logger = logging.getLogger("autovalor.models")

MODEL_NAME = "hedonic_ols"

SKOPS_TRUSTED_TYPES = ["numpy.dtype"]
"""Types MLflow's skops serializer must be told are safe to load.

The pipeline casts columns with pandas, which stores a ``numpy.dtype`` on the fitted
transformer. Declaring it is safe because the pipeline is built in this repository, in
:mod:`autovalor.models.hedonic` — the guard exists for models arriving from elsewhere.
"""


@dataclass(frozen=True)
class BaselineResult:
    """Outcome of one baseline fit.

    Attributes:
        vehicle_type: Vertical modeled.
        feature_set: Feature set used.
        train_report: In-sample error, for contrast only.
        test_report: Held-out error — the figure that may be quoted.
        params: Partition and fit parameters, for the experiment log.
        pipeline: The fitted pipeline.
    """

    vehicle_type: VehicleType
    feature_set: FeatureSet
    train_report: RegressionReport
    test_report: RegressionReport
    params: dict[str, object]
    pipeline: "Pipeline"

    @property
    def run_name(self) -> str:
        """Name this run carries in MLflow."""
        return f"{MODEL_NAME}-{self.vehicle_type}-{self.feature_set}"

    def metrics(self) -> dict[str, float]:
        """Return every metric, prefixed by the split it was measured on."""
        return {
            **{f"train_{key}": value for key, value in self.train_report.as_dict().items()},
            **{f"test_{key}": value for key, value in self.test_report.as_dict().items()},
        }


def train_baseline(dataset: Dataset, feature_set: FeatureSet) -> BaselineResult:
    """Fit the hedonic baseline on one partition and score both sides of it.

    Args:
        dataset: Train/test partition of a single vertical.
        feature_set: ``basic`` or ``full``.

    Returns:
        The fitted pipeline together with its in-sample and held-out error.
    """
    pipeline, spec = fit_hedonic(
        dataset.train,
        feature_set=feature_set,
        vehicle_type=dataset.vehicle_type,
    )

    train_report = regression_report(
        dataset.train[TARGET],
        predict_log_price(pipeline, dataset.train, spec),
    )
    test_report = regression_report(
        dataset.test[TARGET],
        predict_log_price(pipeline, dataset.test, spec),
    )

    params: dict[str, object] = {
        **dataset.describe(),
        "model": MODEL_NAME,
        "feature_set": feature_set,
        "n_features": len(pipeline.named_steps["features"].get_feature_names_out()),
    }

    logger.info("%s / %s — held out: %s", dataset.vehicle_type, feature_set, test_report.summary())
    return BaselineResult(
        vehicle_type=dataset.vehicle_type,
        feature_set=feature_set,
        train_report=train_report,
        test_report=test_report,
        params=params,
        pipeline=pipeline,
    )


def log_to_mlflow(result: BaselineResult) -> None:
    """Record one result as an MLflow run.

    Imported lazily: MLflow is slow to import and is not needed by ``--no-mlflow``
    runs or by the tests.

    Args:
        result: The fit to record.
    """
    import mlflow

    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment)

    with mlflow.start_run(run_name=result.run_name):
        mlflow.log_params(result.params)
        mlflow.log_metrics(result.metrics())
        mlflow.sklearn.log_model(
            result.pipeline,
            name=MODEL_NAME,
            skops_trusted_types=SKOPS_TRUSTED_TYPES,
        )


def format_table(results: Sequence[BaselineResult]) -> str:
    """Render the results as a fixed-width table for the terminal.

    Args:
        results: Fits to display.

    Returns:
        A table whose held-out columns are the ones to read.
    """
    # ASCII only: the development console is cp1252, see RegressionReport.summary.
    header = (
        f"{'vertical':<12} {'features':<8} {'n train':>8} {'n test':>7} "
        f"{'MAPE out':>9} {'MAPE in':>8} {'sigma out':>9} {'R2 out':>7} {'w/in 10%':>9}"
    )
    lines = [header, "-" * len(header)]
    for result in results:
        lines.append(
            f"{result.vehicle_type:<12} {result.feature_set:<8} "
            f"{result.train_report.n:>8} {result.test_report.n:>7} "
            f"{result.test_report.mape:>8.1%} {result.train_report.mape:>7.1%} "
            f"{result.test_report.sigma_log:>9.3f} {result.test_report.r2_log:>7.3f} "
            f"{result.test_report.within_10pct:>8.1%}"
        )
    return "\n".join(lines)


def run(
    *,
    vehicle_types: Sequence[VehicleType] = VEHICLE_TYPES,
    feature_sets: Sequence[FeatureSet] = FEATURE_SETS,
    strategy: SplitStrategy = "random",
    test_size: float = DEFAULT_TEST_SIZE,
    seed: int = DEFAULT_SEED,
    duckdb_path: Path | None = None,
    track: bool = True,
) -> list[BaselineResult]:
    """Train the baseline for every requested vertical and feature set.

    Args:
        vehicle_types: Verticals to model.
        feature_sets: Feature sets to fit.
        strategy: Split strategy, ``random`` or ``temporal``.
        test_size: Fraction of listings held out.
        seed: Seed for the random split.
        duckdb_path: Database written by dbt. Defaults to the configured path.
        track: Whether to record each fit as an MLflow run.

    Returns:
        One result per vertical and feature set.
    """
    results: list[BaselineResult] = []
    for vehicle_type in vehicle_types:
        dataset = load_split(
            vehicle_type,
            strategy=strategy,
            test_size=test_size,
            seed=seed,
            duckdb_path=duckdb_path,
        )
        for feature_set in feature_sets:
            result = train_baseline(dataset, feature_set)
            if track:
                log_to_mlflow(result)
            results.append(result)
    return results


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the training command."""
    parser = argparse.ArgumentParser(
        prog="autovalor-train",
        description="Train the hedonic OLS baseline and report held-out error.",
    )
    parser.add_argument(
        "--vehicle-type",
        action="append",
        choices=VEHICLE_TYPES,
        default=None,
        help="Vertical to model; repeatable. Defaults to both.",
    )
    parser.add_argument(
        "--feature-set",
        action="append",
        choices=FEATURE_SETS,
        default=None,
        help="Feature set to fit; repeatable. Defaults to both.",
    )
    parser.add_argument(
        "--split",
        choices=get_args(SplitStrategy),
        default="random",
        help=(
            "Partition strategy. 'temporal' needs captures spread over time and fails "
            "loudly when they are not (default: random)."
        ),
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=DEFAULT_TEST_SIZE,
        help=f"Fraction of listings held out (default: {DEFAULT_TEST_SIZE}).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Seed for the random split (default: {DEFAULT_SEED}).",
    )
    parser.add_argument(
        "--duckdb-path",
        type=Path,
        default=None,
        help="Database written by dbt (default: the configured AUTOVALOR_DUCKDB_PATH).",
    )
    parser.add_argument(
        "--no-mlflow",
        action="store_true",
        help="Skip MLflow tracking; useful for a quick look at the numbers.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``make train``.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` on success, ``1`` if the data cannot support the requested partition.
    """
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        results = run(
            vehicle_types=args.vehicle_type or VEHICLE_TYPES,
            feature_sets=args.feature_set or FEATURE_SETS,
            strategy=args.split,
            test_size=args.test_size,
            seed=args.seed,
            duckdb_path=args.duckdb_path,
            track=not args.no_mlflow,
        )
    except (SplitNotPossibleError, FileNotFoundError) as error:
        logger.error("%s", error)
        return 1

    sys.stdout.write(format_table(results) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
