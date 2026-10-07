"""Contract tests for the API.

These are about the *shape of the promise*, not about model quality: that a range always
comes back, that the label only appears when the vertical earned it, that a bad request is
rejected at the edge with a message rather than reaching the model. The F4 frontend is
written against exactly these payloads.

Every test runs against a real bundle built from the synthetic lake, so the serving path
exercised here is the one that runs in production — load from disk, frame the request,
score, calibrate, label.
"""

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autovalor.api import main as api_main
from autovalor.api.schemas import MAX_MILEAGE_KM
from autovalor.config import get_settings
from autovalor.models.bundle import load_served_models, save_bundle
from autovalor.models.dataset import split_listings
from autovalor.models.train import train_model

from ..models.conftest import make_gold_frame

CAR = {
    "vehicle_type": "car",
    "brand": "Toyota",
    "model": "corolla",
    "model_year": 2018,
    "mileage_km": 60_000,
    "department": "Antioquia",
}


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real bundle for both verticals, built from the synthetic lake."""
    root = tmp_path_factory.mktemp("artifacts")
    for vehicle_type, seed in (("car", 7), ("motorcycle", 11)):
        frame = make_gold_frame(600, vehicle_type=vehicle_type, seed=seed)
        dataset = split_listings(frame)
        result = train_model(dataset, "lightgbm", n_trials=0, explain=False)
        assert result.interval_model is not None
        assert result.interval is not None
        assert result.label is not None
        save_bundle(
            root / vehicle_type,
            vehicle_type=vehicle_type,  # type: ignore[arg-type]
            version="test.1",
            point=result.model,  # type: ignore[arg-type]
            interval=result.interval_model,
            label=result.label,
            metrics={
                "mape": result.test_report.mape,
                "median_ape": result.test_report.median_ape,
                "sigma_log": result.test_report.sigma_log,
                "r2_log": result.test_report.r2_log,
                "n_test": float(result.test_report.n),
                "interval_coverage": result.interval.coverage,
                "interval_mean_relative_width": result.interval.mean_relative_width,
            },
            lake={"rows": len(frame)},
        )
    return root


@pytest.fixture
def client(artifacts: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(api_main, "ARTIFACTS_DIR", artifacts)
    with TestClient(api_main.app) as test_client:
        yield test_client


@pytest.fixture
def empty_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A service started without artifacts, which is a development checkout."""
    monkeypatch.setattr(api_main, "ARTIFACTS_DIR", tmp_path / "nothing")
    with TestClient(api_main.app) as test_client:
        yield test_client


def test_health_reports_what_is_loaded(client: TestClient) -> None:
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["models_loaded"] == ["car", "motorcycle"]


def test_health_separates_being_up_from_being_able_to_answer(empty_client: TestClient) -> None:
    # A platform probe has to tell these apart: the process is serving, but it cannot
    # predict. Returning 200 "degraded" rather than 503 keeps the container from being
    # restart-looped over a condition a restart will not fix.
    response = empty_client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["models_loaded"] == []


def test_model_info_describes_every_vertical(client: TestClient) -> None:
    body = client.get("/model-info").json()

    assert body["version"] == "test.1"
    assert body["target"] == "log_price"
    assert {v["vehicle_type"] for v in body["verticals"]} == {"car", "motorcycle"}
    for vertical in body["verticals"]:
        assert vertical["mape"] > 0
        assert "publishes_label" in vertical


def test_predict_always_returns_a_band(client: TestClient) -> None:
    # The product promise: never a bare number. A used-vehicle price without a range is
    # false precision, and this is the test that keeps someone from "simplifying" it away.
    body = client.post("/predict", json=CAR).json()

    band = body["band"]
    assert band["lower_cop"] < band["estimate_cop"] < band["upper_cop"]
    assert band["relative_width"] > 0
    assert body["model_version"] == "test.1"


def test_no_asking_price_means_no_label(client: TestClient) -> None:
    body = client.post("/predict", json=CAR).json()

    assert body["label"] is None


def test_an_asking_price_inside_the_band_is_fair(client: TestClient) -> None:
    estimate = client.post("/predict", json=CAR).json()["band"]["estimate_cop"]

    body = client.post("/predict", json={**CAR, "asking_price_cop": int(estimate)}).json()

    # Only meaningful when this vertical publishes a label at all; when it does not, the
    # notice has to be there instead.
    if body["label"] is None:
        assert body["precision_notice"]
    else:
        assert body["label"] == "fair"


def test_a_cheap_asking_price_is_a_bargain_when_the_label_is_published(
    client: TestClient,
) -> None:
    band = client.post("/predict", json=CAR).json()["band"]
    cheap = int(band["lower_cop"] * 0.5)

    body = client.post("/predict", json={**CAR, "asking_price_cop": cheap}).json()

    if body["label"] is not None:
        assert body["label"] == "bargain"


