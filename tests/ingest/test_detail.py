"""Tests for the listing-page enrichment, driven by a trimmed copy of a real page."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from autovalor.config import Settings
from autovalor.ingest.detail import (
    DETAIL_LABELS,
    coverage,
    enrich_listings,
    parse_detail_page,
    select_listings,
)
from autovalor.ingest.polite import PoliteClient
from autovalor.ingest.records import ListingDetail, VehicleType

FIXTURES = Path(__file__).parent.parent / "fixtures"
FETCHED_AT = datetime(2026, 10, 6, 1, 30, tzinfo=UTC)
URL = "https://articulo.tucarro.com.co/MCO-2084746289-pulsar-ns-200-2019-_JM"

Handler = Callable[[httpx.Request], httpx.Response]

# Everything in the fixture's seller card. None of it may appear anywhere in a parsed row.
PERSONAL_DATA = (
    "Carlos Andres Pineda",
    "+57 300 123 4567",
    "3001234567",
    "carlos.pineda@example.com",
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("autovalor.ingest.polite.time.sleep", lambda _seconds: None)


@pytest.fixture
def page() -> str:
    return (FIXTURES / "tucarro_detail_motorcycle.html").read_text(encoding="utf-8")


@pytest.fixture
def parsed(page: str) -> tuple[ListingDetail, dict[str, int]]:
    return parse_detail_page(
        page,
        listing_id="MCO-2084746289",
        source_url=URL,
        vehicle_type=VehicleType.MOTORCYCLE,
        fetched_at=FETCHED_AT,
    )


# --------------------------------------------------------------------------- #
# Ley 1581 de 2012
# --------------------------------------------------------------------------- #
def test_no_personal_data_of_the_seller_is_stored(
    parsed: tuple[ListingDetail, dict[str, int]],
) -> None:
    """The listing page carries the seller's name, phone and e-mail. None is read.

    The same guarantee the search cards have, enforced the same way: serialise everything
    the record would write and assert the personal data is not in it. The allow-list is
    what makes this hold — the fixture even puts a "Nombre del vendedor" row inside the
    attribute table, which is exactly the shape of mistake this test exists to catch.
    """
    detail, _ = parsed

    serialised = " ".join(str(value) for value in detail.to_row().values())

    for personal in PERSONAL_DATA:
        assert personal not in serialised
    assert "vendedor" not in serialised.lower()


def test_the_raw_html_is_never_part_of_the_record(
    parsed: tuple[ListingDetail, dict[str, int]], page: str
) -> None:
    # A stored page would contain the seller's data whether or not anything parsed it.
    detail, _ = parsed

    serialised = " ".join(str(value) for value in detail.to_row().values())

    assert "<html" not in serialised
    assert len(serialised) < len(page) / 10


def test_a_label_outside_the_allow_list_is_reported_and_dropped(
    parsed: tuple[ListingDetail, dict[str, int]],
) -> None:
    # Both unknown labels are dropped, and both are reported so schema drift is visible.
    # One is harmless, the other is the reason the allow-list exists.
    detail, unknown = parsed

    assert "Sistema de arranque" not in str(detail.attributes)
    assert unknown == {"Sistema de arranque": 1, "Nombre del vendedor": 1}


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def test_parses_the_attribute_table(parsed: tuple[ListingDetail, dict[str, int]]) -> None:
    detail, _ = parsed

    assert detail.attributes["body_type"] == "Naked"
    assert detail.attributes["engine_cc"] == "200 cc"
    assert detail.attributes["brand"] == "Bajaj"
    assert detail.attributes["model"] == "PULSAR NS 200"
    assert detail.attributes["mileage"] == "32.500 km"
    assert detail.attributes["brakes"] == "Disco"
    assert detail.attributes["single_owner"] == "Sí"


def test_keeps_the_transmission_and_gear_count_when_the_advert_has_them(
    parsed: tuple[ListingDetail, dict[str, int]],
) -> None:
    # Transmission is one of the fields this enrichment was asked for. It is absent from
    # most motorcycle pages but not all, which is why it is on the allow-list.
    detail, _ = parsed

    assert detail.attributes["transmission"] == "Manual"
    assert detail.attributes["gear_count"] == "6"


def test_values_are_kept_as_published(parsed: tuple[ListingDetail, dict[str, int]]) -> None:
    # This layer is bronze-grade: units and separators are parsed in dbt, not here.
    detail, _ = parsed

    assert detail.attributes["engine_cc"] == "200 cc"
    assert detail.attributes["model_year"] == "2019"


def test_a_row_without_a_value_is_skipped(parsed: tuple[ListingDetail, dict[str, int]]) -> None:
    # The fixture has an empty Potencia cell and a cell with no header at all.
    detail, _ = parsed

    assert "power" not in detail.attributes


def test_a_page_without_a_table_yields_an_empty_row() -> None:
    # A real outcome: some adverts fill nothing in. The empty row is what stops the
    # listing from being fetched again forever.
    detail, unknown = parse_detail_page(
        "<html><body><h1>Sin tabla</h1></body></html>",
        listing_id="MCO-1",
        source_url=URL,
        vehicle_type=VehicleType.MOTORCYCLE,
    )

    assert detail.attributes == {}
    assert unknown == {}


def test_the_record_carries_its_provenance(parsed: tuple[ListingDetail, dict[str, int]]) -> None:
    detail, _ = parsed

    row = detail.to_row()
    assert row["listing_id"] == "MCO-2084746289"
    assert row["source_url"] == URL
    assert row["source"] == "tucarro"
    assert row["vehicle_type"] == "motorcycle"
    assert row["fetched_at"] == FETCHED_AT
    assert row["detail_schema_version"] >= 1


def test_every_allow_listed_label_maps_to_a_non_empty_key() -> None:
    assert all(label and key for label, key in DETAIL_LABELS.items())


# --------------------------------------------------------------------------- #
# Choosing what to fetch
# --------------------------------------------------------------------------- #
def _candidates(count: int) -> list[tuple[str, str]]:
    return [
        (f"MCO-{index:06d}", f"https://articulo.tucarro.com.co/MCO-{index:06d}-pulsar-_JM")
        for index in range(count)
    ]


def test_the_sample_is_random_rather_than_the_first_n() -> None:
    # Identifiers correlate with publication date, so the first N would be a time slice
    # of the market instead of a picture of it.
    candidates = _candidates(100)

    chosen = select_listings(candidates, budget=10, seed=7)

    assert len(chosen) == 10
    assert chosen != candidates[:10]


def test_the_same_seed_picks_the_same_listings() -> None:
    candidates = _candidates(100)

    first = select_listings(candidates, budget=10, seed=7)
    second = select_listings(candidates, budget=10, seed=7)

    assert first == second
    assert first != select_listings(candidates, budget=10, seed=8)


def test_a_budget_larger_than_the_candidates_takes_them_all() -> None:
    candidates = _candidates(5)

    assert select_listings(candidates, budget=50) == sorted(candidates)


def test_a_budget_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="budget must be 1 or greater"):
        select_listings(_candidates(5), budget=0)


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
def build_client(handler: Handler) -> PoliteClient:
    settings = Settings(
        _env_file=None,
        scraper_min_delay_seconds=0.0,
        scraper_max_delay_seconds=0.0,
    )
    http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return PoliteClient(settings, client=http)


def page_handler(page: str, *, failing: set[str] | None = None) -> Handler:
    broken = failing or set()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if any(token in request.url.path for token in broken):
            return httpx.Response(404)
        return httpx.Response(200, text=page)

    return handler


def test_enriches_within_the_budget(page: str) -> None:
    client = build_client(page_handler(page))

    result = enrich_listings(_candidates(30), budget=4, client=client, fetched_at=FETCHED_AT)

    assert result.requested == 4
    assert len(result.details) == 4
    assert result.failed == ()
    assert all(detail.attributes["body_type"] == "Naked" for detail in result.details)


def test_a_failing_page_is_skipped_rather_than_aborting_the_run(page: str) -> None:
    # Losing one page is much better than losing the batch, which is how a failed location
    # is treated during a capture.
    candidates = _candidates(5)
    broken = candidates[2][0]
    client = build_client(page_handler(page, failing={broken}))

    result = enrich_listings(candidates, budget=5, client=client, fetched_at=FETCHED_AT)

    assert len(result.details) == 4
    assert result.failed == (broken,)


def test_unknown_labels_are_aggregated_across_the_run(page: str) -> None:
    client = build_client(page_handler(page))

    result = enrich_listings(_candidates(3), budget=3, client=client, fetched_at=FETCHED_AT)

    assert result.unknown_labels == {"Sistema de arranque": 3, "Nombre del vendedor": 3}


def test_coverage_reports_the_share_of_rows_carrying_each_attribute(page: str) -> None:
    client = build_client(page_handler(page))
    result = enrich_listings(_candidates(2), budget=2, client=client, fetched_at=FETCHED_AT)

    shares = coverage(result.details)

    assert shares["body_type"] == 1.0
    assert "power" not in shares


def test_coverage_of_nothing_is_empty() -> None:
    assert coverage([]) == {}
