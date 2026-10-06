"""Tests for the enrichment command."""

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from autovalor.ingest import detail_cli
from autovalor.ingest.bronze import write_details
from autovalor.ingest.detail import DEFAULT_BUDGET, DEFAULT_SEED, EnrichmentResult
from autovalor.ingest.detail_cli import build_parser, load_candidates, main
from autovalor.ingest.records import ListingDetail, VehicleType

FETCHED_AT = datetime(2026, 10, 6, 1, 30, tzinfo=UTC)


def make_gold(path: Path, *, motorcycles: int = 20, cars: int = 5) -> Path:
    """Write a gold table with the two columns the command reads."""
    rows = [
        {
            "listing_id": f"MCO-{index:06d}",
            "source_url": f"https://articulo.tucarro.com.co/MCO-{index:06d}-pulsar-_JM",
            "vehicle_type": "motorcycle" if index < motorcycles else "car",
        }
        for index in range(motorcycles + cars)
    ]
    with duckdb.connect(str(path)) as con:
        con.execute("create schema if not exists main_gold")
        con.register("listings", pd.DataFrame(rows))
        con.execute("create table main_gold.gold_listings as select * from listings")
    return path


def make_detail(listing_id: str) -> ListingDetail:
    return ListingDetail(
        listing_id=listing_id,
        source_url=f"https://articulo.tucarro.com.co/{listing_id}-pulsar-_JM",
        fetched_at=FETCHED_AT,
        vehicle_type=VehicleType.MOTORCYCLE,
        attributes={"body_type": "Naked"},
    )


def test_candidates_are_the_listings_of_one_vertical(tmp_path: Path) -> None:
    database = make_gold(tmp_path / "autovalor.duckdb")

    candidates = load_candidates(VehicleType.MOTORCYCLE, duckdb_path=database, data_dir=tmp_path)

    assert len(candidates) == 20
    assert all(listing_id.startswith("MCO-") for listing_id, _ in candidates)


def test_already_enriched_listings_are_not_candidates_again(tmp_path: Path) -> None:
    # One request per listing, ever: the attributes describe the vehicle, which does not
    # change while the advert is up.
    database = make_gold(tmp_path / "autovalor.duckdb")
    write_details(
        [make_detail("MCO-000000"), make_detail("MCO-000001")],
        vehicle_type=VehicleType.MOTORCYCLE,
        data_dir=tmp_path,
        fetched_at=FETCHED_AT,
    )

    candidates = load_candidates(VehicleType.MOTORCYCLE, duckdb_path=database, data_dir=tmp_path)

    assert len(candidates) == 18
    assert "MCO-000000" not in {listing_id for listing_id, _ in candidates}


def test_candidates_need_a_lake(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="run the transform first"):
        load_candidates(VehicleType.MOTORCYCLE, duckdb_path=tmp_path / "absent.duckdb")


def test_a_dry_run_makes_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    database = make_gold(tmp_path / "autovalor.duckdb")

    def refuse(*_: object, **__: object) -> EnrichmentResult:
        raise AssertionError("a dry run must not fetch anything")

    monkeypatch.setattr(detail_cli, "enrich_listings", refuse)

    code = main(
        [
            "--budget",
            "3",
            "--dry-run",
            "--duckdb-path",
            str(database),
            "--data-dir",
            str(tmp_path),
        ]
    )

    assert code == 0
    assert "3 listings would be fetched" in capsys.readouterr().out


def test_the_run_writes_the_rows_and_reports_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    database = make_gold(tmp_path / "autovalor.duckdb")
    details = (make_detail("MCO-000000"), make_detail("MCO-000001"))

    monkeypatch.setattr(
        detail_cli,
        "enrich_listings",
        lambda *_, **__: EnrichmentResult(details, 2, (), {"Sistema de arranque": 1}),
    )

    code = main(["--budget", "2", "--duckdb-path", str(database), "--data-dir", str(tmp_path)])

    assert code == 0
    written = list((tmp_path / "detail").glob("**/*.parquet"))
    assert len(written) == 1
    output = capsys.readouterr().out
    assert "body_type" in output
    # Schema drift is surfaced, not swallowed.
    assert "Sistema de arranque" in output


def test_a_run_where_every_page_failed_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = make_gold(tmp_path / "autovalor.duckdb")
    monkeypatch.setattr(
        detail_cli,
        "enrich_listings",
        lambda *_, **__: EnrichmentResult((), 2, ("MCO-000000", "MCO-000001"), {}),
    )

    assert main(["--duckdb-path", str(database), "--data-dir", str(tmp_path)]) == 1


def test_nothing_left_to_enrich_is_a_success(tmp_path: Path) -> None:
    database = make_gold(tmp_path / "autovalor.duckdb", motorcycles=1, cars=0)
    write_details(
        [make_detail("MCO-000000")],
        vehicle_type=VehicleType.MOTORCYCLE,
        data_dir=tmp_path,
        fetched_at=FETCHED_AT,
    )

    assert main(["--duckdb-path", str(database), "--data-dir", str(tmp_path)]) == 0


def test_a_missing_lake_is_reported_as_an_exit_code(tmp_path: Path) -> None:
    assert main(["--duckdb-path", str(tmp_path / "absent.duckdb")]) == 1


def test_the_parser_defaults_to_motorcycles_and_the_standard_budget() -> None:
    # Cars reach the F2 target with no extra request, so they are not the default.
    args = build_parser().parse_args([])

    assert args.vehicle_type == "motorcycle"
    assert args.budget == DEFAULT_BUDGET
    assert args.seed == DEFAULT_SEED
    assert args.dry_run is False


def test_the_detail_rows_round_trip_through_json(tmp_path: Path) -> None:
    # attributes_json is what dbt parses, so it has to survive the Parquet round trip.
    write_details(
        [make_detail("MCO-000000")],
        vehicle_type=VehicleType.MOTORCYCLE,
        data_dir=tmp_path,
        fetched_at=FETCHED_AT,
    )
    written = next((tmp_path / "detail").glob("**/*.parquet"))

    stored = pd.read_parquet(written)

    assert json.loads(stored["attributes_json"].iloc[0]) == {"body_type": "Naked"}
