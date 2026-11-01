"""Tests for the shared-rules layer: what the catalogue says, ``/predict`` enforces.

Every case here is one the audit observed on the deployed service answering 200 with a
confident number. The catalogue is built from the synthetic lake, so the bounds come from
training data rather than from constants typed into the test.
"""

from typing import Any

import pytest
from fastapi import HTTPException

from autovalor.api.rules import DEPARTMENT_NOT_COVERED, MODEL_NOT_COVERED, resolve, year_range
from autovalor.api.schemas import PredictRequest
from autovalor.models.catalog import VehicleCatalog, build_catalog

from ..models.conftest import make_gold_frame

CAR: dict[str, Any] = {
    "vehicle_type": "car",
    "brand": "Toyota",
    "model": "corolla",
    "model_year": 2018,
    "mileage_km": 60_000,
    "department": "Antioquia",
}


@pytest.fixture(scope="module")
def catalog() -> VehicleCatalog:
    frame = make_gold_frame(600, vehicle_type="car", seed=7)
    return build_catalog(frame, vehicle_type="car")


def ask(**overrides: Any) -> PredictRequest:
    return PredictRequest(**{**CAR, **overrides})


def refused(catalog: VehicleCatalog, **overrides: Any) -> str:
    """Return the 422 detail for a request that must not be answered."""
    with pytest.raises(HTTPException) as caught:
        resolve(ask(**overrides), catalog)
    assert caught.value.status_code == 422
    return str(caught.value.detail)


# --- model year ------------------------------------------------------------


def test_a_year_before_the_training_range_is_refused(catalog: VehicleCatalog) -> None:
    # Observed: model_year 1954 answered 200 with 37,6 M.
    lowest = int(catalog.model_year.min)
    assert str(lowest) in refused(catalog, model_year=lowest - 1)


def test_a_year_past_the_range_is_refused(catalog: VehicleCatalog) -> None:
    # Observed: model_year 2028 answered 200 with 127,2 M, pure extrapolation.
    assert "extrapolates" in refused(catalog, model_year=int(catalog.model_year.max) + 1)


def test_both_ends_of_the_published_range_are_accepted(catalog: VehicleCatalog) -> None:
    lowest, highest = year_range(catalog)
    for year in (lowest, highest):
        assert resolve(ask(model_year=year), catalog).warnings == []


def test_the_top_year_is_never_more_than_next_year(catalog: VehicleCatalog) -> None:
    # The cap only bites when the catalogue reaches past it -- the real car bundle tops out
    # at 2027 -- so what is asserted is the promise, not one arithmetic case.
    for now in (2026, 2030, 2040):
        assert year_range(catalog, year=now)[1] <= now + 1


def test_the_top_year_is_the_catalogue_when_that_is_lower(catalog: VehicleCatalog) -> None:
    # Dealers list next year, but the model cannot value a year it never saw, so the
    # training maximum wins whenever it is the smaller of the two.
    observed = int(catalog.model_year.max)
    assert year_range(catalog, year=observed + 5)[1] == observed


def test_the_year_cap_tightens_as_the_bundle_ages(catalog: VehicleCatalog) -> None:
    # A bundle trained in 2026 and served in 2020 must not keep offering 2027.
    assert year_range(catalog, year=2019)[1] == 2020


def test_the_year_range_never_inverts(catalog: VehicleCatalog) -> None:
    # Served far enough in the past, the cap would fall below the floor and reject every
    # year there is.
    lowest, highest = year_range(catalog, year=1900)
    assert lowest <= highest


# --- displacement ----------------------------------------------------------


def test_a_displacement_the_vertical_never_saw_is_refused(catalog: VehicleCatalog) -> None:
    # Observed: a car with engine_cc 50 answered 200 and moved the estimate by 5 M.
    assert catalog.engine_cc is not None
    assert "leave it empty" in refused(catalog, engine_cc=int(catalog.engine_cc.min) - 1)


def test_an_absent_displacement_is_still_fine(catalog: VehicleCatalog) -> None:
    # The field is optional on purpose: the model treats a missing engine as a signal.
    assert resolve(ask(engine_cc=None), catalog).request.engine_cc is None


def test_a_displacement_inside_the_range_passes(catalog: VehicleCatalog) -> None:
    assert catalog.engine_cc is not None
    inside = int((catalog.engine_cc.min + catalog.engine_cc.max) / 2)
    assert resolve(ask(engine_cc=inside), catalog).request.engine_cc == inside


# --- asking price ----------------------------------------------------------


def test_a_price_below_the_training_floor_is_refused(catalog: VehicleCatalog) -> None:
    # Observed: asking_price_cop 59 came back labelled "Ganga - Pides 100 % menos".
    assert "typo rather than a bargain" in refused(catalog, asking_price_cop=59)


