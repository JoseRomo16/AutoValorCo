"""TuCarro scraper for cars and motorcycles.

TuCarro runs on MercadoLibre's search stack, so both verticals share one card layout
(``poly-card``) and one paging scheme. Two quirks shape this module:

* Pagination links are rendered client-side with empty ``href``s, so pages are reached
  through the offset URLs (``.../_Desde_49``) rather than by following links.
* The landing page is geolocated by IP, which would bias a capture towards whichever
  city the runner sits in. Captures therefore go through the category listing and,
  optionally, an explicit location slug.

Seller names are deliberately never read. Only whether the seller is an official store
is kept, which is a market signal rather than personal data (Ley 1581 de 2012).
"""

import re
from collections.abc import Iterator
from datetime import UTC, datetime

from bs4 import BeautifulSoup, Tag

from autovalor.ingest.polite import PoliteClient
from autovalor.ingest.records import RawListing, VehicleType

BASE_URLS: dict[VehicleType, str] = {
    VehicleType.CAR: "https://carros.tucarro.com.co/carros-camionetas",
    VehicleType.MOTORCYCLE: "https://motos.tucarro.com.co/motos",
}

RESULTS_PER_PAGE = 48
"""Cards per search page; the offset in ``_Desde_N`` is 1-based."""

CARD_SELECTOR = "li.ui-search-layout__item"
TITLE_SELECTOR = "a.poly-component__title"
AMOUNT_SELECTOR = ".poly-price__amount"
FRACTION_SELECTOR = ".andes-money-amount__fraction"
CURRENCY_SELECTOR = ".andes-money-amount__currency-symbol"
ATTRIBUTE_SELECTOR = "li.poly-attributes_list__item"
LOCATION_SELECTOR = ".poly-component__location"
OFFICIAL_STORE_SELECTOR = 'svg[aria-label="Tienda oficial"]'

_LISTING_ID = re.compile(r"(MCO-?\d+)")
_YEAR = re.compile(r"^(19|20)\d{2}$")
_MILEAGE = re.compile(r"\bkm\b", re.IGNORECASE)


def search_url(vehicle_type: VehicleType, *, page: int = 1, location: str | None = None) -> str:
    """Build the URL of a search results page.

    Args:
        vehicle_type: Vertical to search.
        page: 1-based page number.
        location: Optional location slug, for example ``"bogota-dc"``. Without it the
            listing is national.

    Returns:
        Absolute URL of the requested page.

    Raises:
        ValueError: If ``page`` is below 1.

    Examples:
        >>> search_url(VehicleType.CAR, page=2)
        'https://carros.tucarro.com.co/carros-camionetas/_Desde_49'
    """
    if page < 1:
        msg = f"page must be 1 or greater, got {page}"
        raise ValueError(msg)

    url = BASE_URLS[vehicle_type]
    if location:
        url = f"{url}/{location}"
    if page > 1:
        url = f"{url}/_Desde_{(page - 1) * RESULTS_PER_PAGE + 1}"
    return url


def parse_search_page(
    html: str,
    *,
    vehicle_type: VehicleType,
    captured_at: datetime | None = None,
) -> list[RawListing]:
    """Parse one search results page into bronze records.

    Cards without a usable URL are skipped rather than raising: a single broken card
    should not lose the other 47 of the page.
    """
    moment = captured_at if captured_at is not None else datetime.now(UTC)
    soup = BeautifulSoup(html, "lxml")
    listings: list[RawListing] = []
    for card in soup.select(CARD_SELECTOR):
        listing = _parse_card(card, vehicle_type=vehicle_type, captured_at=moment)
        if listing is not None:
            listings.append(listing)
    return listings


def scrape_search(
    vehicle_type: VehicleType,
    *,
    pages: int,
    location: str | None = None,
    client: PoliteClient | None = None,
    captured_at: datetime | None = None,
) -> list[RawListing]:
    """Scrape ``pages`` search pages and return the listings found, deduplicated.

    Stops early when a page returns no cards, which is how the last page announces
    itself once the result set is exhausted.
    """
    moment = captured_at if captured_at is not None else datetime.now(UTC)
    owned = client is None
    http = client if client is not None else PoliteClient()
    seen: dict[str, RawListing] = {}
    try:
        for page in range(1, pages + 1):
            url = search_url(vehicle_type, page=page, location=location)
            found = parse_search_page(
                http.get(url).text,
                vehicle_type=vehicle_type,
                captured_at=moment,
            )
            if not found:
                break
            for listing in found:
                seen.setdefault(listing.listing_id, listing)
    finally:
        if owned:
            http.close()
    return list(seen.values())


def iter_pages(
    vehicle_type: VehicleType, *, pages: int, location: str | None = None
) -> Iterator[str]:
    """Yield the URLs a capture of ``pages`` pages would visit."""
    for page in range(1, pages + 1):
        yield search_url(vehicle_type, page=page, location=location)


def _parse_card(
    card: Tag,
    *,
    vehicle_type: VehicleType,
    captured_at: datetime,
) -> RawListing | None:
    title_node = card.select_one(TITLE_SELECTOR)
    url = _attr(title_node, "href")
    if url is None:
        return None
    url = url.split("#", 1)[0]

    match = _LISTING_ID.search(url)
    if match is None:
        return None

    attributes: dict[str, str] = {}
    model_year_raw: str | None = None
    mileage_raw: str | None = None
    for index, node in enumerate(card.select(ATTRIBUTE_SELECTOR), start=1):
        value = node.get_text(strip=True)
        if not value:
            continue
        if model_year_raw is None and _YEAR.match(value):
            model_year_raw = value
        elif mileage_raw is None and _MILEAGE.search(value):
            mileage_raw = value
        else:
            attributes[f"attribute_{index}"] = value

    amount = card.select_one(AMOUNT_SELECTOR)
    aria_label = _attr(amount, "aria-label")
    if aria_label is not None:
        # "78990000 pesos colombianos": the unpunctuated amount, handy for silver.
        attributes["price_aria_label"] = aria_label
    attributes["official_store"] = str(card.select_one(OFFICIAL_STORE_SELECTOR) is not None).lower()

    return RawListing(
        listing_id=match.group(1),
        source_url=url,
        captured_at=captured_at,
        vehicle_type=vehicle_type,
        title=_text(card.select_one(TITLE_SELECTOR)),
        price_raw=_text(card.select_one(FRACTION_SELECTOR)),
        currency=_text(card.select_one(CURRENCY_SELECTOR)),
        model_year_raw=model_year_raw,
        mileage_raw=mileage_raw,
        location_raw=_text(card.select_one(LOCATION_SELECTOR)),
        attributes=attributes,
    )


def _text(node: Tag | None) -> str | None:
    """Return the stripped text of ``node``, or ``None`` when it is missing or empty."""
    if node is None:
        return None
    text = node.get_text(strip=True)
    return text or None


def _attr(node: Tag | None, name: str) -> str | None:
    """Return a single attribute value as a string, tolerating multi-valued attributes."""
    if node is None:
        return None
    value = node.get(name)
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return str(value[0])
    return None
