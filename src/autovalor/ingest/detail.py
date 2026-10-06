"""Enrich motorcycle listings from their own page's attribute table.

A search card gives a title, a price, a year and a mileage. The listing page gives a
structured table, and for motorcycles that table is the only place three things appear:
the **segment** (``Tipo de moto``: Naked, Scooter, Enduro, Doble propósito, Calle…), the
displacement at full coverage rather than the 80,6 % the title yields, and occasional
equipment and condition fields (brakes, gear count, single owner).

What the table does **not** carry, checked against real pages rather than assumed: there
is no version, no transmission, no fuel and no body style. Those are the car schema. The
motorcycle equivalent of body style is ``Tipo de moto``, and the closest thing to a
transmission is ``Numero de velocidades``, which only some adverts fill in.

Three rules shape this module:

* **One request per listing, once.** The attributes describe the vehicle, not the advert,
  so a listing that already has a detail row is never fetched again. The run takes a
  budget and stops there.
* **Allow-list, not scrape-everything.** Only the labels in :data:`DETAIL_LABELS` are
  kept. An unknown label is counted so schema drift is visible, and dropped.
* **Nothing personal, and no HTML.** The page carries the seller's name, their phone
  number and a contact form. None of it is read, and the page itself is never stored —
  a stored page would contain that data whether or not anything parsed it (Ley 1581 de
  2012). A test asserts it.
"""

import logging
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import httpx
from bs4 import BeautifulSoup

from autovalor.ingest.polite import PoliteClient, RetryableStatusError, RobotsDisallowedError
from autovalor.ingest.records import ListingDetail, VehicleType

logger = logging.getLogger("autovalor.ingest.detail")

ATTRIBUTE_ROW_SELECTOR: Final = "tr.andes-table__row"
"""The specs table on a listing page: one row per attribute, ``th`` label, ``td`` value."""

DETAIL_LABELS: Final[dict[str, str]] = {
    # Present on every page surveyed.
    "Tipo de moto": "body_type",
    "Marca": "brand",
    "Modelo": "model",
    "Año": "model_year",
    "Motor": "engine_type",
    "Kilómetros": "mileage",
    "Cilindrada": "engine_cc",
    "Color": "color",
    "Frenos": "brakes",
    # Present on some.
    "Transmisión": "transmission",
    "Potencia": "power",
    "Numero de velocidades": "gear_count",
    "Número de velocidades": "gear_count",
    "Único dueño": "single_owner",
    "Clasificación del vehículo": "vehicle_class",
    "Con precio negociable": "negotiable",
    "Frenos ABS": "abs",
    "Alarma": "alarm",
    "GPS": "gps",
    "Tipo de cargador": "charger_type",
    # Requested for this enrichment and not seen on any motorcycle page so far — they are
    # the car schema. Listed anyway so that the day one appears it is captured instead of
    # being dropped as an unknown label.
    "Versión": "version",
    "Combustible": "fuel",
    "Tipo de combustible": "fuel",
    "Carrocería": "body_style",
    "Tipo de carrocería": "body_style",
    "Puertas": "doors",
}
"""Labels kept, mapped to stable English keys.

An allow-list rather than a filter: a label that is not here cannot reach storage, which
is what keeps a future redesign of the page from quietly introducing a field nobody
reviewed. Both spellings of the gear-count and fuel labels appear in the wild.

The entries were derived from real pages, not guessed, and the unknown-label report in
:class:`EnrichmentResult` is how the list grows: it earned ``Transmisión``, ``GPS``,
``Alarma`` and ``Tipo de cargador`` on the first three-page trial run.
"""

DEFAULT_BUDGET: Final = 500
"""Listings enriched per run.

Polite scraping means a randomised pause between requests, so the budget is really a
time budget: at a 2-6 second pause, 500 listings is around 35 minutes. The weekly capture
takes minutes, so this cannot be part of it by default.
"""

DEFAULT_SEED: Final = 20260930
"""Seed for choosing which listings to enrich, matching the modeling seed.

The sample is drawn at random rather than taken in listing order: identifiers correlate
with publication date, so the first N would be a time slice of the market rather than a
picture of it, and the enriched subset has to resemble the vertical to be worth measuring
on.
"""


@dataclass(frozen=True)
class EnrichmentResult:
    """What one enrichment run did.

    Attributes:
        details: Rows parsed, ready for the detail layer.
        requested: Listings the run attempted.
        failed: Listings whose page could not be read.
        unknown_labels: Labels seen on the pages that are not on the allow-list, with
            how often — the schema-drift signal.
    """

    details: tuple[ListingDetail, ...]
    requested: int
    failed: tuple[str, ...]
    unknown_labels: dict[str, int]

    def summary(self) -> str:
        """Return a one-line description for a log."""
        unknown = ", ".join(sorted(self.unknown_labels)) or "none"
        return (
            f"{len(self.details)}/{self.requested} listings enriched, "
            f"{len(self.failed)} failed, unknown labels: {unknown}"
        )


