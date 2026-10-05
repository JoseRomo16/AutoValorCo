from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from autovalor.models.metrics import regression_report
from autovalor.models.trees import (
    DEFAULT_PARAMS,
    FORBIDDEN_COLUMNS,
    TREE_MODELS,
    TreeModel,
    fit_tree,
    tree_spec,
)

from .conftest import make_gold_frame

FAST: dict[str, dict[str, Any]] = {
    "lightgbm": {"n_estimators": 60, "learning_rate": 0.15, "num_leaves": 15},
    "catboost": {"iterations": 60, "learning_rate": 0.15, "depth": 4},
}
"""Small fits: these tests check wiring, not accuracy, and CatBoost is slow."""


def test_the_specification_never_includes_a_forbidden_column() -> None:
    # The target, the title the features were mined from, and the identifiers. A model
    # consuming any of these would score well and mean nothing.
    for vehicle_type in ("car", "motorcycle"):
        columns = set(tree_spec(vehicle_type).columns)
        assert columns & FORBIDDEN_COLUMNS == set()


def test_only_motorcycles_carry_the_quad_flag() -> None:
    assert "is_quad" in tree_spec("motorcycle").columns
    assert "is_quad" not in tree_spec("car").columns


def test_the_specification_omits_the_hedonic_derived_columns() -> None:
    # Trees are invariant to monotone transformations, so age squared and log mileage
    # would only add correlated splits.
    columns = set(tree_spec("car").columns)
    assert "vehicle_age_squared" not in columns
    assert "log_mileage_km" not in columns


@pytest.mark.parametrize("model_kind", TREE_MODELS)
def test_a_tree_recovers_the_synthetic_price_law(
    model_kind: TreeModel, gold_cars: pd.DataFrame
) -> None:
    model = fit_tree(gold_cars, model_kind=model_kind, vehicle_type="car", params=FAST[model_kind])

    report = regression_report(gold_cars["log_price"], model.predict_log_price(gold_cars))

    assert report.mape < 0.15


@pytest.mark.parametrize("model_kind", TREE_MODELS)
def test_an_unseen_make_does_not_crash_prediction(
    model_kind: TreeModel, gold_cars: pd.DataFrame
) -> None:
    # The holdout always contains makes and models the fit never saw.
    model = fit_tree(gold_cars, model_kind=model_kind, vehicle_type="car", params=FAST[model_kind])
    unseen = gold_cars.head(5).copy()
    unseen["brand"] = "Marca Nueva"
    unseen["model"] = "modelo-nuevo"
    unseen["city"] = "Ciudad Nueva"

    predictions = model.predict_log_price(unseen)

    assert np.isfinite(predictions).all()


@pytest.mark.parametrize("model_kind", TREE_MODELS)
def test_a_missing_engine_size_is_not_dropped(
    model_kind: TreeModel, gold_cars: pd.DataFrame
) -> None:
    model = fit_tree(gold_cars, model_kind=model_kind, vehicle_type="car", params=FAST[model_kind])
    missing = gold_cars.head(5).copy()
    missing["engine_cc"] = None

    predictions = model.predict_log_price(missing)

    assert len(predictions) == 5
    assert np.isfinite(predictions).all()


def test_lightgbm_freezes_the_category_levels(gold_cars: pd.DataFrame) -> None:
    # Without frozen levels the same make could be encoded as a different integer at fit
    # and at predict time, which would silently scramble the prediction.
    model = fit_tree(gold_cars, model_kind="lightgbm", vehicle_type="car", params=FAST["lightgbm"])

    assert set(model.levels) == set(tree_spec("car").categorical)
    assert "Chevrolet" in model.levels["brand"]


def test_catboost_turns_a_missing_category_into_a_level(gold_cars: pd.DataFrame) -> None:
    # CatBoost raises on a null inside a categorical column, so the missing model token
    # has to become its own level instead of staying NaN.
    frame = gold_cars.copy()
    frame.loc[frame.index[:10], "model"] = None

    model = fit_tree(frame, model_kind="catboost", vehicle_type="car", params=FAST["catboost"])

    assert np.isfinite(model.predict_log_price(frame)).all()


def test_fitting_catboost_writes_no_log_directory(
    gold_cars: pd.DataFrame, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # CatBoost drops a catboost_info/ directory into the working directory unless told
    # not to, which would litter the repository on every fit.
    monkeypatch.chdir(tmp_path)

    fit_tree(gold_cars, model_kind="catboost", vehicle_type="car", params=FAST["catboost"])

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("model_kind", TREE_MODELS)
def test_the_design_matrix_carries_the_fitted_columns_in_order(
    model_kind: TreeModel, gold_cars: pd.DataFrame
) -> None:
    # Explaining a prediction attributes this matrix, so it has to be the same shape the
    # estimator was fitted on — same columns, same order.
    model = fit_tree(gold_cars, model_kind=model_kind, vehicle_type="car", params=FAST[model_kind])

    matrix = model.design_matrix(gold_cars.head(5))

    assert list(matrix.columns) == list(tree_spec("car").columns)
    assert len(matrix) == 5


def test_the_lightgbm_design_matrix_turns_an_unseen_level_into_missing(
    gold_cars: pd.DataFrame,
) -> None:
    # The frozen levels are what make an unseen make land on the missing branch rather
    # than on some other make's code.
    model = fit_tree(gold_cars, model_kind="lightgbm", vehicle_type="car", params=FAST["lightgbm"])
    unseen = gold_cars.head(3).copy()
    unseen["brand"] = "Marca Nueva"

    matrix = model.design_matrix(unseen)

    assert matrix["brand"].isna().all()


def test_fit_tree_rejects_an_unknown_model(gold_cars: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="unknown tree model"):
        fit_tree(gold_cars, model_kind="xgboost", vehicle_type="car")  # type: ignore[arg-type]


def test_default_params_exist_for_every_model() -> None:
    assert set(DEFAULT_PARAMS) == set(TREE_MODELS)


def test_the_motorcycle_vertical_fits_end_to_end() -> None:
    bikes = make_gold_frame(300, vehicle_type="motorcycle", seed=3)

    model = fit_tree(
        bikes, model_kind="lightgbm", vehicle_type="motorcycle", params=FAST["lightgbm"]
    )

    assert np.isfinite(model.predict_log_price(bikes)).all()
