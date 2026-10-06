"""Train the valuation models and record honest out-of-sample metrics.

Three models live behind one command: the hedonic OLS baseline and the two tree ensembles
that have to beat it. Every fit reports both sides of the split, because the gap between
them is the point — each sigma and MAPE produced during F1 was in-sample, and quoting
those as performance was the mistake this command exists to stop.

The tree models are tuned with Optuna against grouped folds of the training rows only;
the holdout is scored once, at the end. See :mod:`autovalor.models.tuning`.

The winning model also gets a P10-P90 band from three quantile models, reported in its own
table because a band is judged on coverage and width together. See
:mod:`autovalor.models.quantiles`.

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
from autovalor.models.explain import EXPLAINED_KIND, global_importance
from autovalor.models.hedonic import (
    FEATURE_SETS,
    TARGET,
    FeatureSet,
    HedonicModel,
    fit_hedonic_model,
)
from autovalor.models.metrics import (
    IntervalReport,
    RegressionReport,
    interval_report,
    regression_report,
)
from autovalor.models.quantiles import NOMINAL_COVERAGE, FittedInterval, fit_interval
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

INTERVAL_KIND: Final = "lightgbm"
"""The only model the P10-P90 band is fitted on.

LightGBM won both verticals in F2 step 3 and supports the quantile objective directly.
CatBoost can do quantile regression too; wiring it in is only worth it if CatBoost ever
becomes the served model.
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
        interval: Held-out quality of the P10-P90 band, when one was fitted.
        interval_model: The fitted quantile models behind that band.
        importance: Mean absolute SHAP contribution per feature, measured on the holdout,
            when the model is the one that gets explained.
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
    interval: IntervalReport | None = None
    interval_model: FittedInterval | None = None
    importance: pd.DataFrame | None = None

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
        if self.interval is not None:
            metrics.update(
                {f"test_interval_{key}": value for key, value in self.interval.as_dict().items()}
            )
        if self.interval_model is not None:
            metrics["interval_widening_log"] = self.interval_model.widening
            metrics["interval_crossing_rate"] = self.interval_model.crossing_rate
            metrics["interval_n_calibration"] = float(self.interval_model.n_calibration)
        if self.importance is not None:
            # One metric per feature, so the ranking is queryable in MLflow without
            # opening the artifact.
            features, values = _importance_pairs(self.importance)
            metrics.update(
                {
                    f"shap_mean_abs_{feature}": value
                    for feature, value in zip(features, values, strict=True)
                }
            )
        return metrics


