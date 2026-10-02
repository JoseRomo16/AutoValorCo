import numpy as np
import pandas as pd
import pytest

from autovalor.models.dataset import group_keys, split_listings
from autovalor.models.metrics import interval_report
from autovalor.models.quantiles import (
    BARGAIN,
    EXPENSIVE,
    FAIR,
    NOMINAL_COVERAGE,
    QUANTILES,
    classify,
    conformal_widening,
    fit_interval,
)

from .conftest import make_gold_frame

FAST = {"n_estimators": 60, "learning_rate": 0.15, "num_leaves": 15}
"""Small fits: these tests check calibration and wiring, not accuracy."""


def test_the_levels_are_the_product_requirement() -> None:
    assert QUANTILES == (0.10, 0.50, 0.90)
    # Rounded because 0.90 - 0.10 is 0.8000000000000001 in binary floating point.
    assert round(NOMINAL_COVERAGE, 10) == 0.80


def test_a_band_that_is_too_narrow_gets_widened() -> None:
    # Every price lands outside a band of zero width, so the correction has to be positive
    # and large enough to swallow the distance.
    price = np.log([10_000_000.0, 20_000_000.0, 30_000_000.0, 40_000_000.0] * 10)

    widening = conformal_widening(price, price - 0.0, price + 0.0)

    assert widening == pytest.approx(0.0, abs=1e-9)


def test_the_widening_grows_with_how_far_prices_fall_outside() -> None:
    price = np.log(np.linspace(10_000_000, 40_000_000, 80))
    tight = conformal_widening(price, price + 0.30, price - 0.30)
    loose = conformal_widening(price, price + 0.05, price - 0.05)

    assert tight > loose > 0


def test_a_band_that_is_too_wide_gets_tightened() -> None:
    # The conformal step is two-sided: a band wider than it needs to be is shrunk, which is
    # what keeps the interval from being uselessly conservative.
    price = np.log(np.linspace(10_000_000, 40_000_000, 80))

    widening = conformal_widening(price, price - 1.0, price + 1.0)

    assert widening < 0


def test_the_widening_rejects_mismatched_shapes() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        conformal_widening([17.0, 17.5], [16.0], [18.0])


def test_the_widening_rejects_an_empty_calibration_set() -> None:
    with pytest.raises(ValueError, match="zero rows"):
        conformal_widening([], [], [])


def test_the_band_covers_about_the_nominal_share(gold_cars: pd.DataFrame) -> None:
    # The whole point of the conformal step. Uncalibrated quantile trees came in at 67 % on
    # the real car holdout against a nominal 80 %.
    split = split_listings(gold_cars)
    band = fit_interval(split.train, vehicle_type="car", params=FAST)

    bounds = band.predict_log_bounds(split.test)
    report = interval_report(split.test["log_price"], bounds[:, 0], bounds[:, 2])

    assert report.coverage == pytest.approx(NOMINAL_COVERAGE, abs=0.10)


def test_the_bounds_are_never_crossed(gold_cars: pd.DataFrame) -> None:
    band = fit_interval(gold_cars, vehicle_type="car", params=FAST)

    bounds = band.predict_log_bounds(gold_cars)

    assert np.all(np.diff(bounds, axis=1) >= 0)


def test_the_point_prediction_is_the_middle_bound(gold_cars: pd.DataFrame) -> None:
    band = fit_interval(gold_cars, vehicle_type="car", params=FAST)

    bounds = band.predict_log_bounds(gold_cars)

    assert np.allclose(band.predict_log_price(gold_cars), bounds[:, 1])


def test_calibration_rows_are_held_back_from_the_fit(gold_cars: pd.DataFrame) -> None:
    band = fit_interval(gold_cars, vehicle_type="car", params=FAST)

    # A quarter of the training rows by default, so the quantile models see fewer rows than
    # the point model does.
    assert band.n_calibration == pytest.approx(len(gold_cars) * 0.25, abs=10)


def test_the_calibration_split_keeps_a_reposted_vehicle_on_one_side() -> None:
    # fit_interval reuses the grouped splitter for its inner split; a twin in both halves
    # would flatter the widening downwards and under-cover in production.
    frame = make_gold_frame(600, duplicate_rows=150)
    inner = split_listings(frame, test_size=0.25)

    assert set(group_keys(inner.train)) & set(group_keys(inner.test)) == set()


def test_an_unseen_make_does_not_crash_the_band(gold_cars: pd.DataFrame) -> None:
    band = fit_interval(gold_cars, vehicle_type="car", params=FAST)
    unseen = gold_cars.head(5).copy()
    unseen["brand"] = "Marca Nueva"
    unseen["model"] = "modelo-nuevo"

    assert np.isfinite(band.predict_log_bounds(unseen)).all()


def test_a_caller_cannot_override_the_quantile_objective(gold_cars: pd.DataFrame) -> None:
    # A tuned parameter set could carry an objective; it must not silently replace the
    # level being fitted.
    band = fit_interval(
        gold_cars, vehicle_type="car", params={**FAST, "objective": "regression", "alpha": 0.5}
    )

    for quantile, model in band.models.items():
        assert model.estimator.get_params()["objective"] == "quantile"  # type: ignore[attr-defined]
        assert model.estimator.get_params()["alpha"] == quantile  # type: ignore[attr-defined]


def test_the_motorcycle_vertical_fits_end_to_end() -> None:
    bikes = make_gold_frame(600, vehicle_type="motorcycle", seed=3)

    band = fit_interval(bikes, vehicle_type="motorcycle", params=FAST)

    assert np.isfinite(band.predict_log_bounds(bikes)).all()


def test_classify_labels_each_side_of_the_band() -> None:
    lower = np.log([10_000_000.0] * 3)
    upper = np.log([20_000_000.0] * 3)
    asking = np.log([9_000_000.0, 15_000_000.0, 25_000_000.0])

    assert classify(asking, lower, upper) == [BARGAIN, FAIR, EXPENSIVE]


def test_a_price_exactly_on_a_bound_is_fair() -> None:
    # The band is inclusive: calling a listing a bargain for matching the P10 to the peso
    # would be a coin flip presented as a judgement.
    bound = np.log([10_000_000.0, 20_000_000.0])

    assert classify(bound, bound, np.log([20_000_000.0, 30_000_000.0])) == [FAIR, FAIR]


def test_classify_rejects_a_crossed_band() -> None:
    with pytest.raises(ValueError, match="lower > upper"):
        classify([17.0], [18.0], [16.0])


def test_classify_rejects_mismatched_shapes() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        classify([17.0, 17.5], [16.0], [18.0])
