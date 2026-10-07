from typing import Any

import numpy as np
import pandas as pd
import pytest

from autovalor.models.explain import (
    CANCELLATION_TOLERANCE,
    explain_predictions,
    global_importance,
    shap_contributions,
    top_drivers,
)
from autovalor.models.trees import UNKNOWN_CATEGORY, FittedTree, fit_tree, tree_spec

from .conftest import make_gold_frame

FAST: dict[str, Any] = {"n_estimators": 80, "learning_rate": 0.15, "num_leaves": 15}
"""A small fit: these tests check the attribution, not the accuracy."""


@pytest.fixture
def fitted_cars(gold_cars: pd.DataFrame) -> FittedTree:
    return fit_tree(gold_cars, model_kind="lightgbm", vehicle_type="car", params=FAST)


def test_the_contributions_add_up_to_the_prediction(
    fitted_cars: FittedTree, gold_cars: pd.DataFrame
) -> None:
    # The invariant that matters. SHAP is exactly additive in log space, so if this holds
    # on every row then the explainer is wired to the same model and the same prepared
    # matrix as the prediction. If someone changes the preprocessing without touching
    # explain.py, this is what fails.
    explanation = explain_predictions(fitted_cars, gold_cars)

    summed = explanation.contributions.groupby("row")["phi"].sum() + explanation.base_log_price
    predicted = pd.Series(explanation.predicted_log_price, index=gold_cars.index)

    assert np.allclose(summed.to_numpy(), predicted.loc[summed.index].to_numpy(), atol=1e-9)


def test_the_factors_multiply_up_to_the_predicted_price(
    fitted_cars: FittedTree, gold_cars: pd.DataFrame
) -> None:
    # The multiplicative reading is the primary output, so it has to be exact too:
    # price == base price * product of the factors.
    explanation = explain_predictions(fitted_cars, gold_cars.head(20))

    product = explanation.contributions.groupby("row")["factor"].prod()
    predicted_cop = np.exp(explanation.predicted_log_price[: len(product)])

    assert np.allclose(explanation.base_price_cop * product.to_numpy(), predicted_cop, rtol=1e-9)


def test_an_unseen_category_is_explained_as_unknown(
    fitted_cars: FittedTree, gold_cars: pd.DataFrame
) -> None:
    # A make the fit never saw goes down the missing branch, so the explanation has to say
    # unknown rather than name some other make.
    unseen = gold_cars.head(3).copy()
    unseen["brand"] = "Marca Nueva"

    contributions = explain_predictions(fitted_cars, unseen).contributions
    brand = contributions[contributions["feature"] == "brand"]

    assert (brand["value"] == UNKNOWN_CATEGORY).all()
    assert np.isfinite(brand["phi"]).all()


def test_a_missing_engine_size_is_explained_as_unknown(
    fitted_cars: FittedTree, gold_cars: pd.DataFrame
) -> None:
    missing = gold_cars.head(3).copy()
    missing["engine_cc"] = None

    contributions = explain_predictions(fitted_cars, missing).contributions
    engine = contributions[contributions["feature"] == "engine_cc"]

    assert (engine["value"] == UNKNOWN_CATEGORY).all()


def test_every_feature_is_explained_once_per_row(
    fitted_cars: FittedTree, gold_cars: pd.DataFrame
) -> None:
    rows = gold_cars.head(4)

    contributions = explain_predictions(fitted_cars, rows).contributions

    assert len(contributions) == len(rows) * len(tree_spec("car").columns)
    per_row = contributions.groupby("row")["feature"].nunique()
    assert (per_row == len(tree_spec("car").columns)).all()


def test_the_contributions_are_ordered_by_magnitude_within_each_row(
    fitted_cars: FittedTree, gold_cars: pd.DataFrame
) -> None:
    contributions = explain_predictions(fitted_cars, gold_cars.head(5)).contributions

    for _, group in contributions.groupby("row"):
        magnitudes = group["phi"].abs().to_numpy()
        assert np.all(np.diff(magnitudes) <= 1e-12)


def test_the_listing_id_travels_with_the_explanation(
    fitted_cars: FittedTree, gold_cars: pd.DataFrame
) -> None:
    rows = gold_cars.head(2)

    contributions = explain_predictions(fitted_cars, rows).contributions

    assert set(contributions["listing_id"]) == set(rows["listing_id"])


def test_the_peso_approximation_sums_to_the_price_delta(
    fitted_cars: FittedTree, gold_cars: pd.DataFrame
) -> None:
    # The per-term figure is approximate, but the total is not: a waterfall built from
    # these shares has to land on the predicted price.
    explanation = explain_predictions(fitted_cars, gold_cars.head(20))

    allocated = explanation.contributions.groupby("row")["approx_cop"].sum()
    predicted_cop = np.exp(explanation.predicted_log_price[: len(allocated)])

    assert np.allclose(allocated.to_numpy(), predicted_cop - explanation.base_price_cop, rtol=1e-6)


