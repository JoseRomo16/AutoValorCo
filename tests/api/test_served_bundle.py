"""The cases measured on the deployed service, replayed against the bundle it serves.

`test_contract.py` runs on a bundle trained on the synthetic lake, which is the right
place for the shape of the promise but cannot say anything about a Mazda 3 or about the
real catalogue's years. These tests load `artifacts/models/`, the directory baked into the
API image, so a re-export that breaks one of these answers fails here before it reaches
Render.

No year, displacement or price is written here: every edge is read from `/catalog` and
probed at min - 1 and max + 1. The top year is the current year + 1, so a literal 2028
would turn valid in January 2027, and a retrain moves every range. A case that needs a
particular make or model skips, saying which, when the catalogue stops listing it.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from autovalor.api import main as api_main
from autovalor.models.bundle import ARTIFACTS_DIR


@pytest.fixture(scope="module")
def served() -> Iterator[TestClient]:
    if not (ARTIFACTS_DIR / "car" / "model.json").exists():
        pytest.skip("no served bundle in artifacts/models")
    with TestClient(api_main.app) as client:
        yield client


def vertical(client: TestClient, vehicle_type: str) -> dict[str, Any]:
    """The published catalogue of one vertical."""
    verticals = client.get("/catalog").json()["verticals"]
    found: dict[str, Any] = next(v for v in verticals if v["vehicle_type"] == vehicle_type)
    return found


@pytest.fixture(scope="module")
def car(served: TestClient) -> dict[str, Any]:
    return vertical(served, "car")


@pytest.fixture(scope="module")
def request_body(car: dict[str, Any]) -> dict[str, Any]:
    """A valid car from the catalogue: its most listed make and department, a year in range."""
    brand = max(car["brands"], key=lambda entry: entry["listings"])["name"]
    years = car["model_year"]
    return {
        "vehicle_type": "car",
        "brand": brand,
        "model_year": int((years["min"] + years["max"]) // 2),
        "mileage_km": 60_000,
        "department": max(car["departments"], key=lambda entry: entry["listings"])["name"],
    }


def edges(bounds: dict[str, float]) -> tuple[int, int]:
    """The first value refused on each side of a published range."""
    return int(bounds["min"]) - 1, int(bounds["max"]) + 1


def test_a_car_year_outside_the_catalogue_is_refused(
    served: TestClient, car: dict[str, Any], request_body: dict[str, Any]
) -> None:
    for year in edges(car["model_year"]):
        response = served.post("/predict", json={**request_body, "model_year": year})
        assert response.status_code == 422, year
    for year in (int(car["model_year"]["min"]), int(car["model_year"]["max"])):
        response = served.post("/predict", json={**request_body, "model_year": year})
        assert response.status_code == 200, year


def test_a_displacement_outside_the_car_range_is_refused(
    served: TestClient, car: dict[str, Any], request_body: dict[str, Any]
) -> None:
    if car["engine_cc"] is None:
        pytest.skip("the car catalogue publishes no displacement range")
    for engine_cc in edges(car["engine_cc"]):
        response = served.post("/predict", json={**request_body, "engine_cc": engine_cc})
        assert response.status_code == 422, engine_cc


def test_an_asking_price_under_the_published_floor_is_refused(
    served: TestClient, car: dict[str, Any], request_body: dict[str, Any]
) -> None:
    floor = int(car["asking_price_cop"]["min"])
    below = served.post("/predict", json={**request_body, "asking_price_cop": floor - 1})
    at_floor = served.post("/predict", json={**request_body, "asking_price_cop": floor})
    assert below.status_code == 422
    assert at_floor.status_code == 200


@pytest.fixture(scope="module")
def mazda_3(car: dict[str, Any], request_body: dict[str, Any]) -> dict[str, Any]:
    """The Mazda 3 the displacement finding was measured on, if the catalogue still has it."""
    mazda = next((entry for entry in car["brands"] if entry["name"] == "Mazda"), None)
    if mazda is None:
        pytest.skip("the car catalogue no longer lists Mazda")
    if not any(model["name"] == "3" for model in mazda["models"]):
        pytest.skip("the car catalogue no longer lists the Mazda 3")
    bounds = car["engine_cc"]
    if bounds is None or not (bounds["min"] <= 1600 and bounds["max"] >= 2000):
        pytest.skip("1.600 and 2.000 cc are no longer both inside the car range")
    return {**request_body, "brand": "Mazda", "model": "3"}


def test_the_displacement_moves_the_price(served: TestClient, mazda_3: dict[str, Any]) -> None:
    small = served.post("/predict", json={**mazda_3, "engine_cc": 1600}).json()
    large = served.post("/predict", json={**mazda_3, "engine_cc": 2000}).json()
    assert large["band"]["estimate_cop"] > small["band"]["estimate_cop"]


def test_explain_names_the_displacement_it_was_given(
    served: TestClient, mazda_3: dict[str, Any]
) -> None:
    factors = served.post("/explain", json={**mazda_3, "engine_cc": 2000}).json()["factors"]
    assert "Cilindrada" in {factor["label"]["es"] for factor in factors}


def test_a_make_nobody_sells_is_refused(served: TestClient, request_body: dict[str, Any]) -> None:
    response = served.post("/predict", json={**request_body, "brand": "<script>"})
    assert response.status_code == 422


def test_a_motorcycle_make_is_refused_on_a_car(
    served: TestClient, car: dict[str, Any], request_body: dict[str, Any]
) -> None:
    motorcycle_makes = {entry["name"] for entry in vertical(served, "motorcycle")["brands"]}
    if "Bajaj" not in motorcycle_makes:
        pytest.skip("the motorcycle catalogue no longer lists Bajaj")
    assert "Bajaj" not in {entry["name"] for entry in car["brands"]}
    response = served.post("/predict", json={**request_body, "brand": "Bajaj"})
    assert response.status_code == 422
