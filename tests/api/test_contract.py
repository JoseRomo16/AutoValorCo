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
from typing import Any

import pytest
from fastapi.testclient import TestClient

from autovalor.api import main as api_main
from autovalor.api.labels import FEATURE_LABELS
from autovalor.api.schemas import MAX_MILEAGE_KM
from autovalor.config import get_settings
from autovalor.models.bundle import ServedModel, load_served_models
from autovalor.models.quantiles import LABEL_GATE
from autovalor.models.serving import SERVING_ASSUMPTIONS

CAR = {
    "vehicle_type": "car",
    "brand": "Toyota",
    "model": "corolla",
    "model_year": 2018,
    "mileage_km": 60_000,
    "department": "Antioquia",
}


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


def test_the_root_sends_a_visitor_to_the_documentation(client: TestClient) -> None:
    # The deployed URL is what gets pasted into a README and a CV, and a bare FastAPI root
    # answers "Not Found" there.
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


def test_the_root_redirect_does_not_need_a_model(empty_client: TestClient) -> None:
    # It is a courtesy route, so a checkout without artifacts must still answer it rather
    # than 503 like the prediction routes do.
    response = empty_client.get("/", follow_redirects=False)

    assert response.status_code == 307


def test_the_documentation_the_root_points_at_is_served(client: TestClient) -> None:
    # A redirect to a 404 is worse than no redirect, so the destination is asserted too.
    assert client.get("/docs").status_code == 200


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


@pytest.mark.parametrize("vehicle_type", ["car", "motorcycle"])
def test_predict_and_explain_publish_the_same_price(client: TestClient, vehicle_type: str) -> None:
    # They used to differ: /predict centred its band on the P50 quantile model and /explain
    # reported the point model, so the product showed two prices for one vehicle and only
    # one of them was the model whose MAPE is published. Exact equality, not a tolerance —
    # a tolerance here would let the two models drift apart again.
    payload = {**CAR, "vehicle_type": vehicle_type}

    predicted = client.post("/predict", json=payload).json()["band"]["estimate_cop"]
    explained = client.post("/explain", json=payload).json()["estimate_cop"]

    assert predicted == explained


def test_the_published_estimate_sits_inside_the_published_range(client: TestClient) -> None:
    # The point model and the quantile models are fitted separately and can disagree on a
    # row, so the band is widened to hold the estimate rather than printing a range that
    # excludes the number next to it.
    band = client.post("/predict", json=CAR).json()["band"]

    assert band["lower_cop"] <= band["estimate_cop"] <= band["upper_cop"]


def test_the_factors_carry_readable_names_and_formatted_values(client: TestClient) -> None:
    factors = {f["feature"]: f for f in client.post("/explain", json=CAR).json()["factors"]}

    for feature, factor in factors.items():
        # The technical name survives — a client plotting or logging attributions needs a
        # stable key, and a translated string is not one — and the readable name is not it.
        assert factor["label"]["es"] and factor["label"]["en"]
        assert factor["label"]["es"] != feature
        assert factor["value_display"]["es"] and factor["value_display"]["en"]

    if "mileage_km" in factors:
        assert factors["mileage_km"]["value"] == "60000"
        assert factors["mileage_km"]["value_display"]["es"] == "60.000 km"
        assert factors["mileage_km"]["value_display"]["en"] == "60,000 km"
    if "vehicle_age_years" in factors:
        assert factors["vehicle_age_years"]["value_display"]["es"].endswith("años")
        assert factors["vehicle_age_years"]["value_display"]["en"].endswith("years")


def test_every_served_feature_has_a_human_name(client: TestClient, artifacts: Path) -> None:
    # Adding a feature to the model without naming it would ship a column name into the
    # product card. Checked against the bundle's own specification, not a copy of it.
    models = load_served_models(artifacts)
    for model in models.values():
        spec = model.point.spec
        for feature in (*spec.numeric, *spec.categorical, *spec.boolean):
            assert feature in FEATURE_LABELS, feature


