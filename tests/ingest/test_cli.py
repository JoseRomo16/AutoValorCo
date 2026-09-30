"""Tests for the capture command line."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from autovalor.ingest import cli
from autovalor.ingest.records import RawListing, VehicleType


def make_listing(listing_id: str, vehicle_type: VehicleType) -> RawListing:
    return RawListing(
        listing_id=listing_id,
        source_url=f"https://articulo.tucarro.com.co/{listing_id}",
        captured_at=datetime.now(UTC),
        vehicle_type=vehicle_type,
        title="Mazda 3",
        price_raw="68.900.000",
    )


@pytest.fixture
def fake_scrape(monkeypatch: pytest.MonkeyPatch) -> list[tuple[VehicleType, str | None, int]]:
    """Replace the network call, recording the (vertical, location, pages) asked for."""
    calls: list[tuple[VehicleType, str | None, int]] = []

    def scrape_search(
        vehicle_type: VehicleType,
        *,
        pages: int,
        location: str | None = None,
        client: object = None,
        captured_at: datetime | None = None,
    ) -> list[RawListing]:
        calls.append((vehicle_type, location, pages))
        prefix = "MCO-CAR" if vehicle_type is VehicleType.CAR else "MCO-MOT"
        return [make_listing(f"{prefix}-{location or 'nacional'}", vehicle_type)]

    monkeypatch.setattr(cli, "scrape_search", scrape_search)
    return calls


def test_defaults_to_both_verticals_nationwide(
    fake_scrape: list[tuple[VehicleType, str | None, int]],
    tmp_path: Path,
) -> None:
    assert cli.main(["--pages", "3", "--data-dir", str(tmp_path)]) == 0
    assert fake_scrape == [
        (VehicleType.CAR, None, 3),
        (VehicleType.MOTORCYCLE, None, 3),
    ]


def test_writes_one_capture_per_vertical(
    fake_scrape: list[tuple[VehicleType, str | None, int]],
    tmp_path: Path,
) -> None:
    cli.main(["--pages", "1", "--data-dir", str(tmp_path)])
    written = sorted(path.parent.parent.name for path in tmp_path.rglob("*.parquet"))
    assert written == ["vehicle_type=car", "vehicle_type=motorcycle"]


def test_sweeps_every_requested_location(
    fake_scrape: list[tuple[VehicleType, str | None, int]],
    tmp_path: Path,
) -> None:
    cli.main(
        [
            "--vehicle-type",
            "car",
            "--location",
            "bogota-dc",
            "--location",
            "medellin",
            "--pages",
            "2",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert fake_scrape == [
        (VehicleType.CAR, "bogota-dc", 2),
        (VehicleType.CAR, "medellin", 2),
    ]


def test_dry_run_writes_nothing(
    fake_scrape: list[tuple[VehicleType, str | None, int]],
    tmp_path: Path,
) -> None:
    assert cli.main(["--vehicle-type", "car", "--dry-run", "--data-dir", str(tmp_path)]) == 0
    assert list(tmp_path.rglob("*.parquet")) == []


def test_reports_failure_when_nothing_is_captured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, "scrape_search", lambda *args, **kwargs: [])
    assert cli.main(["--vehicle-type", "car", "--data-dir", str(tmp_path)]) == 1
