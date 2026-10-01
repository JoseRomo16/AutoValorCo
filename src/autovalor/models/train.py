"""Train the valuation models and record honest out-of-sample metrics.

Three models live behind one command: the hedonic OLS baseline and the two tree ensembles
that have to beat it. Every fit reports both sides of the split, because the gap between
them is the point — each sigma and MAPE produced during F1 was in-sample, and quoting
those as performance was the mistake this command exists to stop.

The tree models are tuned with Optuna against grouped folds of the training rows only;
the holdout is scored once, at the end. See :mod:`autovalor.models.tuning`.

Examples:
    uv run python -m autovalor.models.train
    uv run python -m autovalor.models.train --model lightgbm --vehicle-type car --trials 5
    uv run python -m autovalor.models.train --model hedonic --no-mlflow
"""

import argparse
import logging
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Protocol, get_args

import numpy as np
import pandas as pd

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
    HedonicModel,
    fit_hedonic_model,
)
from autovalor.models.metrics import RegressionReport, regression_report
from autovalor.models.trees import DEFAULT_PARAMS, FittedTree, TreeModel, fit_tree
from autovalor.models.tuning import DEFAULT_TRIALS, search, trials_for

logger = logging.getLogger("autovalor.models")

ModelKind = Literal["hedonic", "lightgbm", "catboost"]

MODEL_KINDS: tuple[ModelKind, ...] = get_args(ModelKind)

BASELINE_KIND: Final = "hedonic"
BASELINE_VARIANT: Final = "full"
"""The run every other model is compared against in the result table.

Declared ``Final`` so a comparison against them narrows ``ModelKind`` down to the two tree
models, which is what lets the dispatch below stay type-safe without a cast.
"""

SKOPS_TRUSTED_TYPES = ["numpy.dtype"]
"""Types MLflow's skops serializer must be told are safe to load.

Only the hedonic pipeline needs this: it casts columns with pandas, which stores a
``numpy.dtype`` on the fitted transformer. Declaring it is safe because the pipeline is
built in this repository, in :mod:`autovalor.models.hedonic` — the guard exists for models
arriving from elsewhere. The tree models use their own MLflow flavors and never touch
skops.
"""


class FittedModel(Protocol):
    """Anything this module can score: a model that turns gold rows into log prices."""

    def predict_log_price(self, frame: pd.DataFrame) -> np.ndarray:
        """Predict ``log(price)`` for a gold-shaped frame."""
        ...


@dataclass(frozen=True)
class ModelResult:
    """Outcome of one fit.

    Attributes:
        vehicle_type: Vertical modeled.
        model_kind: Model that was fitted.
        variant: Feature set for the baseline, ``tuned`` or ``default`` for the trees.
        train_report: In-sample error, for contrast only.
        test_report: Held-out error — the figure that may be quoted.
        params: Partition and fit parameters, for the experiment log.
        model: The fitted model.
        cv_mape: Cross-validated MAPE from the search, when one ran.
        trials: One row per Optuna trial, when a search ran.
    """

    vehicle_type: VehicleType
    model_kind: ModelKind
    variant: str
    train_report: RegressionReport
    test_report: RegressionReport
    params: dict[str, object]
    model: FittedModel
    cv_mape: float | None = None
    trials: pd.DataFrame | None = None

    @property
    def run_name(self) -> str:
        """Name this run carries in MLflow."""
        return f"{self.model_kind}-{self.vehicle_type}-{self.variant}"

    @property
    def is_baseline(self) -> bool:
        """Whether this is the run everything else is compared against."""
        return self.model_kind == BASELINE_KIND and self.variant == BASELINE_VARIANT

    def metrics(self) -> dict[str, float]:
        """Return every metric, prefixed by the split it was measured on."""
        metrics = {
            **{f"train_{key}": value for key, value in self.train_report.as_dict().items()},
            **{f"test_{key}": value for key, value in self.test_report.as_dict().items()},
        }
        if self.cv_mape is not None:
            metrics["cv_mape"] = self.cv_mape
        return metrics


