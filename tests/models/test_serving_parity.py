"""Training/serving parity: the published figures must describe what the API serves.

Block 4 found the gate had been scored with each listing's real city, which ``/predict``
never sends; with the city it does send, the car band covered 75 % instead of 80 % and the
car label was published on a band that missed the gate in production. These tests make
that class of bug fail in CI, for ``city`` and for any column added later:

1. Every model column ``to_frame`` fills with a constant — i.e. one no request can change —
   must be declared in :data:`SERVING_ASSUMPTIONS`, with the same value.
2. Every frame the band is calibrated or scored on must carry, in each declared column,
   the value the API sends. A model column evaluated with a value the API cannot send fails.
"""

from typing import Any

import numpy as np
import pandas as pd
import pytest

from autovalor.api.features import to_frame
from autovalor.api.schemas import PredictRequest
from autovalor.models import quantiles
from autovalor.models.dataset import VEHICLE_TYPES, VehicleType, split_listings
from autovalor.models.serving import SERVING_ASSUMPTIONS, as_served
from autovalor.models.train import train_model
from autovalor.models.trees import tree_spec
from tests.models.conftest import make_gold_frame

# Two requests that differ in every field a caller can set, so a column that comes out
# equal in both cannot have been taken from the request.
_REQUESTS: dict[VehicleType, tuple[dict[str, Any], dict[str, Any]]] = {
    "car": (
        {
            "vehicle_type": "car",
            "brand": "Toyota",
            "model": "corolla",
            "model_year": 2018,
            "mileage_km": 60_000,
            "department": "Antioquia",
            "engine_cc": 1800,
        },
        {
            "vehicle_type": "car",
            "brand": "Mazda",
            "model": "3",
            "model_year": 2012,
            "mileage_km": 150_000,
            "department": "Bogotá D.C.",
            "engine_cc": None,
        },
    ),
    "motorcycle": (
        {
            "vehicle_type": "motorcycle",
            "brand": "Yamaha",
            "model": "nmax",
            "model_year": 2021,
            "mileage_km": 10_000,
            "department": "Antioquia",
            "engine_cc": 155,
        },
        {
            "vehicle_type": "motorcycle",
            "brand": "Bajaj",
            "model": "pulsar",
            "model_year": 2015,
            "mileage_km": 45_000,
            "department": "Valle del Cauca",
            "engine_cc": None,
        },
    ),
}


def _api_fixed_columns(vehicle_type: VehicleType) -> dict[str, Any]:
    """Model columns whose value ``to_frame`` does not take from the request."""
    first, second = (
        to_frame(PredictRequest(**body), year=2026) for body in _REQUESTS[vehicle_type]
    )
    fixed = {}
    for column in tree_spec(vehicle_type).columns:
        assert column in first.columns, f"the API does not send model column {column!r}"
        a: Any = first.at[0, column]
        b: Any = second.at[0, column]
        if (bool(pd.isna(a)) and bool(pd.isna(b))) or a == b:
            fixed[column] = a
    return fixed


@pytest.mark.parametrize("vehicle_type", VEHICLE_TYPES)
def test_every_constant_the_api_sends_is_a_declared_serving_assumption(
    vehicle_type: VehicleType,
) -> None:
    fixed = _api_fixed_columns(vehicle_type)
    undeclared = sorted(set(fixed) - set(SERVING_ASSUMPTIONS))
    assert not undeclared, (
        f"to_frame fixes {undeclared} on every request, but SERVING_ASSUMPTIONS does not "
        "declare them, so the published figures are scored with values the API never sends"
    )
    for column, value in fixed.items():
        assert value == SERVING_ASSUMPTIONS[column], column


@pytest.mark.parametrize("vehicle_type", VEHICLE_TYPES)
def test_city_is_not_a_model_column(vehicle_type: VehicleType) -> None:
    # Block 4: the form never asks for the city, so the model must not read it.
    assert "city" not in tree_spec(vehicle_type).columns
    assert "city" not in tree_spec(vehicle_type, detail_features=True).columns