def train_model(
    dataset: Dataset,
    model_kind: ModelKind,
    *,
    feature_set: FeatureSet = BASELINE_VARIANT,
    n_trials: int | None = None,
    seed: int = DEFAULT_SEED,
    intervals: bool = True,
    explain: bool = True,
    detail_features: bool = False,
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
        intervals: Whether to also fit the P10-P90 band. Only applies to
            :data:`INTERVAL_KIND`, and reuses that model's tuned parameters.
        explain: Whether to measure SHAP importance on the holdout. Only applies to
            :data:`autovalor.models.explain.EXPLAINED_KIND`.
        detail_features: Whether the tree models consume the listing-page columns. Only
            meaningful on a partition built with ``only_enriched``; see
            :func:`autovalor.models.trees.tree_spec`.

    Returns:
        The fitted model together with its in-sample and held-out error, plus the band
        when one was fitted.

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
    band: FittedInterval | None = None
    band_report: IntervalReport | None = None
    importance: pd.DataFrame | None = None

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
                detail_features=detail_features,
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
            detail_features=detail_features,
        )
        model = tree
        extra.update({f"param_{key}": value for key, value in best_params.items()})
        extra["detail_features"] = detail_features
        extra["n_model_features"] = len(tree.spec.columns)

        if intervals and tree_kind == INTERVAL_KIND:
            # The band reuses the point model's tuned parameters rather than running its
            # own search. Three more fits instead of three more searches, and whether it
            # was good enough is answered empirically by the coverage below.
            band = fit_interval(
                dataset.train,
                vehicle_type=dataset.vehicle_type,
                params=best_params,
                seed=seed,
            )
            bounds = band.predict_log_bounds(dataset.test)
            band_report = interval_report(dataset.test[TARGET], bounds[:, 0], bounds[:, 2])

        if explain and tree_kind == EXPLAINED_KIND:
            # Measured on the holdout, not on train: an importance ranking read off the
            # rows the trees already memorised would overstate whatever they overfitted.
            importance = global_importance(tree, dataset.test)

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
    if band_report is not None:
        logger.info(
            "%s / %s band — coverage %.1f%% (nominal 80%%), mean width %.0f%% of the estimate",
            dataset.vehicle_type,
            model_kind,
            band_report.coverage * 100,
            band_report.mean_relative_width * 100,
        )
    if importance is not None:
        features, values = _importance_pairs(importance.head(3))
        logger.info(
            "%s / %s drivers — %s",
            dataset.vehicle_type,
            model_kind,
            ", ".join(
                f"{feature} {value:+.3f} log"
                for feature, value in zip(features, values, strict=True)
            ),
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
        interval=band_report,
        interval_model=band,
        importance=importance,
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

        # The band's three models go in next to the point model: /predict needs all four to
        # return an estimate with its interval.
        if result.interval_model is not None:
            for quantile, quantile_model in result.interval_model.models.items():
                mlflow.lightgbm.log_model(
                    quantile_model.estimator, name=f"quantile_p{int(quantile * 100):02d}"
                )

        # The whole search as one artifact rather than one run per trial: 40 trials across
        # four model-and-vertical combinations would leave 160 runs and an unusable UI.
        if result.trials is not None:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / f"{result.run_name}-trials.csv"
                result.trials.to_csv(path, index=False)
                mlflow.log_artifact(str(path), artifact_path="search")

        # The importance ranking also goes in as one metric per feature, above, so it can
        # be compared across runs without opening this artifact.
        if result.importance is not None:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / f"{result.run_name}-shap.csv"
                result.importance.to_csv(path, index=False)
                mlflow.log_artifact(str(path), artifact_path="explain")


def format_importance_table(results: Sequence[ModelResult]) -> str:
    """Render the SHAP importance of every explained fit as one text table.

    Args:
        results: Fits to report; those without an importance table are skipped.

    Returns:
        The table, or an empty string when nothing was explained.
    """
    explained = [
        (result.vehicle_type, result.importance)
        for result in results
        if result.importance is not None
    ]
    if not explained:
        return ""

    header = f"{'vertical':<12} {'feature':<20} {'mean |phi|':>11} {'typical pull':>13}"
    lines = [header, "-" * len(header)]
    for vehicle_type, importance in explained:
        features, values = _importance_pairs(importance)
        for feature, value in zip(features, values, strict=True):
            # expm1 of the mean |phi|: the typical size of this feature's pull on the
            # price, with its direction dropped.
            pull = float(np.expm1(value)) * 100
            lines.append(f"{vehicle_type:<12} {feature:<20} {value:>11.4f} {pull:>12.1f}%")
        lines.append("")
    return "\n".join(lines).rstrip()


def _importance_pairs(importance: pd.DataFrame) -> tuple[list[str], list[float]]:
    """Split an importance table into plain Python lists, in ranked order."""
    features = [str(feature) for feature in importance["feature"].tolist()]
    values = [float(value) for value in importance["mean_abs_phi"].tolist()]
    return features, values


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


def format_interval_table(results: Sequence[ModelResult]) -> str:
    """Render the P10-P90 bands as their own table.

    Kept separate from the point-estimate table because a band is judged on two numbers at
    once: coverage has to approach the nominal 80 %, and the width has to stay narrow
    enough for the bargain / fair / expensive label to mean something. Eighty per cent
    coverage reached by quoting "between 10 and 200 million" tells a user nothing.

    Args:
        results: Fits to display; those without a band are skipped.

    Returns:
        The table, or an empty string when no result carries a band.
    """
    if all(result.interval is None for result in results):
        return ""

    header = (
        f"{'vertical':<12} {'model':<10} {'n test':>7} {'coverage':>9} {'width':>8} "
        f"{'bargain':>8} {'expensive':>10} {'widening':>9} {'crossed':>8}"
    )
    lines = [
        f"P10-P90 band, conformalized (nominal coverage {NOMINAL_COVERAGE:.0%})",
        header,
        "-" * len(header),
    ]
    for result in results:
        band = result.interval
        if band is None:
            continue
        widening = "-"
        crossed = "-"
        if result.interval_model is not None:
            widening = f"{result.interval_model.widening:+.3f}"
            crossed = f"{result.interval_model.crossing_rate:.1%}"
        lines.append(
            f"{result.vehicle_type:<12} {result.model_kind:<10} {band.n:>7} "
            f"{band.coverage:>8.1%} {band.mean_relative_width:>7.0%} "
            f"{band.below_rate:>7.1%} {band.above_rate:>9.1%} {widening:>9} {crossed:>8}"
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
    intervals: bool = True,
    explain: bool = True,
    detail_features: bool = False,
    only_enriched: bool = False,
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
        intervals: Whether to fit the P10-P90 band on :data:`INTERVAL_KIND`.
        explain: Whether to measure SHAP importance on the holdout for
            :data:`autovalor.models.explain.EXPLAINED_KIND`.
        detail_features: Whether the tree models consume the listing-page columns.
        only_enriched: Keep only listings that have a detail row. Pairing this with
            ``detail_features`` on and off is how the enrichment is measured: both runs
            then see exactly the same rows.
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
            only_enriched=only_enriched,
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
                    intervals=intervals,
                    explain=explain,
                    detail_features=detail_features,
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
        "--no-intervals",
        action="store_true",
        help=(
            f"Skip the P10-P90 band, which is otherwise fitted on {INTERVAL_KIND} as three "
            "extra quantile models reusing its tuned parameters."
        ),
    )
    parser.add_argument(
        "--no-explain",
        action="store_true",
        help=(
            f"Skip the SHAP importance, which is otherwise measured on the holdout for "
            f"{EXPLAINED_KIND}."
        ),
    )
    parser.add_argument(
        "--detail-features",
        action="store_true",
        help=(
            "Let the tree models consume the listing-page columns (body type, "
            "transmission, brakes, colour, gear count, single owner). Only meaningful "
            "with --only-enriched: without it the columns are null for most rows."
        ),
    )
    parser.add_argument(
        "--only-enriched",
        action="store_true",
        help=(
            "Keep only listings that have a detail row. Running this twice, with and "
            "without --detail-features, measures the enrichment on identical rows."
        ),
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
            intervals=not args.no_intervals,
            explain=not args.no_explain,
            detail_features=args.detail_features,
            only_enriched=args.only_enriched,
            duckdb_path=args.duckdb_path,
            track=not args.no_mlflow,
        )
    except (SplitNotPossibleError, FileNotFoundError) as error:
        logger.error("%s", error)
        return 1

    sys.stdout.write(format_table(results) + "\n")
    bands = format_interval_table(results)
    if bands:
        sys.stdout.write("\n" + bands + "\n")
    drivers = format_importance_table(results)
    if drivers:
        sys.stdout.write("\n" + drivers + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
