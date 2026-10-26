import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from autovalor.models.bundle import (
    BUNDLE_FORMAT,
    MANIFEST_NAME,
    BundleError,
    ServedModel,
    load_bundle,
    load_served_models,
    save_bundle,
)
from autovalor.models.dataset import split_listings
from autovalor.models.export import default_version, export
from autovalor.models.quantiles import LABEL_GATE
from autovalor.models.train import ModelResult, train_model

from .conftest import make_gold_frame


@pytest.fixture(scope="module")
def saved(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, pd.DataFrame, ModelResult]:
    """A bundle written from a cheap fit, the rows it was scored on, and the fit itself.

    The in-memory fit is kept so the tests can compare against it rather than against a
    recorded number.
    """
    cars = make_gold_frame(600, vehicle_type="car")
    dataset = split_listings(cars)
    result = train_model(dataset, "lightgbm", n_trials=0, explain=False)
    assert result.interval_model is not None
    assert result.interval is not None
    assert result.label is not None

    directory = tmp_path_factory.mktemp("bundle") / "car"
    save_bundle(
        directory,
        vehicle_type="car",
        version="test.1",
        point=result.model,  # type: ignore[arg-type]
        interval=result.interval_model,
        label=result.label,
        metrics={"mape": result.test_report.mape},
        lake={"rows": len(cars)},
        uncalibrated=result.interval_uncalibrated,
        metrics_temporal={"mape": 0.5, "n_test": 30.0},
    )
    return directory, dataset.test, result


def test_a_saved_bundle_predicts_what_the_fitted_one_did(
    saved: tuple[Path, pd.DataFrame, ModelResult],
) -> None:
    # The invariant the whole format exists for: a model that round-trips through disk has
    # to answer identically to the one that was measured. Anything less and the served
    # model is not the model the published MAPE describes.
    directory, rows, result = saved

    expected = result.model.predict_log_price(rows)
    actual = load_bundle(directory).predict_log_price(rows)

    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12)


def test_the_band_matches_the_fitted_one_too(
    saved: tuple[Path, pd.DataFrame, ModelResult],
) -> None:
    directory, rows, result = saved
    assert result.interval_model is not None

    expected = result.interval_model.predict_log_bounds(rows)
    actual = load_bundle(directory).predict_bounds(rows)

    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12)


def test_the_round_trip_is_exact(saved: tuple[Path, pd.DataFrame, ModelResult]) -> None:
    directory, rows, _ = saved
    first = load_bundle(directory).predict_log_price(rows)
    second = load_bundle(directory).predict_log_price(rows)

    np.testing.assert_array_equal(first, second)


def test_the_band_survives_the_round_trip(saved: tuple[Path, pd.DataFrame, ModelResult]) -> None:
    directory, rows, _ = saved
    loaded = load_bundle(directory)

    bounds = loaded.predict_bounds(rows)

    assert bounds.shape == (len(rows), 3)
    # Sorted per row by construction, and the calibration must have come back with it.
    assert (bounds[:, 0] <= bounds[:, 1]).all()
    assert (bounds[:, 1] <= bounds[:, 2]).all()
    assert loaded.interval.widening != 0.0


def test_the_label_decision_travels_with_the_model(
    saved: tuple[Path, pd.DataFrame, ModelResult],
) -> None:
    # Serving a model without its label decision would mean re-deriving the gate at request
    # time from numbers the API does not have.
    directory, _, _ = saved
    loaded = load_bundle(directory)

    assert loaded.label.n > 0
    assert 0.0 <= loaded.label.coverage <= 1.0
    assert isinstance(loaded.label.publishes_label, bool)


def test_saving_the_same_model_twice_writes_the_same_bytes(
    saved: tuple[Path, pd.DataFrame, ModelResult],
    tmp_path: Path,
) -> None:
    # gzip stores a timestamp in its header, so this used to differ in four bytes per file
    # and nothing else. The bundles are committed, so that was ~10 MB of new blobs in a
    # public repository's history every time an unchanged model was re-exported.
    directory, _, result = saved
    assert result.interval_model is not None and result.label is not None
    manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))

    save_bundle(
        tmp_path,
        vehicle_type=result.vehicle_type,
        version=manifest["version"],
        point=result.model,  # type: ignore[arg-type]
        interval=result.interval_model,
        label=result.label,
        metrics=manifest["metrics"],
        lake=manifest["lake"],
    )

    boosters = sorted(path.name for path in directory.glob("*.txt.gz"))
    assert boosters, "no boosters were written"
    for name in boosters:
        assert (tmp_path / name).read_bytes() == (directory / name).read_bytes(), name


