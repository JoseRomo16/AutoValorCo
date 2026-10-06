import numpy as np
import pandas as pd
import pytest

from autovalor.analysis.inference import (
    AGE_SQUARED,
    ENGINE_CC_MISSING,
    LOG_MILEAGE,
    POOLED_LEVEL,
    Effect,
    combined_effect,
    effect_of,
    effects_frame,
    fit_ols,
    pool_rare,
    prepare,
)

from .conftest import AGE_EFFECT, MILEAGE_EFFECT


def test_prepare_adds_the_derived_columns(cars: pd.DataFrame) -> None:
    prepared = prepare(cars)

    assert prepared[AGE_SQUARED].equals(cars["vehicle_age_years"].astype("float64") ** 2)
    assert np.allclose(prepared[LOG_MILEAGE], np.log1p(cars["mileage_km"]))


def test_a_missing_engine_size_becomes_a_level_instead_of_a_dropped_row(
    cars: pd.DataFrame,
) -> None:
    # The fixture leaves engine_cc null for a quarter of the rows. statsmodels would drop
    # them silently, which would change the population every analysis is measured on.
    assert cars["engine_cc"].isna().any()

    prepared = prepare(cars)

    assert len(prepared) == len(cars)
    assert not prepared["engine_cc"].isna().any()
    assert prepared[ENGINE_CC_MISSING].sum() == cars["engine_cc"].isna().sum()


def test_pool_rare_collapses_only_the_thin_levels() -> None:
    values = pd.Series(["common"] * 50 + ["rare"] * 3 + ["also_rare"] * 1, name="brand")

    pooled = pool_rare(values, min_count=10)

    assert set(pooled.unique()) == {"common", POOLED_LEVEL}
    assert (pooled == POOLED_LEVEL).sum() == 4


def test_pool_rare_leaves_a_healthy_column_untouched() -> None:
    values = pd.Series(["a"] * 20 + ["b"] * 20, name="brand")

    assert pool_rare(values, min_count=10).equals(values.astype(str))


def test_the_regression_recovers_the_fixture_price_law(cars: pd.DataFrame) -> None:
    # The whole point of a synthetic lake: the coefficients are known, so this asserts the
    # estimator finds them rather than asserting a number a previous run happened to print.
    results = fit_ols(prepare(cars), f"vehicle_age_years + {LOG_MILEAGE} + C(brand)")

    assert effect_of(results, "vehicle_age_years").log_estimate == pytest.approx(
        AGE_EFFECT, abs=0.01
    )
    assert effect_of(results, LOG_MILEAGE).log_estimate == pytest.approx(MILEAGE_EFFECT, abs=0.01)


def test_the_errors_are_robust(cars: pd.DataFrame) -> None:
    results = fit_ols(prepare(cars), "vehicle_age_years")

    assert results.cov_type == "HC3"


def test_fit_refuses_an_empty_frame(cars: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="zero rows"):
        fit_ols(cars.head(0), "vehicle_age_years")


def test_effect_of_rejects_a_term_the_model_does_not_have(cars: pd.DataFrame) -> None:
    results = fit_ols(prepare(cars), "vehicle_age_years")

    with pytest.raises(KeyError, match="not a parameter"):
        effect_of(results, "colour_of_the_seats")


def test_a_single_term_combination_is_the_coefficient_itself(cars: pd.DataFrame) -> None:
    results = fit_ols(prepare(cars), f"vehicle_age_years + {LOG_MILEAGE}")

    direct = effect_of(results, "vehicle_age_years")
    combined = combined_effect(results, {"vehicle_age_years": 1.0}, name="age")

    assert combined.log_estimate == pytest.approx(direct.log_estimate)
    assert combined.log_ci_low == pytest.approx(direct.log_ci_low, abs=1e-6)
    assert combined.log_ci_high == pytest.approx(direct.log_ci_high, abs=1e-6)


def test_a_combination_carries_the_covariance_rather_than_adding_intervals(
    cars: pd.DataFrame,
) -> None:
    # Two coefficients that covary: adding their intervals would overstate the uncertainty
    # of the sum. The test asserts the combination is tighter than the naive addition,
    # which is the whole reason t_test is used instead of arithmetic.
    results = fit_ols(prepare(cars), f"vehicle_age_years + {AGE_SQUARED}")
    linear = effect_of(results, "vehicle_age_years")
    quadratic = effect_of(results, AGE_SQUARED)
    combined = combined_effect(results, {"vehicle_age_years": 1.0, AGE_SQUARED: 1.0}, name="both")

    naive_width = (linear.log_ci_high - linear.log_ci_low) + (
        quadratic.log_ci_high - quadratic.log_ci_low
    )
    assert combined.log_ci_high - combined.log_ci_low < naive_width


def test_a_combination_rejects_unknown_terms(cars: pd.DataFrame) -> None:
    results = fit_ols(prepare(cars), "vehicle_age_years")

    with pytest.raises(KeyError, match="not parameters"):
        combined_effect(results, {"vehicle_age_years": 1.0, "nonsense": 1.0}, name="x")


def test_a_log_effect_reads_as_a_multiplicative_percentage() -> None:
    effect = Effect(
        name="x",
        log_estimate=-0.08,
        log_ci_low=-0.09,
        log_ci_high=-0.07,
        std_err=0.005,
        p_value=0.0,
        n=100,
    )

    # exp(-0.08) - 1 = -7.69 %, not -8 %. The difference is the whole reason the conversion
    # is a property and not a multiplication by 100.
    assert effect.pct_estimate == pytest.approx(-7.688, abs=0.01)
    assert effect.pct_ci_low < effect.pct_ci_high
    assert effect.is_significant


def test_an_interval_straddling_zero_is_not_significant() -> None:
    effect = Effect(
        name="x",
        log_estimate=0.01,
        log_ci_low=-0.02,
        log_ci_high=0.04,
        std_err=0.015,
        p_value=0.5,
        n=100,
    )

    assert not effect.is_significant


def test_effects_frame_is_empty_for_no_effects() -> None:
    assert effects_frame([]).empty
