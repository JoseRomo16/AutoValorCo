"""Tests for the immutable bronze writer."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from autovalor.ingest.bronze import capture_filename, read_captures, write_capture
from autovalor.ingest.records import BRONZE_SCHEMA_VERSION, RawListing, VehicleType

CAPTURED_AT = datetime(2026, 9, 29, 14, 5, 0, tzinfo=UTC)


def make_listing(listing_id: str = "MCO-1", **overrides: object) -> RawListing:
    defaults: dict[str, object] = {
        "listing_id": listing_id,
        "source_url": f"https://carros.tucarro.com.co/{listing_id}",
        "captured_at": CAPTURED_AT,
        "vehicle_type": VehicleType.CAR,
        "title": "Mazda 3 Grand Touring",
        "price_raw": "68.900.000",
        "currency": "$",
        "model_year_raw": "2019",
        "mileage_raw": "72.000 Km",
        "location_raw": "Medellín - Antioquia",
        "attributes": {"Transmisión": "Automática"},
    }
    return RawListing(**(defaults | overrides))


def test_writes_partitioned_parquet(tmp_path: Path) -> None:
    target = write_capture(
        [make_listing()],
        vehicle_type=VehicleType.CAR,
        captured_at=CAPTURED_AT,
        data_dir=tmp_path,
    )

    expected = (
        tmp_path
        / "bronze"
        / "source=tucarro"
        / "vehicle_type=car"
        / "capture_date=2026-09-29"
        / "listings_20260929T140500Z.parquet"
    )
    assert target == expected
    assert target.is_file()


def test_round_trips_the_listing(tmp_path: Path) -> None:
    write_capture(
        [make_listing()],
        vehicle_type=VehicleType.CAR,
        captured_at=CAPTURED_AT,
        data_dir=tmp_path,
    )
    frame = read_captures(tmp_path, vehicle_type=VehicleType.CAR)

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["listing_id"] == "MCO-1"
    assert row["source_url"].endswith("MCO-1")
    assert row["vehicle_type"] == "car"
    assert row["price_raw"] == "68.900.000"
    assert row["bronze_schema_version"] == BRONZE_SCHEMA_VERSION
    assert '"Transmisión": "Automática"' in row["attributes_json"]


def test_refuses_empty_capture(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        write_capture([], vehicle_type=VehicleType.CAR, captured_at=CAPTURED_AT, data_dir=tmp_path)


def test_bronze_is_immutable(tmp_path: Path) -> None:
    kwargs = {
        "vehicle_type": VehicleType.CAR,
        "captured_at": CAPTURED_AT,
        "data_dir": tmp_path,
    }
    write_capture([make_listing()], **kwargs)  # type: ignore[arg-type]

    with pytest.raises(FileExistsError):
        write_capture([make_listing("MCO-2")], **kwargs)  # type: ignore[arg-type]


def test_reads_nothing_before_the_first_capture(tmp_path: Path) -> None:
    assert read_captures(tmp_path).empty


def test_filters_by_vehicle_type(tmp_path: Path) -> None:
    write_capture(
        [make_listing("MCO-1")],
        vehicle_type=VehicleType.CAR,
        captured_at=CAPTURED_AT,
        data_dir=tmp_path,
    )
    write_capture(
        [make_listing("MCO-9", vehicle_type=VehicleType.MOTORCYCLE)],
        vehicle_type=VehicleType.MOTORCYCLE,
        captured_at=CAPTURED_AT,
        data_dir=tmp_path,
    )

    cars = read_captures(tmp_path, vehicle_type=VehicleType.CAR)
    everything: pd.DataFrame = read_captures(tmp_path)

    assert list(cars["listing_id"]) == ["MCO-1"]
    assert len(everything) == 2


def test_capture_filename_is_utc_and_sortable() -> None:
    assert capture_filename(CAPTURED_AT) == "listings_20260929T140500Z.parquet"