def test_the_gate_the_decision_was_taken_against_travels_too(
    saved: tuple[Path, pd.DataFrame, ModelResult],
) -> None:
    # Read back from the manifest rather than from this process's constants, so an image
    # serving an older bundle publishes the rule that bundle was actually judged against.
    directory, _, _ = saved
    loaded = load_bundle(directory)

    assert loaded.label_gate == LABEL_GATE


def test_a_bundle_without_a_gate_still_loads(
    saved: tuple[Path, pd.DataFrame, ModelResult],
    tmp_path: Path,
) -> None:
    # The field is additive, so a bundle exported before it existed has to keep serving.
    directory, _, _ = saved
    for item in directory.iterdir():
        shutil.copy2(item, tmp_path / item.name)
    manifest = json.loads((tmp_path / MANIFEST_NAME).read_text(encoding="utf-8"))
    del manifest["label"]["gate"]
    (tmp_path / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    loaded = load_bundle(tmp_path)

    assert loaded.label_gate is None
    assert loaded.label.publishes_label == load_bundle(directory).label.publishes_label


def test_the_bundle_records_the_lake_it_came_from(
    saved: tuple[Path, pd.DataFrame, ModelResult],
) -> None:
    directory, _, _ = saved
    loaded = load_bundle(directory)

    assert loaded.version == "test.1"
    assert loaded.lake["rows"] == 600
    assert "mape" in loaded.metrics


def test_a_missing_bundle_says_how_to_build_one(tmp_path: Path) -> None:
    with pytest.raises(BundleError, match=r"make export-model"):
        load_bundle(tmp_path)


def test_an_unknown_format_is_refused_rather_than_guessed(
    saved: tuple[Path, pd.DataFrame, ModelResult], tmp_path: Path
) -> None:
    # Reading a newer bundle with an older loader would silently serve a model assembled
    # from the wrong pieces, which is worse than refusing.
    import json
    import shutil

    directory, _, _ = saved
    copy = tmp_path / "car"
    shutil.copytree(directory, copy)
    manifest = json.loads((copy / MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["format"] = BUNDLE_FORMAT + 1
    (copy / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(BundleError, match="bundle format"):
        load_bundle(copy)


def test_a_truncated_bundle_names_the_missing_file(
    saved: tuple[Path, pd.DataFrame, ModelResult], tmp_path: Path
) -> None:
    import shutil

    directory, _, _ = saved
    copy = tmp_path / "car"
    shutil.copytree(directory, copy)
    from autovalor.models.bundle import POINT_MODEL_NAME

    (copy / POINT_MODEL_NAME).unlink()

    with pytest.raises(BundleError, match=r"point\.txt\.gz"):
        load_bundle(copy)


def test_loading_an_empty_root_is_not_an_error(tmp_path: Path) -> None:
    # A development checkout without artifacts has to start and report itself unready,
    # rather than failing at import time.
    assert load_served_models(tmp_path / "nothing-here") == {}


def test_every_bundle_under_the_root_is_loaded(
    saved: tuple[Path, pd.DataFrame, ModelResult],
) -> None:
    directory, _, _ = saved

    models = load_served_models(directory.parent)

    assert set(models) == {"car"}
    assert isinstance(models["car"], ServedModel)


def test_the_version_names_the_lake_behind_it() -> None:
    # Two bundles from different lakes must not be able to claim the same version.
    assert default_version(11691).endswith(".11691")
    assert default_version(11691) != default_version(12000)


def test_export_writes_one_bundle_per_vertical(gold_duckdb: Path, tmp_path: Path) -> None:
    written = export(
        ("car",), directory=tmp_path, n_trials=0, version="dev", duckdb_path=gold_duckdb
    )

    assert [path.name for path in written] == [MANIFEST_NAME]
    assert load_bundle(tmp_path / "car").version == "dev"


def test_the_uncalibrated_band_is_recorded_next_to_the_calibrated_one(
    saved: tuple[Path, pd.DataFrame, ModelResult],
) -> None:
    # The whole case for conformalising is the gap between these two numbers, and the
    # methodology page shows them side by side. Recorded rather than measured once and
    # typed into a document.
    import json

    directory, _, result = saved
    manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert result.interval_uncalibrated is not None

    assert manifest["interval"]["uncalibrated_coverage"] == pytest.approx(
        result.interval_uncalibrated.coverage
    )
    assert manifest["interval"]["uncalibrated_mean_relative_width"] == pytest.approx(
        result.interval_uncalibrated.mean_relative_width
    )


def test_the_raw_band_is_narrower_than_the_calibrated_one(
    saved: tuple[Path, pd.DataFrame, ModelResult],
) -> None:
    # Which is the direction the conformal step corrects: the quantile models pin their
    # levels to the training rows, so the raw band comes out too narrow on new ones. A
    # calibrated band that is not wider than the raw one means the widening did nothing.
    _, rows, result = saved
    assert result.interval_model is not None

    raw = result.interval_model.predict_raw_log_bounds(rows)
    calibrated = result.interval_model.predict_log_bounds(rows)

    assert (raw[:, 2] - raw[:, 0]).mean() < (calibrated[:, 2] - calibrated[:, 0]).mean()


def test_the_temporal_measurement_travels_but_is_not_the_published_one(
    saved: tuple[Path, pd.DataFrame, ModelResult],
) -> None:
    directory, _, _ = saved
    loaded = load_bundle(directory)

    assert loaded.metrics_temporal is not None
    assert loaded.metrics_temporal["mape"] == pytest.approx(0.5)
    # The served model is the grouped-random fit, so the published MAPE is the one in
    # `metrics`. A reader that confused the two would quote a number for a model nobody
    # exported.
    assert loaded.metrics["mape"] != loaded.metrics_temporal["mape"]


def test_a_bundle_without_the_new_fields_still_loads(
    saved: tuple[Path, pd.DataFrame, ModelResult], tmp_path: Path
) -> None:
    # The service and the bundle are deployed separately, so a loader that required the
    # fields this format added would turn an ordinary deploy order into an outage.
    import json
    import shutil

    directory, rows, _ = saved
    copy = tmp_path / "car"
    shutil.copytree(directory, copy)
    manifest = json.loads((copy / MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["format"] = 1
    manifest.pop("metrics_temporal")
    manifest["label"].pop("failure_codes")
    manifest["interval"].pop("uncalibrated_coverage")
    manifest["interval"].pop("uncalibrated_mean_relative_width")
    (copy / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    loaded = load_bundle(copy)

    assert loaded.metrics_temporal is None
    assert loaded.label.failure_codes == ()
    assert len(loaded.predict_log_price(rows)) == len(rows)


def test_the_label_failures_travel_as_text_and_as_codes(
    saved: tuple[Path, pd.DataFrame, ModelResult],
) -> None:
    # Both, saying the same thing: the text is what shipped and what an older reader looks
    # for, the codes are what a reader translating the sentence needs.
    import json

    directory, _, _ = saved
    manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))

    assert len(manifest["label"]["failures"]) == len(manifest["label"]["failure_codes"])
    for text, code in zip(
        manifest["label"]["failures"], manifest["label"]["failure_codes"], strict=True
    ):
        assert code["message"] == text
        assert 0.0 <= code["value"] <= 10.0
        assert 0.0 <= code["limit"] <= 1.0


def test_export_records_the_baseline_it_beats(gold_duckdb: Path, tmp_path: Path) -> None:
    # "LightGBM reduces the error by N points" has to be a figure the site reads, not a
    # sentence somebody typed, so the reference is measured on the same partition and
    # written next to the served model's own error.
    export(
        ("car",),
        directory=tmp_path,
        n_trials=0,
        version="dev",
        duckdb_path=gold_duckdb,
        temporal=False,
    )

    loaded = load_bundle(tmp_path / "car")

    assert loaded.metrics["baseline_mape"] > 0.0
    assert loaded.metrics["baseline_r2_log"] <= 1.0
    # Skipped on request, so the field says "not measured" rather than carrying a stale
    # number from some earlier run.
    assert loaded.metrics_temporal is None


def test_a_lake_too_young_for_a_temporal_split_still_exports(
    gold_duckdb: Path, tmp_path: Path
) -> None:
    # The temporal partition is an extra measurement. A lake that cannot support one has
    # to produce a bundle with the field null, not a failed export.
    export(
        ("car",),
        directory=tmp_path,
        n_trials=0,
        version="dev",
        duckdb_path=gold_duckdb,
        temporal=True,
    )

    assert load_bundle(tmp_path / "car").metrics_temporal is None
