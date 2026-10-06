"""Fixtures for the economic analyses.

The synthetic lake is the modeling one, reused rather than rebuilt: its price law is
``log(price) = base + AGE_EFFECT * age + MILEAGE_EFFECT * log1p(km) + brand``, with known
coefficients, which is what makes it possible to assert that an estimator **recovers** a
number instead of asserting whatever a previous run printed.
"""

import numpy as np
import pandas as pd
import pytest

from tests.models.conftest import AGE_EFFECT, BRANDS, MILEAGE_EFFECT, make_gold_frame

__all__ = ["AGE_EFFECT", "BRANDS", "MILEAGE_EFFECT", "make_gold_frame"]


@pytest.fixture(scope="session")
def cars() -> pd.DataFrame:
    """A car vertical thick enough for every brand to clear the eligibility filters.

    Session-scoped, and therefore shared: every test here either reads it or copies it
    before changing anything, which is the contract that makes the sharing safe.
    """
    return make_gold_frame(1200, vehicle_type="car", seed=5)


@pytest.fixture(scope="session")
def bikes() -> pd.DataFrame:
    """A motorcycle vertical, for the paths that branch on the vertical."""
    return make_gold_frame(1200, vehicle_type="motorcycle", seed=13)


def with_department_premium(frame: pd.DataFrame, department: str, premium: float) -> pd.DataFrame:
    """Return a copy where one department's listings are dearer by a known factor.

    Args:
        frame: Gold-shaped rows.
        department: Department to make more expensive.
        premium: Proportional premium, e.g. ``0.10`` for 10 % dearer.

    Returns:
        A copy with ``price_cop`` and ``log_price`` moved consistently, so the regional
        estimator has a planted effect to find.
    """
    planted = frame.copy()
    affected = planted["department"] == department
    planted.loc[affected, "price_cop"] = (
        planted.loc[affected, "price_cop"] * (1.0 + premium)
    ).round()
    planted["log_price"] = np.log(planted["price_cop"])
    return planted
