"""Tests for the validation command."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from autovalor.ingest.bronze import write_capture
from autovalor.ingest.records import RawListing, VehicleType
from autovalor.quality import cli

CAPTURED_AT = datetime(2026, 9, 29, 14, 5, tzinfo=UTC)


def write_good_capture(data_dir: Path) -> None:
    write_capture(
        [
            RawListing(
                listing_id="MCO-1686772601",
                source_url="https://articulo.tucarro.com.co/MCO-1686772601-hb20-_JM",
                captured_at=CAPTURED_AT,
                vehicle_type=VehicleType.CAR,
                title="Hyundai Hb20 2026",
                price_raw="78.990.000",
                currency="$",
                model_year_raw="2026",
                mileage_raw="0 Km",
                location_raw="Armenia - Quindio",
                attributes={"official_store": "true"},
            )
        ],
        vehicle_type=VehicleType.CAR,
        captured_at=CAPTURED_AT,
        data_dir=data_dir,
    )


def test_skips_stages_without_data(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    exit_code = cli.main(
        ["--data-dir", str(tmp_path), "--duckdb-path", str(tmp_path / "missing.duckdb")]
    )
    assert exit_code == 0
    assert "no data yet" in caplog.text


def test_validates_a_real_capture(tmp_path: Path) -> None:
    write_good_capture(tmp_path)
    assert cli.main(["--stage", "bronze", "--data-dir", str(tmp_path)]) == 0


def test_reports_a_broken_capture(tmp_path: Path) -> None:
    """A column the schema does not know about must fail, not pass silently."""
    write_good_capture(tmp_path)
    target = next(tmp_path.rglob("*.parquet"))
    frame = pd.read_parquet(target)
    frame["seller_name"] = "Autama Hyundai"
    frame.to_parquet(target, index=False)

    assert cli.main(["--stage", "bronze", "--data-dir", str(tmp_path)]) == 1


def test_missing_dbt_table_is_not_a_failure(tmp_path: Path) -> None:
    import duckdb

    database = tmp_path / "autovalor.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.sql("create table unrelated (x integer)")

    assert cli.main(["--stage", "gold", "--duckdb-path", str(database)]) == 0
