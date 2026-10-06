import pandas as pd
import pytest

from autovalor.analysis.inference import POOLED_LEVEL
from autovalor.analysis.mileage import (
    ALL_SEGMENTS,
    MILEAGE_STEP_KM,
    PRICE_SEGMENTS,
    mileage_effects,
    price_segments,
    vehicle_price_class,
)
from autovalor.analysis.regional import NOT_PLACES, regional_effects

from .conftest import MILEAGE_EFFECT, with_department_premium


def test_the_price_class_is_a_property_of_the_vehicle_not_the_listing(cars: pd.DataFrame) -> None:
    # Two listings of the same model share a class however differently they are priced,
    # which is what keeps the segment cut from conditioning on the dependent variable.
    classes = vehicle_price_class(cars)
    same_model = cars["model"] == cars["model"].iloc[0]

    assert classes[same_model].nunique() == 1


def test_the_segments_cover_every_row_in_order(cars: pd.DataFrame) -> None:
    segments = price_segments(cars)

    assert len(segments) == len(cars)
    assert set(segments.unique()) <= {f"Q{index + 1}" for index in range(PRICE_SEGMENTS)}


def test_the_mileage_effect_recovers_the_fixture_elasticity(cars: pd.DataFrame) -> None:
    effects = mileage_effects(cars, vehicle_type="car")

    overall = effects[effects["segment"] == ALL_SEGMENTS].iloc[0]
    assert overall["elasticity"] == pytest.approx(MILEAGE_EFFECT, abs=0.01)


def test_more_kilometres_cost_money(cars: pd.DataFrame) -> None:
    effects = mileage_effects(cars, vehicle_type="car")
    overall = effects[effects["segment"] == ALL_SEGMENTS].iloc[0]

    assert overall["cop_per_step"] < 0
    assert overall["significant"]


def test_the_peso_figure_matches_its_own_elasticity_and_base(cars: pd.DataFrame) -> None:
    # The conversion is the part a reader has to trust, so it is checked against the medians
    # the row itself reports rather than against a constant.
    import numpy as np

    overall = mileage_effects(cars, vehicle_type="car").iloc[0]
    step = np.log1p(overall["median_mileage_km"] + MILEAGE_STEP_KM) - np.log1p(
        overall["median_mileage_km"]
    )
    expected = np.expm1(overall["elasticity"] * step) * overall["median_price_cop"]

    assert overall["cop_per_step"] == pytest.approx(expected)


def test_the_interval_ends_keep_their_order(cars: pd.DataFrame) -> None:
    effects = mileage_effects(cars, vehicle_type="car")

    assert (effects["cop_ci_low"] <= effects["cop_per_step"]).all()
    assert (effects["cop_per_step"] <= effects["cop_ci_high"]).all()


def test_the_whole_vertical_is_reported_beside_the_segments(cars: pd.DataFrame) -> None:
    effects = mileage_effects(cars, vehicle_type="car")

    assert (effects["segment"] == ALL_SEGMENTS).sum() == 1
    assert len(effects) > 1


def test_regional_recovers_a_planted_premium(cars: pd.DataFrame) -> None:
    # The reference is the most listed department, so the fixture's near-even split is
    # tilted first: without that, whichever department wins the tie becomes the baseline
    # and the planted effect could land on the reference itself, at zero by construction.
    tilted = cars.copy()
    tilted.loc[tilted.index[: len(tilted) // 2], "department"] = "Bogota D.C."
    planted = with_department_premium(tilted, "Antioquia", 0.12)

    effects = regional_effects(planted, vehicle_type="car")
    antioquia = effects[effects["department"] == "Antioquia"]

    assert effects[effects["is_reference"]]["department"].iloc[0] == "Bogota D.C."
    assert not antioquia.empty
    assert antioquia["pct_change"].iloc[0] == pytest.approx(12.0, abs=2.0)
    assert bool(antioquia["significant"].iloc[0])


def test_the_reference_department_sits_at_zero(cars: pd.DataFrame) -> None:
    effects = regional_effects(cars, vehicle_type="car")
    reference = effects[effects["is_reference"]]

    assert len(reference) == 1
    assert reference["pct_change"].iloc[0] == 0.0


def test_the_pooled_bucket_is_a_control_and_not_a_result(cars: pd.DataFrame) -> None:
    thinned = cars.copy()
    thinned.loc[thinned.index[:10], "department"] = "Vaupes"
    thinned.loc[thinned.index[10:50], "department"] = "Desconocido"

    effects = regional_effects(thinned, vehicle_type="car")

    assert not effects["department"].isin(NOT_PLACES).any()
    assert POOLED_LEVEL not in set(effects["department"])