def train_model(
    dataset: Dataset,
    model_kind: ModelKind,
    *,
    feature_set: FeatureSet = BASELINE_VARIANT,
    n_trials: int | None = None,
    seed: int = DEFAULT_SEED,
) -> ModelResult:
    """Fit one model on a partition and score both sides of it.

    Args:
        dataset: Train/test partition of a single vertical.
        model_kind: Model to fit.
        feature_set: Feature set, for the hedonic baseline only.
        n_trials: Optuna budget for the tree models; defaults to the model's entry in
            :data:`autovalor.models.tuning.DEFAULT_TRIALS`. ``0`` skips the search and
            uses :data:`autovalor.models.trees.DEFAULT_PARAMS`.
        seed: Seed for the search and the models.

    Returns:
        The fitted model together with its in-sample and held-out error.

    Raises:
        ValueError: If ``model_kind`` is not recognised.
    """
    if model_kind not in MODEL_KINDS:
        msg = f"unknown model {model_kind!r}"
        raise ValueError(msg)

    model: FittedModel
    variant: str
    extra: dict[str, object] = {}
    cv_mape: float | None = None
    trials: pd.DataFrame | None = None

    if model_kind == BASELINE_KIND:
        variant = feature_set
        hedonic: HedonicModel = fit_hedonic_model(
            dataset.train, feature_set=feature_set, vehicle_type=dataset.vehicle_type
        )
        model = hedonic
        extra["n_features"] = len(hedonic.pipeline.named_steps["features"].get_feature_names_out())
    else:
        tree_kind: TreeModel = model_kind
        if trials_for(tree_kind, n_trials) > 0:
            result = search(
                dataset.train,
                model_kind=tree_kind,
                vehicle_type=dataset.vehicle_type,
                n_trials=n_trials,
                seed=seed,
            )
            variant = "tuned"
            best_params = result.best_params
            cv_mape = result.cv_mape
            trials = result.trials
            extra["n_trials"] = result.n_trials
        else:
            variant = "default"
            best_params = dict(DEFAULT_PARAMS[tree_kind])
        tree: FittedTree = fit_tree(
            dataset.train,
            model_kind=tree_kind,
            vehicle_type=dataset.vehicle_type,
            params=best_params,
            seed=seed,
        )
        model = tree
        extra.update({f"param_{key}": value for key, value in best_params.items()})

    train_report = regression_report(dataset.train[TARGET], model.predict_log_price(dataset.train))
    test_report = regression_report(dataset.test[TARGET], model.predict_log_price(dataset.test))

    params: dict[str, object] = {
        **dataset.describe(),
        "model": model_kind,
        "variant": variant,
        **extra,
    }

    logger.info(
        "%s / %s %s — held out: %s",
        dataset.vehicle_type,
        model_kind,
        variant,
        test_report.summary(),
    )
    return ModelResult(
        vehicle_type=dataset.vehicle_type,
        model_kind=model_kind,
        variant=variant,
        train_report=train_report,
        test_report=test_report,
        params=params,
        model=model,
        cv_mape=cv_mape,
        trials=trials,
    )


def train_baseline(dataset: Dataset, feature_set: FeatureSet) -> ModelResult:
    """Fit the hedonic baseline on one partition — a shorthand for :func:`train_model`.

    Args:
        dataset: Train/test partition of a single vertical.
        feature_set: ``basic`` or ``full``.

    Returns:
        The fitted baseline together with its in-sample and held-out error.
    """
    return train_model(dataset, BASELINE_KIND, feature_set=feature_set)