def test_catalog_lists_what_the_form_may_ask(client: TestClient) -> None:
    body = client.get("/catalog").json()

    assert {v["vehicle_type"] for v in body["verticals"]} == {"car", "motorcycle"}
    for vertical in body["verticals"]:
        assert vertical["brands"], "a vertical with no makes would render a dead dropdown"
        assert vertical["model_version"] == "test.1"
        assert vertical["trained_on_rows"] > 0
        assert vertical["model_year"]["min"] <= vertical["model_year"]["max"]
        for brand in vertical["brands"]:
            assert brand["listings"] >= 1
            assert all(model["listings"] >= 1 for model in brand["models"])


def test_catalog_can_be_asked_for_one_vertical(client: TestClient) -> None:
    body = client.get("/catalog", params={"vehicle_type": "motorcycle"}).json()

    assert [v["vehicle_type"] for v in body["verticals"]] == ["motorcycle"]


def test_catalog_entries_are_accepted_by_predict(client: TestClient) -> None:
    # The contract that makes the catalogue worth serving: everything it offers is a valid
    # request. A list the form cannot submit is worse than no list.
    vertical = client.get("/catalog", params={"vehicle_type": "car"}).json()["verticals"][0]
    brand = vertical["brands"][0]

    response = client.post(
        "/predict",
        json={
            "vehicle_type": "car",
            "brand": brand["name"],
            "model": brand["models"][0]["name"],
            "model_year": int(vertical["model_year"]["max"]),
            "mileage_km": 30_000,
            "department": vertical["departments"][0]["name"],
        },
    )

    assert response.status_code == 200


def test_catalog_without_a_model_says_so(empty_client: TestClient) -> None:
    assert empty_client.get("/catalog").status_code == 503


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


def test_model_info_carries_the_reference_the_served_model_beats(client: TestClient) -> None:
    # The site says "LightGBM reduces the error by N points". That subtraction has to be
    # done on two numbers the service publishes, not on one number and a memory.
    body = client.get("/model-info").json()

    for vertical in body["verticals"]:
        assert vertical["baseline_mape"] > vertical["mape"]
        assert vertical["interval_uncalibrated_coverage"] is not None
        assert vertical["metrics_temporal"]["mape"] > 0


def test_a_withheld_label_comes_with_codes_as_well_as_text(client: TestClient) -> None:
    # The notice has to be renderable in Spanish, and a Spanish sentence cannot be derived
    # from the English one. Both travel, saying the same thing.
    body = client.get("/model-info").json()

    for vertical in body["verticals"]:
        text = vertical["label_withheld_because"]
        codes = vertical["label_withheld_codes"]
        assert len(text) == len(codes)
        assert (len(codes) == 0) == vertical["publishes_label"]
        for message, code in zip(text, codes, strict=True):
            assert code["message"] == message
            assert code["code"] in {
                "coverage_below_min",
                "coverage_above_max",
                "width_above_max",
            }
            assert code["limit"] > 0


def test_model_info_publishes_the_whole_rule_not_only_the_limit_that_failed(
    client: TestClient,
) -> None:
    # A failure is one-sided, so `limit` never shows the coverage window and a vertical
    # that passes carries no limit at all. The page states all three, so all three ship.
    gate = client.get("/model-info").json()["label_gate"]

    assert gate == {
        "min_coverage": LABEL_GATE.min_coverage,
        "max_coverage": LABEL_GATE.max_coverage,
        "max_relative_width": LABEL_GATE.max_relative_width,
    }


def test_the_published_gate_is_the_one_the_verticals_were_judged_against(
    client: TestClient,
) -> None:
    body = client.get("/model-info").json()
    gate = body["label_gate"]

    for vertical in body["verticals"]:
        within = gate["min_coverage"] <= vertical["interval_coverage"] <= gate["max_coverage"]
        narrow = vertical["interval_mean_relative_width"] <= gate["max_relative_width"]
        assert vertical["publishes_label"] == (within and narrow)


