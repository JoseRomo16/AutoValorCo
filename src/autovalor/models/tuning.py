"""Hyperparameter search for the tree models.

Two properties matter more than the search itself.

**The holdout is never touched.** Optuna only ever sees folds carved out of
``Dataset.train``; the test rows are scored once, at the end, in
:mod:`autovalor.models.train`. Tuning against the holdout would turn it into a second
training set and the reported MAPE back into an in-sample figure.

**The folds group reposted vehicles.** The same reason the split groups them: a vehicle
reposted under a new ``listing_id`` appearing in two folds makes the cross-validated score
look better than it is, and Optuna would then pick the parameters that exploit it. The
grouping comes from :func:`autovalor.models.dataset.group_keys`, the same function the
split uses.

The objective is the MAPE in pesos, which is the F2 acceptance metric — not a proxy on the
log scale.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pandas as pd
from sklearn.model_selection import GroupKFold

from autovalor.models.dataset import DEFAULT_SEED, VehicleType, group_keys
from autovalor.models.metrics import regression_report
from autovalor.models.trees import TreeModel, fit_tree

if TYPE_CHECKING:
    import optuna

logger = logging.getLogger("autovalor.models")

DEFAULT_TRIALS: dict[TreeModel, int] = {"lightgbm": 40, "catboost": 20}
"""Search budget per model and vertical, set from measured cost rather than symmetry.

On the development machine one fit takes ~6 s for LightGBM and ~18-55 s for CatBoost on
the 5.766 training rows of the car vertical, so an equal budget would spend 80 % of the
run on CatBoost. These numbers put the full sweep of two models by two verticals at
roughly an hour.
"""

DEFAULT_FOLDS = 3
"""Folds in the inner cross-validation.