def test_a_price_above_the_ceiling_is_answered(catalog: VehicleCatalog) -> None:
    # Deliberately asymmetric: asking far too much is exactly what the expensive label
    # exists to report, so rejecting it would delete the answer the caller came for.
    assert catalog.asking_price_cop is not None
    high = int(catalog.asking_price_cop.max) * 10
    assert resolve(ask(asking_price_cop=high), catalog).warnings == []


def test_the_price_floor_comes_from_the_data_not_a_round_number(catalog: VehicleCatalog) -> None:
    # A fixed million-peso floor would reject motorcycles that are in the training data,
    # which is why this is per vertical and derived.
    assert catalog.asking_price_cop is not None
    prices = make_gold_frame(600, vehicle_type="car", seed=7)["price_cop"]
    assert catalog.asking_price_cop.min >= prices.min()
    assert catalog.asking_price_cop.max <= prices.max()


# --- make ------------------------------------------------------------------


@pytest.mark.parametrize("spelling", ["toyota", "TOYOTA", "  Toyota  ", "ToYoTa"])
def test_the_make_spelling_does_not_change_the_answer(
    catalog: VehicleCatalog, spelling: str
) -> None:
    # Observed: "toyota" valued 58,0 M and "Toyota" 72,7 M -- 20 % apart, silently.
    assert resolve(ask(brand=spelling), catalog).request.brand == "Toyota"


def test_a_make_the_model_never_saw_is_refused(catalog: VehicleCatalog) -> None:
    # Observed: brand "<script>" answered 200 with a price. React escapes the text, so it
    # was never XSS -- the problem is that the model cannot value a make it has no category
    # for and answered anyway.
    assert "not one the car model was trained on" in refused(catalog, brand="<script>")


def test_a_make_from_the_other_vertical_is_refused(catalog: VehicleCatalog) -> None:
    # Observed: "Bajaj" in a car gave the same 58,0 M as any other unknown make.
    refused(catalog, brand="Bajaj")


# --- model token -----------------------------------------------------------


def test_an_unknown_token_is_dropped_and_flagged(catalog: VehicleCatalog) -> None:
    # Observed: model "zzz" answered 200 with 93,3 M -- more than a Corolla -- with nothing
    # to say the token meant nothing.
    checked = resolve(ask(model="zzz"), catalog)
    assert checked.request.model is None
    assert checked.warnings == [MODEL_NOT_COVERED]


def test_a_token_from_another_make_is_dropped(catalog: VehicleCatalog) -> None:
    # Observed: "mazda 3" under Toyota was valued as if it meant something.
    checked = resolve(ask(brand="Toyota", model="cx30"), catalog)
    assert checked.request.model is None
    assert checked.warnings == [MODEL_NOT_COVERED]


def test_dropping_the_token_matches_not_sending_one(catalog: VehicleCatalog) -> None:
    # The promise behind warning instead of rejecting: the answer is the one the caller
    # would have got by leaving the field blank.
    unknown = resolve(ask(model="zzz"), catalog).request
    absent = resolve(ask(model=None), catalog).request
    assert unknown.model == absent.model


def test_a_known_token_is_kept(catalog: VehicleCatalog) -> None:
    checked = resolve(ask(model="corolla"), catalog)
    assert checked.request.model == "corolla"
    assert checked.warnings == []


def test_the_token_is_matched_case_insensitively(catalog: VehicleCatalog) -> None:
    # The API expected the token lower-cased and the make capitalised, which is two
    # criteria for one kind of field.
    assert resolve(ask(model="Corolla"), catalog).request.model == "corolla"


def test_an_empty_token_is_not_a_warning(catalog: VehicleCatalog) -> None:
    assert resolve(ask(model=""), catalog).warnings == []


# --- department ------------------------------------------------------------


def test_an_uncovered_department_is_answered_and_flagged(catalog: VehicleCatalog) -> None:
    # Refusing would leave whoever lives there with no service at all.
    assert resolve(ask(department="Nariño"), catalog).warnings == [DEPARTMENT_NOT_COVERED]


@pytest.mark.parametrize("spelling", ["Bogota D.C.", "bogota d.c.", "BOGOTA D.C."])
def test_the_department_spelling_and_accents_are_normalised(
    catalog: VehicleCatalog, spelling: str
) -> None:
    checked = resolve(ask(department=spelling), catalog)
    assert checked.request.department == "Bogota D.C."
    assert checked.warnings == []


# --- a bundle with no catalogue --------------------------------------------


def test_a_bundle_with_no_catalogue_still_answers() -> None:
    # Refusing every request over a missing list would turn a stale bundle into an outage.
    # The bundle and the service deploy separately. 1950 rather than 1800: the schema keeps
    # outer sanity bounds on the wire format, and the point here is that the
    # catalogue-derived rules are the ones skipped.
    checked = resolve(ask(model_year=1950, brand="whatever"), None)
    assert checked.request.brand == "whatever"
    assert checked.warnings == []
