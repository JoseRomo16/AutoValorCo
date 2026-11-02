"""Tests for the Block 4 band diagnostics.

The fake model scores each department at a fixed log level, so every average and every
position below can be checked by hand. The property that matters most is the exclusion
in the "Otro departamento" measurement: a row must never be averaged over its own
department, or the figure is partly of the covered case and reads optimistic.
"""

from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pandas as pd
import pytest

from autovalor.models.band_diagnostics import (
    city_shap,
    condition_metrics,
    department_effects,
    diagnose,
    exclusion_weights,
    position_in_band,
    uncovered_bands,
    uncovered_coverage,
    width_by_quartile,
)
from autovalor.models.bundle import ServedModel
from autovalor.models.catalog import NamedCount

PAIRS = (("A", 1.0), ("B", 3.0), ("Bogotá D.C.", 6.0))
LEVEL = {"A": 10.0, "B": 11.0, "Bogotá D.C.": 12.0}


class _FakeModel:
    """``log(price)`` is a fixed level per department; the band is +-0.5 around it.

    ``shift`` moves the point estimate off the band's centre, which is how the
    published-band widening and the position measurement get exercised.
    """

    def __init__(self, *, shift: float = 0.0, uses_city: bool = False) -> None:
        self.vehicle_type = "car"
        self.version = "test.1"
        self.metrics = {"interval_coverage": 0.8, "interval_mean_relative_width": 0.4}
        self.lake: dict[str, Any] = {}
        self.catalog = SimpleNamespace(
            departments=tuple(
                NamedCount(name=name, listings=int(count), display_name=name)
                for name, count in PAIRS
            )
        )
        categorical = ("department", "city") if uses_city else ("department",)
        self.point = SimpleNamespace(spec=SimpleNamespace(categorical=categorical))
        self.shift = shift
        self.seen: list[pd.DataFrame] = []

    def _centre(self, frame: pd.DataFrame) -> Any:
        self.seen.append(frame)
        return frame["department"].map(LEVEL).to_numpy(dtype=np.float64)

    def predict_log_price(self, frame: pd.DataFrame) -> Any:
        return self._centre(frame) + self.shift

    def predict_bounds(self, frame: pd.DataFrame) -> Any:
        centre = self._centre(frame)
        return np.column_stack([centre - 0.5, centre, centre + 0.5])

    def predict_published_band(self, frame: pd.DataFrame) -> Any:
        bounds = self.predict_bounds(frame)
        estimate = self.predict_log_price(frame)
        return np.column_stack(
            [np.minimum(bounds[:, 0], estimate), estimate, np.maximum(bounds[:, 2], estimate)]
        )


def _served(fake: _FakeModel) -> ServedModel:
    return cast(ServedModel, fake)


# --- position and width ---------------------------------------------------------------


def test_the_position_is_zero_at_p10_and_one_at_p90() -> None:
    lower, upper = np.array([1.0, 1.0, 1.0]), np.array([3.0, 3.0, 3.0])
    assert position_in_band(np.array([1.0, 2.0, 3.0]), lower, upper).tolist() == [0, 0.5, 1]


def test_a_zero_width_band_sits_in_the_middle_instead_of_dividing_by_zero() -> None:
    one = np.array([2.0])
    assert position_in_band(one, one, one).tolist() == [0.5]


def test_width_is_cut_on_the_estimate_into_four_quartiles() -> None:
    estimate = np.log(np.arange(1.0, 9.0))
    rows = width_by_quartile(estimate - 0.1, estimate, estimate + 0.1)
    assert [row["quartile"] for row in rows] == [1.0, 2.0, 3.0, 4.0]
    assert sum(row["n"] for row in rows) == 8
    assert rows[0]["median_p90_over_p10"] == pytest.approx(np.exp(0.2))


# --- one condition --------------------------------------------------------------------


def test_a_centred_estimate_sits_at_half_and_nothing_is_widened() -> None:
    frame = pd.DataFrame({"department": ["A", "B"], "log_price": [10.0, 11.0]})
    metrics = condition_metrics(_served(_FakeModel()), frame)

    assert metrics["position"]["median"] == pytest.approx(0.5)
    assert metrics["widened"]["share"] == 0.0
    assert metrics["mape"] == pytest.approx(0.0)
    assert metrics["coverage_published"] == 1.0