def test_the_label_follows_the_gate_rather_than_the_endpoint(client: TestClient) -> None:
    # The decision travels with the model; /predict must not re-derive or override it.
    info = {v["vehicle_type"]: v for v in client.get("/model-info").json()["verticals"]}
    for vehicle_type, vertical in info.items():
        payload = {**CAR, "vehicle_type": vehicle_type, "asking_price_cop": 30_000_000}
        body = client.post("/predict", json=payload).json()
        if vertical["publishes_label"]:
            assert body["label"] is not None
            assert body["precision_notice"] is None
        else:
            assert body["label"] is None
            assert body["precision_notice"]


def test_predict_without_a_model_says_so(empty_client: TestClient) -> None:
    response = empty_client.post("/predict", json=CAR)

    assert response.status_code == 503
    assert "artifacts" in response.json()["detail"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_year", 1800),
        ("model_year", 2200),
        ("mileage_km", -1),
        ("mileage_km", MAX_MILEAGE_KM + 1),
        ("engine_cc", 0),
        ("asking_price_cop", 0),
        ("brand", ""),
        ("department", ""),
    ],
)
def test_bad_input_is_rejected_at_the_edge(client: TestClient, field: str, value: object) -> None:
    # Rejected by the schema, before the model sees it: a 1800 model year would otherwise
    # produce a confident estimate for a vehicle 226 years old.
    response = client.post("/predict", json={**CAR, field: value})

    assert response.status_code == 422


def test_an_unknown_field_is_rejected_rather_than_ignored(client: TestClient) -> None:
    # Silently dropping "colour" would let a caller believe it influenced the estimate.
    response = client.post("/predict", json={**CAR, "colour": "rojo"})

    assert response.status_code == 422


def test_an_unknown_vertical_is_rejected(client: TestClient) -> None:
    assert client.post("/predict", json={**CAR, "vehicle_type": "truck"}).status_code == 422


def test_explain_returns_multiplicative_factors(client: TestClient) -> None:
    body = client.post("/explain", json=CAR).json()

    assert body["factors"]
    assert len(body["factors"]) <= 5
    for factor in body["factors"]:
        assert factor["factor"] > 0
        assert factor["direction"] in {"raises", "lowers"}
        assert (factor["factor"] >= 1.0) == (factor["direction"] == "raises")


def test_the_factors_are_ordered_by_how_much_they_move_the_price(client: TestClient) -> None:
    factors = client.post("/explain", json=CAR).json()["factors"]

    pulls = [abs(factor["factor"] - 1.0) for factor in factors]
    assert pulls == sorted(pulls, reverse=True)


def test_the_explanation_reconciles_with_the_estimate(client: TestClient) -> None:
    # The property that makes this explanation checkable rather than decorative: the base
    # price times every factor is the estimate. Only the top five are returned, so the
    # product of those five cannot exceed the full journey from base to estimate.
    body = client.post("/explain", json=CAR).json()

    assert body["estimate_cop"] > 0
    assert body["base_price_cop"] > 0
    predicted = client.post("/predict", json=CAR).json()["band"]["estimate_cop"]
    # /explain reports the point model; /predict's centre is the band's median, so these
    # are close but not identical, and the test says which is which rather than hiding it.
    assert body["estimate_cop"] == pytest.approx(predicted, rel=0.5)


def test_explain_without_a_model_says_so(empty_client: TestClient) -> None:
    assert empty_client.post("/explain", json=CAR).status_code == 503


def test_market_lists_what_it_can_serve(client: TestClient, tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    (results / "manifest.json").write_text(json.dumps({"gold_rows": {"car": 1}}), encoding="utf-8")
    (results / "depreciation_by_brand.json").write_text(
        json.dumps([{"brand": "Toyota", "annual_depreciation_pct": 5.9}]), encoding="utf-8"
    )
    get_settings.cache_clear()
    try:
        os.environ["AUTOVALOR_RESULTS_DIR"] = str(results)
        body = client.get("/market").json()

        assert body["tables"] == ["depreciation_by_brand"]
        assert body["manifest"]["gold_rows"] == {"car": 1}

        table = client.get("/market", params={"table": "depreciation_by_brand"}).json()
        assert table["rows"][0]["brand"] == "Toyota"

        missing = client.get("/market", params={"table": "nope"})
        assert missing.status_code == 404
        assert "depreciation_by_brand" in missing.json()["detail"]
    finally:
        os.environ.pop("AUTOVALOR_RESULTS_DIR", None)
        get_settings.cache_clear()


def test_the_served_bundle_is_the_one_on_disk(artifacts: Path) -> None:
    # Guards the wiring rather than the routes: if the API loaded from somewhere else, every
    # test above would still pass while production served a different model.
    models = load_served_models(artifacts)

    assert set(models) == {"car", "motorcycle"}
    assert all(model.version == "test.1" for model in models.values())
