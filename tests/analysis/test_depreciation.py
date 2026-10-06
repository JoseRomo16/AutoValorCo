import numpy as np
import pandas as pd
import pytest

from autovalor.analysis.depreciation import (
    MIN_BRAND_LISTINGS,
    UNKNOWN_BRANDS,
    _half_life,
    depreciation_at_ages,
    depreciation_curves,
    eligible_brands,
)

from .conftest import AGE_EFFECT


def test_a_thin_brand_does_not_get_its_own_slope(cars: pd.DataFrame) -> None:
    thinned = cars.copy()
    thinned.loc[thinned.index[:5], "brand"] = "Koenigsegg"

    assert "Koenigsegg" not in eligible_brands(thinned)


def test_a_brand_with_one_model_year_does_not_get_a_slope(cars: pd.DataFrame) -> None:
    # Well represented but all from the same year: there is nothing in those rows about
    # what a fifth year costs, and an extrapolated slope would look like a measurement.
    single_year = cars.copy()
    affected = single_year["brand"] == "Toyota"
    single_year.loc[affected, "model_year"] = 2024
    single_year.loc[affected, "vehicle_age_years"] = 2

    assert affected.sum() >= MIN_BRAND_LISTINGS
    assert "Toyota" not in eligible_brands(single_year)


def test_the_unknown_brand_bucket_is_never_a_brand(cars: pd.DataFrame) -> None:
    # For motorcycles this bucket is the largest "brand" in the vertical, so without the
    # exclusion it would become the reference every real brand is compared against.
    unknown = cars.copy()
    unknown.loc[unknown.index[: len(unknown) // 2], "brand"] = UNKNOWN_BRANDS[0]

    assert UNKNOWN_BRANDS[0] not in eligible_brands(unknown)


def test_the_curves_recover_the_fixture_depreciation(cars: pd.DataFrame) -> None:
    curves = depreciation_curves(cars, vehicle_type="car")

    # The fixture loses AGE_EFFECT per year in log space with mileage held fixed, so the
    # age-only rate is 1 - exp(AGE_EFFECT) for every brand.
    expected = -(np.expm1(AGE_EFFECT)) * 100.0
    assert curves["age_only_pct"].to_numpy() == pytest.approx(expected, abs=1.0)


def test_the_total_rate_is_at_least_the_age_only_rate(cars: pd.DataFrame) -> None:
    # A year adds kilometres and kilometres cost money, so the headline rate cannot be
    # smaller than the rate that holds mileage fixed.
    curves = depreciation_curves(cars, vehicle_type="car")

    assert (curves["annual_depreciation_pct"] >= curves["age_only_pct"] - 1e-9).all()


def test_exactly_one_brand_is_the_reference(cars: pd.DataFrame) -> None:
    curves = depreciation_curves(cars, vehicle_type="car")

    assert curves["is_reference"].sum() == 1


def test_the_interval_brackets_the_estimate(cars: pd.DataFrame) -> None:
    curves = depreciation_curves(cars, vehicle_type="car")

    assert (curves["ci_low_pct"] <= curves["annual_depreciation_pct"]).all()
    assert (curves["annual_depreciation_pct"] <= curves["ci_high_pct"]).all()


def test_a_vertical_with_no_eligible_brand_fails_loudly(cars: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="no car brand reaches"):
        depreciation_curves(cars.head(30), vehicle_type="car")


def test_a_brand_that_holds_its_value_has_no_half_life() -> None:
    # Reporting 10.000 years would imply a measurement; NaN says there is none.
    assert np.isnan(_half_life(0.0))
    assert np.isnan(_half_life(0.01))
    assert _half_life(np.log(0.5)) == pytest.approx(1.0)


def test_retained_value_falls_with_age(cars: pd.DataFrame) -> None:
    curves = depreciation_curves(cars, vehicle_type="car")

    retained = depreciation_at_ages(curves, ages=(1, 5, 10))

    for _, brand in retained.groupby("brand"):
        ordered = brand.sort_values("age_years")["retained_value_pct"].to_numpy()
        assert (np.diff(ordered) < 0).all()
        assert (ordered < 100.0).all()