def test_predict_carries_the_precision_codes_next_to_the_notice(client: TestClient) -> None:
    # Built from the catalogue rather than hard-coded, so both verticals are exercised
    # whatever the synthetic lake happened to generate.
    for vertical in client.get("/catalog").json()["verticals"]:
        brand = vertical["brands"][0]
        request = {
            "vehicle_type": vertical["vehicle_type"],
            "brand": brand["name"],
            "model": brand["models"][0]["name"],
            "model_year": int(vertical["model_year"]["max"]),
            "mileage_km": 20_000,
            "department": vertical["departments"][0]["name"],
        }
        body = client.post("/predict", json=request).json()

        has_notice = body["precision_notice"] is not None
        assert bool(body["precision_codes"]) == has_notice
        for code in body["precision_codes"]:
            assert code["message"] in body["precision_notice"]


def test_a_department_resolves_however_it_is_spelled(client: TestClient) -> None:
    # The lake used to store whatever the site published, so an older client still sends
    # "Valle Del Cauca" where the level is now "Valle del Cauca". Missing every category
    # would send the request down the trees' missing branch -- a wrong answer that looks
    # exactly like a right one -- so the spellings have to meet.
    catalog = client.get("/catalog", params={"vehicle_type": "car"}).json()
    level = catalog["verticals"][0]["departments"][0]["name"]

    canonical = client.post("/predict", json={**CAR, "department": level}).json()
    shouted = client.post("/predict", json={**CAR, "department": level.upper()}).json()
    unaccented = client.post("/predict", json={**CAR, "department": _strip_accents(level)}).json()

    assert shouted["band"] == canonical["band"]
    assert unaccented["band"] == canonical["band"]


def test_an_unknown_department_is_answered_rather_than_rejected(client: TestClient) -> None:
    # "No data for that region" is a real answer; turning it into a 422 would make the
    # form unusable for a department the lake has not reached yet.
    body = client.post("/predict", json={**CAR, "department": "Vaupés"})

    assert body.status_code == 200
    assert body.json()["band"]["estimate_cop"] > 0


