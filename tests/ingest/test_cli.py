"""Tests for the capture command line."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd
import pytest

from autovalor.ingest import cli
from autovalor.ingest.polite import VerificationWallError
from autovalor.ingest.records import RawListing, VehicleType

WALL = "https://www.mercadolibre.com.co/gz/account-verification"


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


def wall_after(
    blocked_location: str, calls: list[tuple[VehicleType, str | None]]
) -> Callable[..., list[RawListing]]:
    """Return a fake scrape that works until ``blocked_location`` puts the wall up."""

    def scrape_search(
        vehicle_type: VehicleType,
        *,
        pages: int,
        location: str | None = None,
        client: object = None,
        captured_at: datetime | None = None,
    ) -> list[RawListing]:
        calls.append((vehicle_type, location))
        if location == blocked_location:
            raise VerificationWallError(f"https://carros.tucarro.com.co/{location}", WALL)
        return [make_listing(f"MCO-{location}", vehicle_type)]

    return scrape_search


def test_the_wall_stops_the_capture_with_its_own_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[VehicleType, str | None]] = []
    monkeypatch.setattr(cli, "scrape_search", wall_after("antioquia", calls))

    exit_code = cli.main(
        [
            "--location",
            "bogota-dc",
            "--location",
            "antioquia",
            "--location",
            "valle-del-cauca",
            "--data-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == cli.BLOCKED_EXIT_CODE
    # Not one more request: neither the remaining location nor the other vertical.
    assert calls == [(VehicleType.CAR, "bogota-dc"), (VehicleType.CAR, "antioquia")]


def test_what_was_captured_before_the_wall_is_written(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The locations already swept are data; stopping must not throw them away."""
    calls: list[tuple[VehicleType, str | None]] = []
    monkeypatch.setattr(cli, "scrape_search", wall_after("antioquia", calls))

    cli.main(
        [
            "--vehicle-type",
            "car",
            "--location",
            "bogota-dc",
            "--location",
            "antioquia",
            "--data-dir",
            str(tmp_path),
        ]
    )

    written = pd.read_parquet(next(tmp_path.rglob("*.parquet")))
    assert sorted(written["listing_id"]) == ["MCO-bogota-dc"]


def test_a_wall_on_the_first_location_writes_nothing_and_still_exits_three(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """What happened on 2026-10-26: the wall answered from the first request."""
    calls: list[tuple[VehicleType, str | None]] = []
    monkeypatch.setattr(cli, "scrape_search", wall_after("bogota-dc", calls))

    exit_code = cli.main(["--location", "bogota-dc", "--data-dir", str(tmp_path)])

    assert exit_code == cli.BLOCKED_EXIT_CODE
    assert list(tmp_path.rglob("*.parquet")) == []
    # And "nothing captured" is not reported as the ordinary empty-capture failure.
    assert calls == [(VehicleType.CAR, "bogota-dc")]


def test_the_wall_is_reported_as_blocked_not_as_a_failed_location(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[VehicleType, str | None]] = []
    monkeypatch.setattr(cli, "scrape_search", wall_after("bogota-dc", calls))

    result = cli.capture(
        VehicleType.CAR,
        pages=1,
        locations=["bogota-dc"],
        client=None,  # type: ignore[arg-type]  # the fake never touches it
        captured_at=datetime.now(UTC),
    )

    assert result.blocked == WALL
    assert result.failed_locations == []


def test_one_failing_location_does_not_lose_the_others(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Losing a department must not cost the whole capture, but must still be visible."""

    def scrape_search(
        vehicle_type: VehicleType,
        *,
        pages: int,
        location: str | None = None,
        client: object = None,
        captured_at: datetime | None = None,
    ) -> list[RawListing]:
        if location == "atlantico":
            request = httpx.Request("GET", "https://motos.tucarro.com.co/motos-atlantico")
            raise httpx.HTTPStatusError(
                "404", request=request, response=httpx.Response(404, request=request)
            )
        return [make_listing(f"MCO-{location}", vehicle_type)]

    monkeypatch.setattr(cli, "scrape_search", scrape_search)

    exit_code = cli.main(
        [
            "--vehicle-type",
            "car",
            "--location",
            "bogota-dc",
            "--location",
            "atlantico",
            "--location",
            "santander",
            "--data-dir",
            str(tmp_path),
        ]
    )

    written = pd.read_parquet(next(tmp_path.rglob("*.parquet")))
    assert sorted(written["listing_id"]) == ["MCO-bogota-dc", "MCO-santander"]
    assert exit_code == 1
