import pandas as pd
import pytest
from sklearn.model_selection import GroupKFold

from autovalor.models.dataset import group_keys
from autovalor.models.tuning import (
    DEFAULT_FOLDS,
    DEFAULT_TRIALS,
    cross_validated_mape,
    search,
    trials_for,
)

from .conftest import make_gold_frame

FAST_FOLDS = 2
"""Fewer folds than production: these tests check the protocol, not the tuning quality."""


def test_the_folds_never_split_a_vehicle_group() -> None:
    # The same reason the train/test split groups vehicles: a reposted listing landing in
    # two folds makes the cross-validated score look better than it is, and Optuna would
    # then pick the parameters that exploit it.
    frame = make_gold_frame(400, duplicate_rows=120)
    groups = group_keys(frame)

    for fit_index, score_index in GroupKFold(n_splits=DEFAULT_FOLDS).split(frame, groups=groups):
        fit_groups = set(groups.iloc[fit_index])
        score_groups = set(groups.iloc[score_index])
        assert fit_groups & score_groups == set()


def test_cross_validated_mape_returns_a_usable_rate(gold_cars: pd.DataFrame) -> None:
    score = cross_validated_mape(
        gold_cars,
        model_kind="lightgbm",
        vehicle_type="car",
        params={"n_estimators": 40, "num_leaves": 15},
        n_splits=FAST_FOLDS,
    )

    assert 0.0 < score < 1.0


def test_the_search_respects_its_budget(gold_cars: pd.DataFrame) -> None:
    result = search(
        gold_cars,
        model_kind="lightgbm",
        vehicle_type="car",
        n_trials=2,
        n_splits=FAST_FOLDS,
    )

    assert result.n_trials == 2
    assert len(result.trials) == 2
    assert result.best_params
    assert 0.0 < result.cv_mape < 1.0


def test_the_search_is_reproducible_for_a_seed(gold_cars: pd.DataFrame) -> None:
    first = search(
        gold_cars, model_kind="lightgbm", vehicle_type="car", n_trials=2, n_splits=FAST_FOLDS
    )
    second = search(
        gold_cars, model_kind="lightgbm", vehicle_type="car", n_trials=2, n_splits=FAST_FOLDS
    )

    assert first.best_params == second.best_params
    assert first.cv_mape == pytest.approx(second.cv_mape)


def test_the_search_records_the_vertical_it_ran_for(gold_cars: pd.DataFrame) -> None:
    result = search(
        gold_cars, model_kind="lightgbm", vehicle_type="car", n_trials=1, n_splits=FAST_FOLDS
    )

    assert result.vehicle_type == "car"
    assert result.model_kind == "lightgbm"


def test_the_budget_defaults_per_model_and_is_overridable() -> None:
    # CatBoost gets fewer trials because one fit costs several times a LightGBM fit; an
    # equal budget would spend most of the run on it.
    assert trials_for("lightgbm") == DEFAULT_TRIALS["lightgbm"]
    assert trials_for("catboost") < trials_for("lightgbm")
    assert trials_for("lightgbm", 7) == 7
    assert trials_for("lightgbm", 0) == 0
