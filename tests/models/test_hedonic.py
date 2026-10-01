import numpy as np
import pandas as pd
import pytest

from autovalor.models.hedonic import (
    AGE_SQUARED,
    LOG_MILEAGE,
    add_derived,
    feature_spec,
    fit_hedonic,
    predict_log_price,
    prepare,
)
from autovalor.models.metrics import regression_report

from .conftest import make_gold_frame


def test_add_derived_leaves_the_input_untouched(gold_cars: pd.DataFrame) -> None:
    enriched = add_derived(gold_cars)

    assert AGE_SQUARED not in gold_cars.columns
    assert AGE_SQUARED in enriched.columns


def test_derived_columns_follow_their_definitions(gold_cars: pd.DataFrame) -> None:
    enriched = add_derived(gold_cars)

    expected_age = gold_cars["vehicle_age_years"].astype("float64") ** 2
    assert np.allclose(enriched[AGE_SQUARED], expected_age)
    assert np.allclose(enriched[LOG_MILEAGE], np.log1p(gold_cars["mileage_km"]))


def test_log_mileage_keeps_a_brand_new_vehicle_at_zero() -> None:
    frame = make_gold_frame(200)
    frame.loc[:, "mileage_km"] = 0

    assert add_derived(frame)[LOG_MILEAGE].eq(0.0).all()


def test_the_basic_set_excludes_the_title_features() -> None:
    spec = feature_spec("basic", "car")

    assert "brand" not in spec.columns
    assert "model" not in spec.columns
    assert "engine_cc" not in spec.columns


def test_the_full_set_adds_the_title_features() -> None:
    spec = feature_spec("full", "car")

    assert {"brand", "model", "engine_cc"} <= set(spec.columns)


def test_only_motorcycles_carry_the_quad_flag() -> None:
    # Quads, buggies and side-by-sides live in the motorcycle vertical but not on its
    # price curve, so the flag has to reach the model there and nowhere else.
    assert "is_quad" in feature_spec("full", "motorcycle").columns
    assert "is_quad" not in feature_spec("full", "car").columns


def test_feature_spec_rejects_an_unknown_set() -> None:
    with pytest.raises(ValueError, match="unknown feature set"):
        feature_spec("kitchen_sink", "car")  # type: ignore[arg-type]


def test_prepare_keeps_a_missing_model_as_its_own_level() -> None:
    frame = add_derived(make_gold_frame(200))
    frame.loc[0, "model"] = None
    spec = feature_spec("full", "car")

    prepared = prepare(frame, spec)

    assert prepared.loc[0, "model"] == "Desconocido"
    assert list(prepared.columns) == list(spec.columns)


def test_the_full_set_recovers_the_synthetic_price_law(gold_cars: pd.DataFrame) -> None:
    # The fixture's prices are a linear function of age, log mileage and brand plus a
    # small noise term, so a correctly wired OLS has to fit it almost exactly.
    pipeline, spec = fit_hedonic(gold_cars, feature_set="full", vehicle_type="car")

    report = regression_report(gold_cars["log_price"], predict_log_price(pipeline, gold_cars, spec))

    assert report.mape < 0.06
    assert report.r2_log > 0.98


def test_an_unseen_make_degrades_the_prediction_instead_of_crashing(
    gold_cars: pd.DataFrame,
) -> None:
    pipeline, spec = fit_hedonic(gold_cars, feature_set="full", vehicle_type="car")
    unseen = gold_cars.head(5).copy()
    unseen["brand"] = "Marca Nueva"
    unseen["model"] = "modelo-nuevo"

    predictions = predict_log_price(pipeline, unseen, spec)

    assert np.isfinite(predictions).all()


def test_a_missing_engine_size_is_imputed_rather_than_dropped(gold_cars: pd.DataFrame) -> None:
    pipeline, spec = fit_hedonic(gold_cars, feature_set="full", vehicle_type="car")
    missing = gold_cars.head(5).copy()
    missing["engine_cc"] = None

    predictions = predict_log_price(pipeline, missing, spec)

    assert len(predictions) == 5
    assert np.isfinite(predictions).all()


def test_the_motorcycle_vertical_fits_end_to_end() -> None:
    bikes = make_gold_frame(400, vehicle_type="motorcycle", seed=3)

    pipeline, spec = fit_hedonic(bikes, feature_set="full", vehicle_type="motorcycle")

    assert np.isfinite(predict_log_price(pipeline, bikes, spec)).all()