@pytest.mark.parametrize("vehicle_type", VEHICLE_TYPES)
def test_the_api_frame_carries_no_city(vehicle_type: VehicleType) -> None:
    frame = to_frame(PredictRequest(**_REQUESTS[vehicle_type][0]), year=2026)
    assert "city" not in frame.columns


def test_as_served_applies_every_declared_value_and_nothing_else() -> None:
    frame = make_gold_frame(20)
    served = as_served(frame)
    for column, value in SERVING_ASSUMPTIONS.items():
        if column in frame.columns:
            assert (served[column] == value).all(), column
    untouched = [c for c in frame.columns if c not in SERVING_ASSUMPTIONS]
    pd.testing.assert_frame_equal(served[untouched], frame[untouched])


@pytest.mark.parametrize("vehicle_type", VEHICLE_TYPES)
def test_the_band_is_calibrated_and_gated_on_what_the_api_sends(
    vehicle_type: VehicleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The fixture carries values the API cannot send: a real city, and official-store
    # listings. Every frame the quantile models score during the fit -- the calibration
    # rows and the holdout the gate reads -- must arrive with the API's values instead.
    frame = make_gold_frame(600, vehicle_type=vehicle_type, seed=3)
    assert frame["is_official_store"].any()
    scored: list[pd.DataFrame] = []
    original = quantiles._raw_bounds

    def spy(models: Any, scored_frame: pd.DataFrame) -> Any:
        scored.append(scored_frame)
        return original(models, scored_frame)

    monkeypatch.setattr(quantiles, "_raw_bounds", spy)
    train_model(split_listings(frame), "lightgbm", n_trials=0, explain=False)

    assert len(scored) >= 2, "expected the calibration rows and the holdout to be scored"
    spec = tree_spec(vehicle_type)
    for scored_frame in scored:
        for column, value in SERVING_ASSUMPTIONS.items():
            if column in spec.columns:
                values = scored_frame[column].to_numpy()
                assert np.all(values == value), (
                    f"the band was scored with {column}={sorted(set(values))!r}, which the "
                    f"API cannot send (it always sends {value!r})"
                )


def test_the_published_error_is_measured_on_what_the_api_sends() -> None:
    frame = make_gold_frame(600, seed=5)
    dataset = split_listings(frame)
    result = train_model(dataset, "lightgbm", n_trials=0, explain=False, intervals=False)
    expected = result.model.predict_log_price(as_served(dataset.test))
    actual = np.exp(expected - dataset.test["log_price"].to_numpy()) - 1
    assert result.test_report.mape == pytest.approx(float(np.mean(np.abs(actual))))


def test_the_published_segment_error_is_measured_on_what_the_api_sends() -> None:
    # /market serves segment_error beside the headline MAPE; both must describe the
    # model as served, or an official-store-heavy brand gets a flattering figure.
    from types import SimpleNamespace

    from autovalor.analysis.segments import segment_errors

    seen: list[pd.DataFrame] = []

    class _Recorder:
        def predict_log_price(self, frame: pd.DataFrame) -> Any:
            seen.append(frame)
            return frame["log_price"].to_numpy()

    dataset = split_listings(make_gold_frame(600, seed=9))
    result = SimpleNamespace(model=_Recorder(), vehicle_type="car", model_kind="lightgbm")
    segment_errors(result, dataset, min_rows=1)  # type: ignore[arg-type]

    assert seen
    for frame in seen:
        assert not frame["is_official_store"].any()


def test_the_published_importance_is_measured_on_what_the_api_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from autovalor.models import train as train_module

    seen: list[pd.DataFrame] = []
    original = train_module.global_importance  # type: ignore[attr-defined]

    def spy(model: Any, frame: pd.DataFrame) -> Any:
        seen.append(frame)
        return original(model, frame)

    monkeypatch.setattr(train_module, "global_importance", spy)
    frame = make_gold_frame(600, seed=11)
    train_model(split_listings(frame), "lightgbm", n_trials=0, intervals=False)

    assert seen
    assert all(not scored["is_official_store"].any() for scored in seen)