def log_to_mlflow(result: ModelResult) -> None:
    """Record one result as an MLflow run.

    Imported lazily: MLflow is slow to import and is not needed by ``--no-mlflow`` runs
    or by the tests. Each model goes through its own flavor — the tree flavors serialise
    with the library's native format, which sidesteps the skops guard entirely.

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

        if isinstance(result.model, HedonicModel):
            mlflow.sklearn.log_model(
                result.model.pipeline,
                name=result.model_kind,
                skops_trusted_types=SKOPS_TRUSTED_TYPES,
            )
        elif isinstance(result.model, FittedTree):
            flavor = mlflow.lightgbm if result.model.model_kind == "lightgbm" else mlflow.catboost
            flavor.log_model(result.model.estimator, name=result.model_kind)

        # The whole search as one artifact rather than one run per trial: 40 trials across
        # four model-and-vertical combinations would leave 160 runs and an unusable UI.
        if result.trials is not None:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / f"{result.run_name}-trials.csv"
                result.trials.to_csv(path, index=False)
                mlflow.log_artifact(str(path), artifact_path="search")


def format_table(results: Sequence[ModelResult]) -> str:
    """Render the results as a fixed-width table for the terminal.

    The last column is the verdict F2 turns on: how far each model lands from the hedonic
    baseline of its own vertical, in MAPE points. Negative is better.

    Args:
        results: Fits to display.

    Returns:
        A table whose held-out columns are the ones to read.
    """
    baseline = {
        result.vehicle_type: result.test_report.mape for result in results if result.is_baseline
    }

    # ASCII only: the development console is cp1252, see RegressionReport.summary.
    header = (
        f"{'vertical':<12} {'model':<10} {'variant':<8} {'n test':>7} "
        f"{'CV MAPE':>8} {'MAPE out':>9} {'MAPE in':>8} {'sigma out':>9} "
        f"{'R2 out':>7} {'vs base':>8}"
    )
    lines = [header, "-" * len(header)]
    for result in results:
        reference = baseline.get(result.vehicle_type)
        if reference is None:
            verdict = "n/a"
        elif result.is_baseline:
            verdict = "base"
        else:
            verdict = f"{(result.test_report.mape - reference) * 100:+.1f}pt"
        cv = "-" if result.cv_mape is None else f"{result.cv_mape:.1%}"
        lines.append(
            f"{result.vehicle_type:<12} {result.model_kind:<10} {result.variant:<8} "
            f"{result.test_report.n:>7} {cv:>8} "
            f"{result.test_report.mape:>8.1%} {result.train_report.mape:>7.1%} "
            f"{result.test_report.sigma_log:>9.3f} {result.test_report.r2_log:>7.3f} "
            f"{verdict:>8}"
        )
    return "\n".join(lines)


def run(
    *,
    vehicle_types: Sequence[VehicleType] = VEHICLE_TYPES,
    model_kinds: Sequence[ModelKind] = MODEL_KINDS,
    feature_sets: Sequence[FeatureSet] = FEATURE_SETS,
    strategy: SplitStrategy = "random",
    test_size: float = DEFAULT_TEST_SIZE,
    seed: int = DEFAULT_SEED,
    n_trials: int | None = None,
    duckdb_path: Path | None = None,
    track: bool = True,
) -> list[ModelResult]:
    """Train every requested model on every requested vertical.

    Args:
        vehicle_types: Verticals to model.
        model_kinds: Models to fit.
        feature_sets: Feature sets, for the hedonic baseline only.
        strategy: Split strategy, ``random`` or ``temporal``.
        test_size: Fraction of listings held out.
        seed: Seed for the split, the search and the models.
        n_trials: Optuna budget per tree model and vertical; ``None`` uses the per-model
            defaults.
        duckdb_path: Database written by dbt. Defaults to the configured path.
        track: Whether to record each fit as an MLflow run.

    Returns:
        One result per model and vertical, with the baseline's feature sets expanded.
    """
    results: list[ModelResult] = []
    for vehicle_type in vehicle_types:
        dataset = load_split(
            vehicle_type,
            strategy=strategy,
            test_size=test_size,
            seed=seed,
            duckdb_path=duckdb_path,
        )
        for model_kind in model_kinds:
            # The feature set is a baseline-only knob; the trees always take the full
            # tree specification.
            variants: Sequence[FeatureSet] = (
                feature_sets if model_kind == BASELINE_KIND else (BASELINE_VARIANT,)
            )
            for feature_set in variants:
                result = train_model(
                    dataset,
                    model_kind,
                    feature_set=feature_set,
                    n_trials=n_trials,
                    seed=seed,
                )
                if track:
                    log_to_mlflow(result)
                results.append(result)
    return results


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the training command."""
    parser = argparse.ArgumentParser(
        prog="autovalor-train",
        description="Train the valuation models and report held-out error.",
    )
    parser.add_argument(
        "--vehicle-type",
        action="append",
        choices=VEHICLE_TYPES,
        default=None,
        help="Vertical to model; repeatable. Defaults to both.",
    )
    parser.add_argument(
        "--model",
        action="append",
        choices=MODEL_KINDS,
        default=None,
        help="Model to fit; repeatable. Defaults to all three.",
    )
    parser.add_argument(
        "--feature-set",
        action="append",
        choices=FEATURE_SETS,
        default=None,
        help=(
            "Feature set for the hedonic baseline; repeatable, defaults to both. Ignored "
            "by the tree models, which always take the full tree specification."
        ),
    )
    budgets = ", ".join(f"{model} {trials}" for model, trials in DEFAULT_TRIALS.items())
    parser.add_argument(
        "--trials",
        type=int,
        default=None,
        help=(
            f"Optuna budget per tree model and vertical, overriding the per-model "
            f"defaults ({budgets}; CatBoost is the slower fit). Zero skips the search "
            "and uses the default parameters."
        ),
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
        help=f"Seed for the split, the search and the models (default: {DEFAULT_SEED}).",
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
            model_kinds=args.model or MODEL_KINDS,
            feature_sets=args.feature_set or FEATURE_SETS,
            strategy=args.split,
            test_size=args.test_size,
            seed=args.seed,
            n_trials=args.trials,
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
