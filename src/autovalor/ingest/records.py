"""Bronze-layer record shape.

Bronze stays as close to the source as possible: every advertised field is kept as the
string it was published as, and all cleaning, parsing and unit normalisation happens in
silver. Personal data of sellers (names, phone numbers, e-mail addresses) is never
collected, per Ley 1581 de 2012 — the model does not need it and storing it would make
this dataset a liability.
"""

import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

BRONZE_SCHEMA_VERSION = 1
"""Bumped whenever the bronze columns change, so captures stay self-describing."""

DETAIL_SCHEMA_VERSION = 1
"""Same idea for the detail layer, which evolves on its own schedule."""


class VehicleType(StrEnum):
    """Vehicle families modeled separately, each with its own scraper and model."""

    CAR = "car"
    MOTORCYCLE = "motorcycle"


class RawListing(BaseModel):
    """A single listing as advertised, before any cleaning."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    listing_id: str = Field(description="Publisher's identifier, e.g. MCO-1234567890.")
    source: str = Field(default="tucarro", description="Site the listing came from.")
    source_url: str = Field(description="Canonical listing URL.")
    captured_at: datetime = Field(description="Capture instant, timezone-aware, UTC.")
    vehicle_type: VehicleType

    title: str | None = None
    price_raw: str | None = Field(default=None, description="Price as shown, e.g. '45.900.000'.")
    currency: str | None = Field(default=None, description="Currency symbol or code as shown.")
    model_year_raw: str | None = None
    mileage_raw: str | None = Field(default=None, description="Mileage as shown, e.g. '86.000 Km'.")
    location_raw: str | None = Field(default=None, description="City / department as shown.")
    attributes: dict[str, str] = Field(
        default_factory=dict,
        description="Any other label/value pair found on the card or detail page.",
    )

    def to_row(self) -> dict[str, Any]:
        """Flatten to a Parquet-friendly row, with attributes serialised as JSON."""
        row: dict[str, Any] = self.model_dump(mode="python", exclude={"attributes"})
        row["vehicle_type"] = self.vehicle_type.value
        row["attributes_json"] = json.dumps(self.attributes, ensure_ascii=False, sort_keys=True)
        row["bronze_schema_version"] = BRONZE_SCHEMA_VERSION
        return row


class ListingDetail(BaseModel):
    """The attribute table of one listing's own page, as published.

    A search card carries a handful of tokens; the listing page carries a structured
    table. This is one row per ``listing_id`` rather than one per capture: the attributes
    describe the vehicle, which does not change while the advert is up, so re-fetching a
    page that already has a detail row buys nothing and costs a request.

    Only the attribute table is read, and only labels on an explicit allow-list are kept
    (see :data:`autovalor.ingest.detail.DETAIL_LABELS`). The page also carries the
    seller's name, phone number and a contact form; none of it is parsed, stored, or even
    looked for. The raw HTML is never written either — a stored page would contain that
    personal data whether or not anything read it (Ley 1581 de 2012).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    listing_id: str = Field(description="Publisher's identifier, e.g. MCO-1234567890.")
    source: str = Field(default="tucarro", description="Site the listing came from.")
    source_url: str = Field(description="Page the attributes were read from.")
    fetched_at: datetime = Field(description="Fetch instant, timezone-aware, UTC.")
    vehicle_type: VehicleType
    attributes: dict[str, str] = Field(
        default_factory=dict,
        description="Allow-listed label/value pairs, exactly as published.",
    )

    def to_row(self) -> dict[str, Any]:
        """Flatten to a Parquet-friendly row, with attributes serialised as JSON."""
        row: dict[str, Any] = self.model_dump(mode="python", exclude={"attributes"})
        row["vehicle_type"] = self.vehicle_type.value
        row["attributes_json"] = json.dumps(self.attributes, ensure_ascii=False, sort_keys=True)
        row["detail_schema_version"] = DETAIL_SCHEMA_VERSION
        return row
