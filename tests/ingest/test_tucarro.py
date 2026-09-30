"""Tests for the TuCarro scraper, driven by trimmed copies of real search pages."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from autovalor.config import Settings
from autovalor.ingest.polite import PoliteClient
from autovalor.ingest.records import RawListing, VehicleType
from autovalor.ingest.tucarro import RESULTS_PER_PAGE, parse_search_page, scrape_search, search_url

FIXTURES = Path(__file__).parent.parent / "fixtures"
CAPTURED_AT = datetime(2026, 9, 29, 14, 5, tzinfo=UTC)

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("autovalor.ingest.polite.time.sleep", lambda _seconds: None)


@pytest.fixture
def cars() -> list[RawListing]:
    html = (FIXTURES / "tucarro_cars.html").read_text(encoding="utf-8")
    return parse_search_page(html, vehicle_type=VehicleType.CAR, captured_at=CAPTURED_AT)


# --------------------------------------------------------------------------- #
# URL building
# --------------------------------------------------------------------------- #
def test_first_page_has_no_offset() -> None:
    assert search_url(VehicleType.CAR) == "https://carros.tucarro.com.co/carros-camionetas"


def test_offset_is_one_based() -> None:
    """Page 2 starts at result 49, matching the site's own paging."""
    assert search_url(VehicleType.CAR, page=2).endswith(f"/_Desde_{RESULTS_PER_PAGE + 1}")
    assert search_url(VehicleType.CAR, page=3).endswith(f"/_Desde_{2 * RESULTS_PER_PAGE + 1}")


def test_motorcycles_use_their_own_host() -> None:
    assert search_url(VehicleType.MOTORCYCLE) == "https://motos.tucarro.com.co/motos"


def test_location_is_part_of_the_path() -> None:
    url = search_url(VehicleType.CAR, page=2, location="bogota-dc")
    assert url == "https://carros.tucarro.com.co/carros-camionetas/bogota-dc/_Desde_49"


def test_rejects_page_zero() -> None:
    with pytest.raises(ValueError, match="page must be 1 or greater"):
        search_url(VehicleType.CAR, page=0)


# --------------------------------------------------------------------------- #
# Card parsing
# --------------------------------------------------------------------------- #
def test_skips_cards_without_a_link(cars: list[RawListing]) -> None:
    """The fixture holds three cards; the linkless one must not become a record."""
    assert len(cars) == 2


def test_parses_a_full_card(cars: list[RawListing]) -> None:
    listing = cars[0]
    assert listing.listing_id == "MCO-1686772601"
    assert listing.title == "Hyundai Hb20 2026 1.6 Advance Aut"
    assert listing.price_raw == "78.990.000"
    assert listing.currency == "$"
    assert listing.model_year_raw == "2026"
    assert listing.mileage_raw == "0 Km"
    assert listing.location_raw == "Armenia - Quindio"
    assert listing.vehicle_type is VehicleType.CAR
    assert listing.captured_at == CAPTURED_AT


def test_strips_tracking_fragment_from_the_url(cars: list[RawListing]) -> None:
    assert "#" not in cars[0].source_url
    assert cars[0].source_url.endswith("-hb20-premium-modelo-2026-_JM")


def test_keeps_the_unpunctuated_amount(cars: list[RawListing]) -> None:
    """The aria-label carries the amount without separators, handy for silver."""
    assert cars[0].attributes["price_aria_label"] == "78990000 pesos colombianos"


def test_records_official_store_without_the_seller_name(cars: list[RawListing]) -> None:
    """Ley 1581: the store flag is a market signal, the seller name is personal data."""
    assert cars[0].attributes["official_store"] == "true"
    assert cars[1].attributes["official_store"] == "false"
    serialised = " ".join(str(value) for listing in cars for value in listing.model_dump().values())
    assert "Autama" not in serialised


def test_extra_attributes_are_kept(cars: list[RawListing]) -> None:
    used_car = cars[1]
    assert used_car.model_year_raw == "2006"
    assert used_car.mileage_raw == "138.000 Km"
    assert "Mecánica" in used_car.attributes.values()


def test_parses_motorcycles() -> None:
    html = (FIXTURES / "tucarro_motorcycles.html").read_text(encoding="utf-8")
    listings = parse_search_page(html, vehicle_type=VehicleType.MOTORCYCLE, captured_at=CAPTURED_AT)
    assert [listing.listing_id for listing in listings] == ["MCO-2084746289", "MCO-4336714534"]
    assert listings[0].mileage_raw == "78.000 Km"
    assert all(listing.vehicle_type is VehicleType.MOTORCYCLE for listing in listings)


def test_empty_page_yields_nothing() -> None:
    assert parse_search_page("<html><body></body></html>", vehicle_type=VehicleType.CAR) == []


# --------------------------------------------------------------------------- #
# Multi-page scraping
# --------------------------------------------------------------------------- #
def build_client(handler: Handler) -> PoliteClient:
    settings = Settings(
        _env_file=None,
        scraper_min_delay_seconds=0.0,
        scraper_max_delay_seconds=0.0,
    )
    http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return PoliteClient(settings, client=http)


def page_handler(pages: dict[str, str]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, text=pages.get(request.url.path, "<html></html>"))

    return handler


def test_scrapes_several_pages_and_deduplicates() -> None:
    cars_html = (FIXTURES / "tucarro_cars.html").read_text(encoding="utf-8")
    motos_html = (FIXTURES / "tucarro_motorcycles.html").read_text(encoding="utf-8")
    handler = page_handler(
        {
            "/carros-camionetas": cars_html,
            "/carros-camionetas/_Desde_49": motos_html,
            # The site repeats listings across pages as the result set shifts under
            # paging; the capture must keep one record per listing id.
            "/carros-camionetas/_Desde_97": cars_html,
        }
    )

    with build_client(handler) as client:
        listings = scrape_search(VehicleType.CAR, pages=3, client=client)

    ids = sorted(listing.listing_id for listing in listings)
    assert ids == ["MCO-1686772601", "MCO-2084746289", "MCO-4336714534", "MCO-4430904096"]


def test_treats_a_404_past_the_last_page_as_the_end() -> None:
    """Observed live: an offset beyond the result set 404s instead of returning nothing."""
    cars_html = (FIXTURES / "tucarro_cars.html").read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if request.url.path == "/carros-camionetas":
            return httpx.Response(200, text=cars_html)
        return httpx.Response(404, text="not found")

    with build_client(handler) as client:
        listings = scrape_search(VehicleType.CAR, pages=4, client=client)

    assert len(listings) == 2


def test_a_404_on_the_first_page_is_an_error() -> None:
    """A bad location slug must fail loudly, not look like an empty result set."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(404, text="not found")

    with build_client(handler) as client, pytest.raises(httpx.HTTPStatusError):
        scrape_search(VehicleType.CAR, pages=3, location="no-such-place", client=client)


def test_stops_when_a_page_is_empty() -> None:
    cars_html = (FIXTURES / "tucarro_cars.html").read_text(encoding="utf-8")
    visited: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        visited.append(request.url.path)
        if request.url.path == "/carros-camionetas":
            return httpx.Response(200, text=cars_html)
        return httpx.Response(200, text="<html><body></body></html>")

    with build_client(handler) as client:
        listings = scrape_search(VehicleType.CAR, pages=5, client=client)

    assert len(listings) == 2
    assert visited == ["/carros-camionetas", "/carros-camionetas/_Desde_49"]