Three rather than five, because the cost is multiplicative with the trial budget and the
folds are only used to rank hyperparameters, not to report performance. Three leaves
~1.900 rows per fold for cars, which is enough to separate a good draw from a bad one.
"""


def trials_for(model_kind: TreeModel, override: int | None = None) -> int:
    """Return the trial budget for a model.

    Args:
        model_kind: Model to be tuned.
        override: Explicit budget from the command line, if any. ``0`` is a valid
            override and means "skip the search".

    Returns:
        ``override`` when given, otherwise the model's entry in :data:`DEFAULT_TRIALS`.
    """
    return DEFAULT_TRIALS[model_kind] if override is None else override


@dataclass(frozen=True)
class SearchResult:
    """Outcome of one hyperparameter search.

    Attributes:
        model_kind: Model that was tuned.
        vehicle_type: Vertical it was tuned for.
        best_params: Parameters with the lowest cross-validated MAPE.
        cv_mape: That MAPE, averaged over the folds. Compare it against the held-out
            MAPE later: a large gap means the search overfitted the folds.
        n_trials: Trials actually run.
        trials: One row per trial, for the experiment log.
    """

    model_kind: TreeModel
    vehicle_type: VehicleType
    best_params: dict[str, Any]
    cv_mape: float
    n_trials: int
    trials: pd.DataFrame


def _lightgbm_space(trial: "optuna.Trial") -> dict[str, Any]:
    """Return a LightGBM parameter draw.

    ``min_data_per_group`` and ``cat_smooth`` are in here because of the categorical
    columns: ``model`` has hundreds of levels, and without smoothing the splits chase
    levels that carry a handful of listings.
    """
    return {
        "n_estimators": trial.suggest_int("n_estimators", 200, 1500, step=100),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
        "num_leaves": trial.suggest_int("num_leaves", 15, 255, log=True),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "subsample_freq": trial.suggest_int("subsample_freq", 0, 5),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        "min_data_per_group": trial.suggest_int("min_data_per_group", 5, 100),
        "cat_smooth": trial.suggest_float("cat_smooth", 1.0, 50.0, log=True),
    }


def _catboost_space(trial: "optuna.Trial") -> dict[str, Any]:
    """Return a CatBoost parameter draw."""
    return {
        "iterations": trial.suggest_int("iterations", 200, 1500, step=100),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
        "depth": trial.suggest_int("depth", 4, 10),
        "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 30.0, log=True),
        "random_strength": trial.suggest_float("random_strength", 1e-3, 10.0, log=True),
        "bagging_temperature": trial.suggest_float("bagging_temperature", 0.0, 2.0),
        "one_hot_max_size": trial.suggest_int("one_hot_max_size", 2, 32),
    }


SPACES = {"lightgbm": _lightgbm_space, "catboost": _catboost_space}


def cross_validated_mape(
    train: pd.DataFrame,
    *,
    model_kind: TreeModel,
    vehicle_type: VehicleType,
    params: dict[str, Any] | None = None,
    n_splits: int = DEFAULT_FOLDS,
    seed: int = DEFAULT_SEED,
    detail_features: bool = False,
) -> float:
    """Return the MAPE of one parameter set, averaged over grouped folds.

    Args:
        train: Training rows; the holdout must not be in here.
        model_kind: Model to fit.
        vehicle_type: Vertical being modeled.
        params: Hyperparameters to score.
        n_splits: Number of folds.
        seed: Seed passed to the model.
        detail_features: Whether the folds see the listing-page columns. Has to match
            what the final fit will use, or the search tunes a different model.

    Returns:
        Mean of the per-fold MAPE, in peso terms.
    """
    folds = GroupKFold(n_splits=n_splits)
    groups = group_keys(train)
    scores: list[float] = []

    for fit_index, score_index in folds.split(train, groups=groups):
        fold_train = train.iloc[fit_index]
        fold_score = train.iloc[score_index]
        model = fit_tree(
            fold_train,
            model_kind=model_kind,
            vehicle_type=vehicle_type,
            params=params,
            seed=seed,
            detail_features=detail_features,
        )
        report = regression_report(fold_score["log_price"], model.predict_log_price(fold_score))
        scores.append(report.mape)

    return float(sum(scores) / len(scores))


def search(
    train: pd.DataFrame,
    *,
    model_kind: TreeModel,
    vehicle_type: VehicleType,
    n_trials: int | None = None,
    n_splits: int = DEFAULT_FOLDS,
    seed: int = DEFAULT_SEED,
    detail_features: bool = False,
) -> SearchResult:
    """Search for the hyperparameters with the lowest cross-validated MAPE.

    Args:
        train: Training rows; the holdout must not be in here.
        model_kind: Model to tune.
        vehicle_type: Vertical being modeled.
        n_trials: Search budget; defaults to the model's entry in
            :data:`DEFAULT_TRIALS`.
        n_splits: Folds in the inner cross-validation.
        seed: Seed for both the sampler and the models, so a rerun compares models
            rather than random draws.
        detail_features: Whether the folds see the listing-page columns; must match the
            final fit.

    Returns:
        The best parameters, their cross-validated MAPE and the trial log.
    """
    import optuna

    # 40 trials across four model-and-vertical combinations would bury the result table
    # under Optuna's per-trial chatter.
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    space = SPACES[model_kind]

    def objective(trial: "optuna.Trial") -> float:
        return cross_validated_mape(
            train,
            model_kind=model_kind,
            vehicle_type=vehicle_type,
            params=space(trial),
            n_splits=n_splits,
            seed=seed,
            detail_features=detail_features,
        )

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=seed),
        study_name=f"{model_kind}-{vehicle_type}",
    )
    study.optimize(objective, n_trials=trials_for(model_kind, n_trials))

    logger.info(
        "%s / %s — best CV MAPE %.1f%% over %d trials",
        vehicle_type,
        model_kind,
        study.best_value * 100,
        len(study.trials),
    )
    return SearchResult(
        model_kind=model_kind,
        vehicle_type=vehicle_type,
        best_params=dict(study.best_params),
        cv_mape=float(study.best_value),
        n_trials=len(study.trials),
        trials=study.trials_dataframe(),
    )