def parse_detail_page(
    html: str,
    *,
    listing_id: str,
    source_url: str,
    vehicle_type: VehicleType,
    fetched_at: datetime | None = None,
) -> tuple[ListingDetail, dict[str, int]]:
    """Parse one listing page's attribute table.

    Args:
        html: The page as served.
        listing_id: Identifier the attributes belong to.
        source_url: Page the attributes were read from.
        vehicle_type: Vertical the listing belongs to.
        fetched_at: Fetch instant; defaults to now in UTC.

    Returns:
        The parsed row, and the labels that were seen but are not on the allow-list.

    A page whose table is missing or empty yields a record with no attributes rather than
    an error: it is a real outcome — some adverts fill nothing in — and the empty row is
    what stops the listing from being fetched again forever.
    """
    moment = fetched_at if fetched_at is not None else datetime.now(UTC)
    soup = BeautifulSoup(html, "lxml")

    attributes: dict[str, str] = {}
    unknown: dict[str, int] = {}
    for row in soup.select(ATTRIBUTE_ROW_SELECTOR):
        header = row.select_one("th")
        cell = row.select_one("td")
        if header is None or cell is None:
            continue
        label = header.get_text(strip=True)
        value = cell.get_text(strip=True)
        if not label or not value:
            continue
        key = DETAIL_LABELS.get(label)
        if key is None:
            unknown[label] = unknown.get(label, 0) + 1
            continue
        # First occurrence wins: the highlighted specs at the top of the page repeat a
        # few of the same labels further down.
        attributes.setdefault(key, value)

    detail = ListingDetail(
        listing_id=listing_id,
        source_url=source_url,
        fetched_at=moment,
        vehicle_type=vehicle_type,
        attributes=attributes,
    )
    return detail, unknown


def select_listings(
    candidates: Sequence[tuple[str, str]],
    *,
    budget: int = DEFAULT_BUDGET,
    seed: int = DEFAULT_SEED,
) -> list[tuple[str, str]]:
    """Choose which listings to enrich, at random with a fixed seed.

    Args:
        candidates: ``(listing_id, source_url)`` pairs that have no detail row yet.
        budget: Most listings to return.
        seed: Seed for the draw, so a run is reproducible and two runs with the same
            seed and the same candidates pick the same listings.

    Returns:
        Up to ``budget`` pairs, in a stable order.

    Raises:
        ValueError: If ``budget`` is below 1.
    """
    if budget < 1:
        msg = f"budget must be 1 or greater, got {budget}"
        raise ValueError(msg)

    ordered = sorted(candidates)
    if len(ordered) <= budget:
        return ordered
    return sorted(random.Random(seed).sample(ordered, budget))


def enrich_listings(
    candidates: Sequence[tuple[str, str]],
    *,
    vehicle_type: VehicleType = VehicleType.MOTORCYCLE,
    budget: int = DEFAULT_BUDGET,
    seed: int = DEFAULT_SEED,
    client: PoliteClient | None = None,
    fetched_at: datetime | None = None,
) -> EnrichmentResult:
    """Fetch and parse the detail page of up to ``budget`` listings.

    Args:
        candidates: ``(listing_id, source_url)`` pairs with no detail row yet.
        vehicle_type: Vertical being enriched.
        budget: Most listings to fetch in this run.
        seed: Seed for the random draw.
        client: Polite client to reuse; one is created and closed when omitted.
        fetched_at: Fetch instant recorded on every row; defaults to now in UTC.

    Returns:
        The rows parsed, plus what failed and which labels were unrecognised.

    A listing whose page fails is logged and skipped rather than aborting the run, for the
    same reason a failed location does not abort a capture: losing one page is much better
    than losing the batch.
    """
    chosen = select_listings(candidates, budget=budget, seed=seed)
    moment = fetched_at if fetched_at is not None else datetime.now(UTC)
    owned = client is None
    http = client if client is not None else PoliteClient()

    details: list[ListingDetail] = []
    failed: list[str] = []
    unknown_total: dict[str, int] = {}
    try:
        for listing_id, url in chosen:
            try:
                html = http.get(url).text
            except (httpx.HTTPError, RetryableStatusError, RobotsDisallowedError) as exc:
                logger.warning("%s: skipped after %s: %s", listing_id, type(exc).__name__, exc)
                failed.append(listing_id)
                continue
            detail, unknown = parse_detail_page(
                html,
                listing_id=listing_id,
                source_url=url,
                vehicle_type=vehicle_type,
                fetched_at=moment,
            )
            details.append(detail)
            for label, count in unknown.items():
                unknown_total[label] = unknown_total.get(label, 0) + count
    finally:
        if owned:
            http.close()

    result = EnrichmentResult(tuple(details), len(chosen), tuple(failed), unknown_total)
    logger.info("%s", result.summary())
    return result


def coverage(details: Iterable[ListingDetail]) -> dict[str, float]:
    """Return the share of rows carrying each allow-listed attribute.

    Args:
        details: Parsed rows.

    Returns:
        One entry per key that appeared, as a fraction of the rows. Useful for deciding
        whether an attribute is worth feeding to a model at all.
    """
    rows = list(details)
    if not rows:
        return {}
    counts: dict[str, int] = {}
    for detail in rows:
        for key in detail.attributes:
            counts[key] = counts.get(key, 0) + 1
    return {key: count / len(rows) for key, count in sorted(counts.items())}
