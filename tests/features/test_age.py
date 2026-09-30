"""Tests for autovalor.features.age."""

from datetime import date

import pytest

from autovalor.features.age import MIN_MODEL_YEAR, vehicle_age

REFERENCE = date(2026, 9, 29)


@pytest.mark.parametrize(
    ("model_year", "expected"),
    [
        (2026, 0),
        (2025, 1),
        (2018, 8),
        (2000, 26),
        (MIN_MODEL_YEAR, 126),
    ],
)
def test_returns_calendar_year_difference(model_year: int, expected: int) -> None:
    assert vehicle_age(model_year, REFERENCE) == expected


def test_next_year_model_is_floored_at_zero() -> None:
    """A 2027 model sold in 2026 is new, not minus one year old."""
    assert vehicle_age(2027, REFERENCE) == 0


def test_defaults_to_today() -> None:
    today = date.today()
    assert vehicle_age(today.year) == 0


@pytest.mark.parametrize("model_year", [0, 199, MIN_MODEL_YEAR - 1])
def test_rejects_years_below_minimum(model_year: int) -> None:
    with pytest.raises(ValueError, match="below the minimum"):
        vehicle_age(model_year, REFERENCE)


@pytest.mark.parametrize("model_year", [2028, 3000])
def test_rejects_implausible_future_years(model_year: int) -> None:
    with pytest.raises(ValueError, match="implausible"):
        vehicle_age(model_year, REFERENCE)
