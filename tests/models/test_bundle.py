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