def test_the_peso_approximation_refuses_to_answer_when_contributions_cancel(
    fitted_cars: FittedTree, gold_cars: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Total log movement near zero with non-zero terms would make the shares arbitrarily
    # large and signed almost at random, so the column says NaN instead of a confident
    # wrong number. Real fits rarely cancel exactly, so the case is constructed.
    rows = gold_cars.head(4)
    phi, base = shap_contributions(fitted_cars, rows)
    cancelling, ordinary = phi.index[0], phi.index[1]
    forced = phi.copy()
    forced.loc[cancelling, :] = 0.0
    forced.loc[cancelling, forced.columns[0]] = 0.5
    forced.loc[cancelling, forced.columns[1]] = -0.5
    assert abs(float(forced.loc[cancelling].sum())) < CANCELLATION_TOLERANCE

    monkeypatch.setattr(
        "autovalor.models.explain.shap_contributions", lambda *_, **__: (forced, base)
    )
    contributions = explain_predictions(fitted_cars, rows).contributions

    cancelled = contributions[contributions["row"] == cancelling]
    assert cancelled["approx_cop"].isna().all()
    # The exact factors are still reported for that row, and other rows are unaffected.
    assert cancelled["factor"].notna().all()
    assert contributions[contributions["row"] == ordinary]["approx_cop"].notna().all()


def test_global_importance_ranks_the_known_price_driver_first(
    fitted_cars: FittedTree, gold_cars: pd.DataFrame
) -> None:
    # The synthetic law makes age the dominant term, so the ranking has to find it.
    importance = global_importance(fitted_cars, gold_cars)

    assert list(importance.columns) == ["feature", "mean_abs_phi", "mean_abs_pct"]
    assert importance.iloc[0]["feature"] == "vehicle_age_years"
    assert (importance["mean_abs_phi"] >= 0).all()
    assert importance["mean_abs_phi"].is_monotonic_decreasing


def test_top_drivers_keeps_k_contributions_per_row(
    fitted_cars: FittedTree, gold_cars: pd.DataFrame
) -> None:
    rows = gold_cars.head(5)

    drivers = top_drivers(fitted_cars, rows, k=3)

    assert len(drivers) == len(rows) * 3
    assert (drivers.groupby("row")["feature"].nunique() == 3).all()


def test_top_drivers_rejects_a_budget_below_one(
    fitted_cars: FittedTree, gold_cars: pd.DataFrame
) -> None:
    with pytest.raises(ValueError, match="k must be 1 or greater"):
        top_drivers(fitted_cars, gold_cars.head(2), k=0)


def test_catboost_is_not_explained(gold_cars: pd.DataFrame) -> None:
    # CatBoost needs its own path and is not the served model; refusing is better than
    # silently attributing the wrong matrix.
    catboost = fit_tree(
        gold_cars, model_kind="catboost", vehicle_type="car", params={"iterations": 30}
    )

    with pytest.raises(ValueError, match="only lightgbm predictions are explained"):
        explain_predictions(catboost, gold_cars.head(2))


def test_motorcycles_are_explained_with_their_own_feature_set() -> None:
    # The quad flag reaches the motorcycle model and nowhere else, so it has to appear in
    # a motorcycle explanation.
    bikes = make_gold_frame(300, vehicle_type="motorcycle", seed=11)
    fitted = fit_tree(bikes, model_kind="lightgbm", vehicle_type="motorcycle", params=FAST)

    contributions = explain_predictions(fitted, bikes.head(2)).contributions

    assert "is_quad" in set(contributions["feature"])


def test_the_native_contributions_match_the_shap_package(gold_cars: pd.DataFrame) -> None:
    # shap_contributions uses LightGBM's own pred_contrib rather than the shap package, so
    # that the API image does not have to carry shap, numba and llvmlite. Both are exact
    # TreeSHAP; this pins that claim numerically, so the swap stays a packaging decision.
    import shap

    fitted = fit_tree(gold_cars, model_kind="lightgbm", vehicle_type="car", params=FAST)
    rows = gold_cars.head(40)

    ours, base = shap_contributions(fitted, rows)

    explainer = shap.TreeExplainer(fitted.estimator)
    theirs = np.asarray(explainer.shap_values(fitted.design_matrix(rows)), dtype=np.float64)

    np.testing.assert_allclose(ours.to_numpy(), theirs, rtol=1e-9, atol=1e-9)
    assert base == pytest.approx(float(np.ravel(explainer.expected_value)[0]))
