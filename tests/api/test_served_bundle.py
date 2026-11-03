"""The cases measured on the deployed service, replayed against the bundle it serves.

`test_contract.py` runs on a bundle trained on the synthetic lake, which is the right
place for the shape of the promise but cannot say anything about a Mazda 3 or about
1955: those are facts of the real catalogue. These tests load `artifacts/models/`, the
directory baked into the API image, so a re-export that moves a published range or
breaks one of these answers fails here before it reaches Render.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from autovalor.api import main as api_main
from autovalor.models.bundle import ARTIFACTS_DIR

MAZDA_3 = {
    "vehicle_type": "car",
    "brand": "Mazda",
    "model": "3",
    "model_year": 2018,
    "mileage_km": 60_000,
    "department": "Antioquia",
}


@pytest.fixture(scope="module")
def served() -> Iterator[TestClient]:
    if not (ARTIFACTS_DIR / "car" / "model.json").exists():
        pytest.skip("no served bundle in artifacts/models")
    with TestClient(api_main.app) as client:
        yield client


@pytest.mark.parametrize("year", [1954, 2028])
def test_a_car_year_outside_the_catalogue_is_refused(served: TestClient, year: int) -> None:
    car = next(
        vertical
        for vertical in served.get("/catalog").json()["verticals"]
        if vertical["vehicle_type"] == "car"
    )
    # The published range is what makes these two the first refused years.
    assert car["model_year"] == {"min": 1955.0, "max": 2027.0}
    assert served.post("/predict", json={**MAZDA_3, "model_year": year}).status_code == 422


def test_a_motorcycle_displacement_on_a_car_is_refused(served: TestClient) -> None:
    assert served.post("/predict", json={**MAZDA_3, "engine_cc": 50}).status_code == 422


def test_the_displacement_moves_the_price(served: TestClient) -> None:
    small = served.post("/predict", json={**MAZDA_3, "engine_cc": 1600}).json()
    large = served.post("/predict", json={**MAZDA_3, "engine_cc": 2000}).json()
    assert large["band"]["estimate_cop"] > small["band"]["estimate_cop"]


def test_explain_names_the_displacement_it_was_given(served: TestClient) -> None:
    factors = served.post("/explain", json={**MAZDA_3, "engine_cc": 2000}).json()["factors"]
    labels = {factor["label"]["es"] for factor in factors}
    assert "Cilindrada" in labels


def test_an_asking_price_under_the_published_floor_is_refused(served: TestClient) -> None:
    car = next(
        vertical
        for vertical in served.get("/catalog").json()["verticals"]
        if vertical["vehicle_type"] == "car"
    )
    floor = int(car["asking_price_cop"]["min"])
    assert (
        served.post("/predict", json={**MAZDA_3, "asking_price_cop": floor - 1}).status_code == 422
    )
    assert served.post("/predict", json={**MAZDA_3, "asking_price_cop": floor}).status_code == 200


@pytest.mark.parametrize("brand", ["<script>", "Bajaj"])
def test_an_unknown_or_motorcycle_make_is_refused_on_a_car(served: TestClient, brand: str) -> None:
    assert served.post("/predict", json={**MAZDA_3, "brand": brand}).status_code == 422