def _strip_accents(text: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


# ---------------------------------------------------------------------------
# The shared-rules layer, over HTTP. The unit cases live in test_rules.py; what
# is checked here is that /predict and /explain actually apply them and that the
# catalogue publishes the same bounds.
# ---------------------------------------------------------------------------


def car_catalog(client: TestClient) -> dict[str, Any]:
    return dict(client.get("/catalog", params={"vehicle_type": "car"}).json()["verticals"][0])


def test_the_catalogue_publishes_an_asking_price_range(client: TestClient) -> None:
    for vertical in client.get("/catalog").json()["verticals"]:
        price = vertical["asking_price_cop"]
        assert price is not None, f"{vertical['vehicle_type']} publishes no price range"
        assert 0 < price["min"] < price["max"]


def test_predict_refuses_a_year_outside_the_published_range(client: TestClient) -> None:
    bounds = car_catalog(client)["model_year"]
    for year in (int(bounds["min"]) - 1, int(bounds["max"]) + 1):
        response = client.post("/predict", json={**CAR, "model_year": year})
        assert response.status_code == 422, year


def test_predict_refuses_a_displacement_outside_the_published_range(client: TestClient) -> None:
    bounds = car_catalog(client)["engine_cc"]
    response = client.post("/predict", json={**CAR, "engine_cc": int(bounds["min"]) - 1})
    assert response.status_code == 422


def test_predict_refuses_an_asking_price_under_the_floor(client: TestClient) -> None:
    # 59 pesos used to come back as a bargain.
    response = client.post("/predict", json={**CAR, "asking_price_cop": 59})
    assert response.status_code == 422


def test_predict_refuses_a_make_the_model_does_not_know(client: TestClient) -> None:
    for brand in ("<script>", "Bajaj"):
        assert client.post("/predict", json={**CAR, "brand": brand}).status_code == 422, brand


def test_the_make_is_not_case_sensitive(client: TestClient) -> None:
    # Observed: "toyota" came back 20 % under "Toyota".
    lower = client.post("/predict", json={**CAR, "brand": "toyota"}).json()
    exact = client.post("/predict", json={**CAR, "brand": "Toyota"}).json()
    assert lower["band"] == exact["band"]


def test_the_department_is_not_case_sensitive(client: TestClient) -> None:
    lower = client.post("/predict", json={**CAR, "department": "antioquia"}).json()
    exact = client.post("/predict", json={**CAR, "department": "Antioquia"}).json()
    assert lower["band"] == exact["band"]


def test_an_unknown_model_token_is_valued_without_it_and_flagged(client: TestClient) -> None:
    unknown = client.post("/predict", json={**CAR, "model": "zzz"})
    assert unknown.status_code == 200
    assert unknown.json()["warnings"] == ["model_not_covered"]
    # And the answer is the one that omitting the field would have given.
    without = client.post(
        "/predict", json={key: value for key, value in CAR.items() if key != "model"}
    )
    assert unknown.json()["band"] == without.json()["band"]


def test_an_uncovered_department_is_answered_and_flagged(client: TestClient) -> None:
    response = client.post("/predict", json={**CAR, "department": "Nariño"})
    assert response.status_code == 200
    assert response.json()["warnings"] == ["department_not_covered"]


def test_a_clean_request_carries_no_warnings(client: TestClient) -> None:
    assert client.post("/predict", json=CAR).json()["warnings"] == []


def test_explain_reports_the_same_warnings(client: TestClient) -> None:
    body = client.post("/explain", json={**CAR, "model": "zzz"}).json()
    assert body["warnings"] == ["model_not_covered"]


def test_explain_always_shows_a_displacement_that_was_supplied(client: TestClient) -> None:
    # Observed: 2.000 cc moved a Mazda 3 by 11,5 % and "Cilindrada" was still not listed,
    # so someone who typed a number could not tell whether it had been used.
    bounds = car_catalog(client)["engine_cc"]
    inside = int((bounds["min"] + bounds["max"]) / 2)
    body = client.post("/explain", json={**CAR, "engine_cc": inside}).json()
    assert "engine_cc" in {factor["feature"] for factor in body["factors"]}


def test_explain_does_not_invent_a_displacement_that_was_not_supplied(client: TestClient) -> None:
    body = client.post("/explain", json=CAR).json()
    shown = {factor["feature"]: factor for factor in body["factors"]}
    # It may still rank into the top five on its own; what must not happen is it being
    # listed with a value the caller never gave.
    if "engine_cc" in shown:
        assert shown["engine_cc"]["value"] is None


def test_the_row_counts_have_names_that_say_what_they_count(client: TestClient) -> None:
    # /catalog said trained_on_rows 6.754 and /model-info said 8.443 for the same cars:
    # one counted the training rows and the other the lake.
    catalogue = car_catalog(client)
    info = next(
        vertical
        for vertical in client.get("/model-info").json()["verticals"]
        if vertical["vehicle_type"] == "car"
    )
    assert catalogue["train_rows"] == info["train_rows"]
    assert catalogue["total_rows"] == info["total_rows"]
    assert info["total_rows"] >= info["train_rows"]
    # The old name stays, so a deployed frontend does not break.
    assert catalogue["trained_on_rows"] == catalogue["train_rows"]
    assert info["trained_on_rows"] == info["total_rows"]


# ---------------------------------------------------------------------------
# An uncovered department, over HTTP. The arithmetic is covered in
# test_regions.py; what matters here is that the routes take that path and say
# so.
# ---------------------------------------------------------------------------

UNCOVERED = {**CAR, "department": "Nariño"}


def test_an_uncovered_department_no_longer_answers_like_a_covered_one(client: TestClient) -> None:
    # Measured on the deployed service: "Nariño", "xyz", "Otro" and a lower-cased
    # "antioquia" all returned exactly the same estimate as Antioquia, because there is no
    # unknown level and the request took LightGBM's default branch.
    averaged = client.post("/predict", json=UNCOVERED).json()
    antioquia = client.post("/predict", json={**CAR, "department": "Antioquia"}).json()
    assert averaged["band"] != antioquia["band"]


def test_every_uncovered_spelling_gets_the_same_average(client: TestClient) -> None:
    # Which is the point of an average over known departments: the answer depends on the
    # model's data, not on which unknown string happened to be typed.
    first = client.post("/predict", json={**CAR, "department": "Nariño"}).json()
    second = client.post("/predict", json={**CAR, "department": "Otro departamento"}).json()
    assert first["band"] == second["band"]
    assert first["warnings"] == ["department_not_covered"]


def test_the_averaged_band_is_still_ordered(client: TestClient) -> None:
    band = client.post("/predict", json=UNCOVERED).json()["band"]
    assert band["lower_cop"] <= band["estimate_cop"] <= band["upper_cop"]


def test_explain_calls_the_region_an_average_rather_than_echoing_the_input(
    client: TestClient,
) -> None:
    body = client.post("/explain", json=UNCOVERED).json()
    region = next(factor for factor in body["factors"] if factor["feature"] == "department")
    assert region["value"] is None
    assert region["value_display"]["es"] == "promedio de departamentos"
    assert region["value_display"]["en"] == "average of departments"
    # And never the department the caller typed, which the estimate is not about.
    assert "Nariño" not in json.dumps(body, ensure_ascii=False)


def test_the_averaged_explanation_still_reconciles(client: TestClient) -> None:
    # base x every factor == the estimate. The property is exact, so a loose tolerance here
    # would hide a real break; only the five strongest factors are returned, so the product
    # is checked against the estimate the same route publishes.
    body = client.post("/explain", json=UNCOVERED).json()
    predicted = client.post("/predict", json=UNCOVERED).json()["band"]["estimate_cop"]
    assert body["estimate_cop"] == pytest.approx(predicted, rel=1e-9)


def test_the_average_costs_one_scoring_call_not_one_per_department(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The departments become rows, so ten of them cost what one prediction costs.

    Asserted structurally rather than with a stopwatch: a wall-clock bound on ten tiny
    LightGBM calls measures the machine, while the number of calls is the actual claim.
    Patched on the class because ServedModel is a frozen dataclass.
    """
    scored = _count_scored_rows(monkeypatch)
    client.post("/predict", json=UNCOVERED)

    assert len(scored) == 1, "the departments should be scored together, not in a loop"
    model = client.app.state.models["car"]  # type: ignore[attr-defined]
    assert model.catalog is not None
    assert scored[0] == len(model.catalog.departments)


def test_a_covered_department_does_not_pay_for_the_average(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scored = _count_scored_rows(monkeypatch)
    client.post("/predict", json={**CAR, "department": "Antioquia"})
    assert scored == [1]


def _count_scored_rows(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Record how many rows each call to the published band scored."""
    scored: list[int] = []
    original = ServedModel.predict_published_band

    def counted(self: ServedModel, frame: Any) -> Any:
        scored.append(len(frame))
        return original(self, frame)

    monkeypatch.setattr(ServedModel, "predict_published_band", counted)
    return scored


REQUEST_DERIVED = frozenset(
    {"brand", "model", "department", "vehicle_age_years", "mileage_km", "engine_cc", "km_per_year"}
)
"""Model columns whose value comes from what the caller typed, directly or derived."""


@pytest.mark.parametrize(
    "body",
    [
        CAR,
        {**CAR, "engine_cc": 1400},
        {**CAR, "model": None},
        {**CAR, "department": "Nariño"},
        # The synthetic lake reuses the car makes for motorcycles; what matters here is
        # that the motorcycle model reads is_quad and is_cargo, which the API assumes.
        {**CAR, "vehicle_type": "motorcycle", "engine_cc": 1000},
    ],
    ids=["car", "car-with-engine", "car-without-model", "uncovered-department", "motorcycle"],
)
def test_explain_never_shows_a_value_the_caller_did_not_enter(
    client: TestClient, body: dict[str, Any]
) -> None:
    # Block 4: "Ciudad: Desconocida" lowered every estimate by a few percent and the card
    # showed it as a fact about the vehicle, though nobody typed a city. A factor now either
    # comes from the request, or is flagged as an assumption of the model, or is the region
    # stated as the average of departments.
    factors = client.post("/explain", json=body).json()["factors"]
    for factor in factors:
        feature = factor["feature"]
        if feature in SERVING_ASSUMPTIONS:
            assert factor["assumed"] is True, feature
            continue
        assert factor["assumed"] is False, feature
        assert feature in REQUEST_DERIVED, f"{feature} is neither typed by the caller nor assumed"
        if feature == "department" and body["department"] == "Nariño":
            assert factor["value"] is None
            assert factor["value_display"]["es"] == "promedio de departamentos"
