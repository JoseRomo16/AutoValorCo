import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from autovalor.analysis import figures
from autovalor.analysis.depreciation import depreciation_at_ages, depreciation_curves
from autovalor.analysis.export import (
    FLOAT_DECIMALS,
    MANIFEST_NAME,
    Manifest,
    now_utc,
    write_manifest,
    write_table,
)
from autovalor.analysis.mileage import mileage_effects
from autovalor.analysis.regional import regional_effects


@pytest.fixture
def manifest() -> Manifest:
    return Manifest(
        generated_at=now_utc(),
        gold_rows={"car": 7639, "motorcycle": 4052},
        capture_span_days=5.54,
        detail_coverage={"car": 0.0, "motorcycle": 0.5676},
        thresholds={"min_brand_listings": 200},
    )


def test_a_table_is_written_in_both_formats(tmp_path: Path, manifest: Manifest) -> None:
    frame = pd.DataFrame({"brand": ["Toyota"], "rate": [5.8926123456]})

    write_table(frame, "rates", output_dir=tmp_path, manifest=manifest)

    assert (tmp_path / "rates.csv").exists()
    assert (tmp_path / "rates.json").exists()
    assert set(manifest.files) == {"rates.csv", "rates.json"}


def test_floats_are_rounded_so_the_diffs_stay_readable(tmp_path: Path, manifest: Manifest) -> None:
    # These files live in git; an unrounded float changes in its last decimal every time
    # the lake grows by a row, and every commit would look like a result moved.
    frame = pd.DataFrame({"rate": [5.892612345678]})

    write_table(frame, "rates", output_dir=tmp_path, manifest=manifest)

    written = json.loads((tmp_path / "rates.json").read_text(encoding="utf-8"))
    assert written[0]["rate"] == pytest.approx(round(5.892612345678, FLOAT_DECIMALS))


def test_a_missing_value_becomes_null_rather_than_nan(tmp_path: Path, manifest: Manifest) -> None:
    # NaN is not valid JSON, and a consumer can branch on null.
    frame = pd.DataFrame({"half_life": [np.nan, 7.5]})

    write_table(frame, "lives", output_dir=tmp_path, manifest=manifest)

    written = json.loads((tmp_path / "lives.json").read_text(encoding="utf-8"))
    assert written[0]["half_life"] is None
    assert written[1]["half_life"] == pytest.approx(7.5)


def test_the_manifest_records_what_the_numbers_were_measured_on(
    tmp_path: Path, manifest: Manifest
) -> None:
    write_table(pd.DataFrame({"a": [1]}), "a", output_dir=tmp_path, manifest=manifest)

    path = write_manifest(manifest, output_dir=tmp_path)

    written = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == MANIFEST_NAME
    assert written["gold_rows"] == {"car": 7639, "motorcycle": 4052}
    assert written["capture_span_days"] == pytest.approx(5.54)
    assert written["files"] == ["a.csv", "a.json"]


def test_the_timestamp_has_no_microseconds() -> None:
    assert "." not in now_utc()


def test_the_manifest_says_what_could_not_be_produced(tmp_path: Path, manifest: Manifest) -> None:
    # An absent result and a result nobody asked for look identical in a directory, so the
    # reason an analysis was skipped has to be written down somewhere.
    manifest.skipped["price_index.car"] = "the lake spans 5.5 days, under the 180 needed"

    written = json.loads(write_manifest(manifest, output_dir=tmp_path).read_text(encoding="utf-8"))

    assert "under the 180" in written["skipped"]["price_index.car"]


def test_every_figure_renders(tmp_path: Path, cars: pd.DataFrame) -> None:
    # A smoke test rather than a pixel comparison: what breaks a chart in practice is a
    # column that is not there or an interval that comes out backwards, and both of those
    # raise here.
    curves = depreciation_curves(cars, vehicle_type="car")
    retained = depreciation_at_ages(curves)
    effects = mileage_effects(cars, vehicle_type="car")
    regions = regional_effects(cars, vehicle_type="car")

    written = [
        figures.depreciation_figure(curves, tmp_path / "depreciation.png"),
        figures.retained_value_figure(retained, tmp_path / "retained.png"),
        figures.mileage_figure(effects, tmp_path / "mileage.png"),
        figures.regional_figure(regions, tmp_path / "regional.png"),
    ]

    for path in written:
        assert path.exists()
        assert path.stat().st_size > 0


def test_the_curve_chart_never_needs_a_hue_the_palette_does_not_have(
    tmp_path: Path, cars: pd.DataFrame
) -> None:
    # A ninth series is never a generated colour; the chart folds brands out instead.
    curves = depreciation_curves(cars, vehicle_type="car")
    retained = depreciation_at_ages(curves)

    figures.retained_value_figure(retained, tmp_path / "retained.png", max_brands=2)

    assert (tmp_path / "retained.png").exists()
