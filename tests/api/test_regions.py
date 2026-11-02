"""Tests for how an uncovered department is answered.

The claim being protected is narrow and checkable: the estimate is the listing-weighted
geometric mean over the departments the model does know, the band is averaged the same way,
and the explanation still reconciles exactly against it.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from autovalor.api.features import to_frame
from autovalor.api.regions import average_band, average_contributions, spread, weights
from autovalor.api.schemas import PredictRequest
from autovalor.models.bundle import ServedModel, load_served_models
from autovalor.models.catalog import NamedCount, VehicleCatalog

CAR: dict[str, Any] = {
    "vehicle_type": "car",
    "brand": "Toyota",
    "model": "corolla",
    "model_year": 2018,
    "mileage_km": 60_000,
    "department": "Antioquia",
}


@pytest.fixture(scope="module")
def model(artifacts: Path) -> ServedModel:
    return load_served_models(artifacts)["car"]


def test_the_weights_are_the_published_listing_counts() -> None:
    catalog = _catalog(("Bogota", 300), ("Cauca", 100))
    assert weights(catalog) == (("Bogota", 0.75), ("Cauca", 0.25))


def test_the_weights_sum_to_one() -> None:
    catalog = _catalog(("A", 1), ("B", 2), ("C", 7))
    assert sum(share for _, share in weights(catalog)) == pytest.approx(1.0)


def test_a_thin_department_does_not_count_as_much_as_a_large_one() -> None:
    # Cauca has one training listing and Bogota 1.251. An unweighted mean would let a
    # region the model barely saw drag the national average around.
    catalog = _catalog(("Bogota", 1251), ("Cauca", 1))
    shares = dict(weights(catalog))
    assert shares["Bogota"] > 100 * shares["Cauca"]


def test_a_catalogue_with_no_departments_averages_over_nothing() -> None:
    assert weights(_catalog()) == ()


def test_spreading_varies_only_the_department(model: ServedModel) -> None:
    frame = to_frame(PredictRequest(**CAR))
    spread_frame = spread(frame, ["A", "B", "C"])

    assert list(spread_frame["department"]) == ["A", "B", "C"]
    for column in frame.columns:
        if column == "department":
            continue
        assert spread_frame[column].nunique(dropna=False) == 1, column


def test_the_band_stays_ordered_after_averaging(model: ServedModel) -> None:
    # Every row comes out of predict_published_band ordered, and a weighted mean of
    # ordered triples is ordered -- so the published range can never exclude the estimate
    # printed next to it.
    assert model.catalog is not None
    lower, estimate, upper = average_band(
        model, to_frame(PredictRequest(**CAR)), weights(model.catalog)
    )
    assert lower <= estimate <= upper


def test_the_estimate_lands_between_the_departments_it_averages(model: ServedModel) -> None:
    # A mean is not an extrapolation: it has to sit inside the range of what was averaged.
    assert model.catalog is not None
    pairs = weights(model.catalog)
    frame = to_frame(PredictRequest(**CAR))
    per_department = np.asarray(
        model.predict_published_band(spread(frame, [name for name, _ in pairs]))
    )[:, 1]

    averaged = average_band(model, frame, pairs)[1]
    assert per_department.min() <= averaged <= per_department.max()


def test_the_explanation_reconciles_against_the_averaged_estimate(model: ServedModel) -> None:
    # The property that makes the explanation checkable rather than decorative:
    # base + sum(phi) == the prediction, exactly, even after averaging.
    assert model.catalog is not None
    contributions, base, predicted = average_contributions(
        model, to_frame(PredictRequest(**CAR)), weights(model.catalog)
    )
    assert base + float(contributions.sum()) == pytest.approx(predicted, rel=1e-9)


def test_the_averaged_prediction_is_the_mean_of_the_predictions(model: ServedModel) -> None:
    assert model.catalog is not None
    pairs = weights(model.catalog)
    frame = to_frame(PredictRequest(**CAR))
    rows = np.asarray(model.predict_log_price(spread(frame, [name for name, _ in pairs])))
    expected = float(np.average(rows, weights=[share for _, share in pairs]))

    _, _, predicted = average_contributions(model, frame, pairs)
    assert predicted == pytest.approx(expected, rel=1e-9)


def test_averaging_one_department_is_just_predicting_it(model: ServedModel) -> None:
    # The degenerate case has to agree with the ordinary path, or the two code paths are
    # measuring different things.
    frame = to_frame(PredictRequest(**{**CAR, "department": "Antioquia"}))
    direct = np.asarray(model.predict_published_band(frame))[0]
    averaged = average_band(model, frame, (("Antioquia", 1.0),))
    assert averaged == pytest.approx(direct)


def _catalog(*departments: tuple[str, int]) -> VehicleCatalog:
    """A catalogue carrying nothing but the departments under test."""
    from autovalor.models.catalog import NumericRange

    return VehicleCatalog(
        vehicle_type="car",
        n_rows=sum(count for _, count in departments),
        brands=(),
        departments=tuple(
            NamedCount(name=name, listings=count, display_name=name) for name, count in departments
        ),
        model_year=NumericRange(min=2000.0, max=2026.0),
        engine_cc=None,
    )