def test_an_estimate_outside_the_band_is_counted_as_widened_and_at_an_edge() -> None:
    # The point model sits 0.7 above a band of half-width 0.5: the published band has to
    # widen to contain it, and the estimate lands exactly on its upper edge.
    frame = pd.DataFrame({"department": ["A"], "log_price": [10.0]})
    metrics = condition_metrics(_served(_FakeModel(shift=0.7)), frame)

    assert metrics["widened"] == {"below_p10": 0.0, "above_p90": 1.0, "share": 1.0}
    assert metrics["position"]["median"] == pytest.approx(1.0)
    assert metrics["position"]["share_above_0_8"] == 1.0
    assert metrics["point_minus_p50_log"]["mean"] == pytest.approx(0.7)
    assert metrics["p50_mape"] == pytest.approx(0.0)


def test_bias_is_negative_when_the_model_underestimates() -> None:
    frame = pd.DataFrame({"department": ["A"], "log_price": [10.0]})
    assert condition_metrics(_served(_FakeModel(shift=-0.1)), frame)["bias_log"] < 0


# --- the uncovered department ---------------------------------------------------------


def test_a_row_is_never_averaged_over_its_own_department() -> None:
    weights = exclusion_weights(["A", "B", "Bogotá D.C."], PAIRS)
    assert np.diag(weights).tolist() == [0.0, 0.0, 0.0]


def test_the_remaining_weights_are_renormalised() -> None:
    weights = exclusion_weights(["Bogotá D.C."], PAIRS)
    assert weights[0].tolist() == pytest.approx([0.25, 0.75, 0.0])


def test_an_unknown_department_keeps_every_weight() -> None:
    assert exclusion_weights(["Nariño"], PAIRS)[0].tolist() == pytest.approx([0.1, 0.3, 0.6])


def test_a_single_department_model_has_nothing_to_average() -> None:
    with pytest.raises(ValueError, match="no department"):
        exclusion_weights(["A"], (("A", 5.0),))


def test_the_uncovered_band_is_the_weighted_mean_over_the_other_departments() -> None:
    frame = pd.DataFrame({"department": ["Bogotá D.C.", "A"]})
    bands = uncovered_bands(_served(_FakeModel()), frame, PAIRS)
    # Bogotá: A and B at 1:3; A: B and Bogotá at 3:6.
    assert bands[:, 1].tolist() == pytest.approx([10.75, 11 / 3 + 12 * 2 / 3])


def test_uncovered_coverage_is_judged_against_the_gate_window() -> None:
    # Bogotá averages to 10.75 and 11.0 is inside; A averages to 11.67 and 13.0 is not.
    frame = pd.DataFrame({"department": ["Bogotá D.C.", "A"], "log_price": [11.0, 13.0]})
    result = uncovered_coverage(_served(_FakeModel()), frame, PAIRS)
    assert result["coverage"] == pytest.approx(0.5)
    assert result["within_gate"] is False


# --- geography and city ---------------------------------------------------------------


def test_department_effects_are_against_bogota_and_sit_beside_the_market() -> None:
    frame = pd.DataFrame({"department": ["A"]})
    market = [{"department": "A", "pct_change": -60.0, "significant": True}]
    rows = {
        row["department"]: row
        for row in department_effects(_served(_FakeModel()), frame, PAIRS, market)
    }

    assert rows["Bogotá D.C."]["model_pct"] == pytest.approx(0.0)
    assert rows["A"]["model_pct"] == pytest.approx(np.expm1(-2.0) * 100)
    assert rows["A"]["market_pct"] == -60.0
    assert rows["B"]["market_pct"] is None


def test_a_model_without_city_reports_no_city_pull() -> None:
    frame = pd.DataFrame({"department": ["A"]})
    assert city_shap(_served(_FakeModel()), frame) is None


def test_the_served_condition_scores_what_the_api_sends() -> None:
    fake = _FakeModel()
    test = pd.DataFrame(
        {
            "department": ["A"],
            "city": ["Medellín"],
            "is_official_store": [True],
            "log_price": [10.0],
        }
    )
    result = diagnose(_served(fake), test)

    assert set(result["conditions"]) == {"real", "served"}
    served_frames = [frame for frame in fake.seen if (frame["city"] == "Desconocida").all()]
    assert served_frames, "no frame was scored with the city the API sends"
    assert all(not frame["is_official_store"].any() for frame in served_frames)
