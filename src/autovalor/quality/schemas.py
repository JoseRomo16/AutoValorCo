"""Pandera schemas guarding each layer of the lake.

Each layer has a contract, and ``make transform`` refuses to move data forward when
one is broken. The thresholds below are the single source of truth for what counts as
a plausible listing; ``dbt/dbt_project.yml`` mirrors them as dbt vars and a test keeps
the two in step.
"""

from typing import Final

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaError, SchemaErrors

# --------------------------------------------------------------------------- #
# Plausibility thresholds
# --------------------------------------------------------------------------- #
MIN_PRICE_COP: Final = 1_000_000
"""Below a million pesos the listing is a part, a scam or a typo, not a vehicle."""

MAX_PRICE_COP: Final = 2_000_000_000
"""Two thousand million pesos is far above any mainstream used vehicle."""

MIN_MODEL_YEAR: Final = 1950
"""Older vehicles exist but are collector items, priced by a different market."""

MAX_MILEAGE_KM: Final = 1_000_000
"""A million kilometres is already implausible for a private vehicle."""

MIN_ENGINE_CC: Final = 50
"""Smallest displacement worth treating as a motorcycle rather than a moped part."""

MAX_ENGINE_CC: Final = 2_500
"""Largest displacement for a motorcycle; above this the number is not an engine."""

MIN_CAR_CC: Final = 600
"""Cars advertise litres; below 0.6 L the number parsed out is not a displacement."""

MAX_CAR_CC: Final = 8_000
"""Eight litres covers every car sold in Colombia, with room to spare."""

MIN_GEAR_COUNT: Final = 1
"""A single-speed motorcycle exists — scooters and electrics; zero gears does not."""

MAX_GEAR_COUNT: Final = 12
"""Above a dozen the number is not a gear count.

The listing page's gear field is free text, and the first production pass returned 0 and
82 among the real values, so this range is enforced in ``stg_listing_details`` and not
only here.
"""

VEHICLE_TYPES: Final = ("car", "motorcycle")

_LISTING_ID_PATTERN = r"^MCO-?\d+$"

# --------------------------------------------------------------------------- #
# Bronze
# --------------------------------------------------------------------------- #
BRONZE_LISTINGS: Final = pa.DataFrameSchema(
    name="bronze_listings",
    strict=True,
    coerce=True,
    columns={
        "listing_id": pa.Column(
            str, nullable=False, checks=pa.Check.str_matches(_LISTING_ID_PATTERN)
        ),
        "source": pa.Column(str, nullable=False),
        "source_url": pa.Column(str, nullable=False, checks=pa.Check.str_startswith("https://")),
        "captured_at": pa.Column("datetime64[ns, UTC]", nullable=False),
        "vehicle_type": pa.Column(str, nullable=False, checks=pa.Check.isin(VEHICLE_TYPES)),
        "title": pa.Column(str, nullable=True),
        "price_raw": pa.Column(str, nullable=True),
        "currency": pa.Column(str, nullable=True),
        "model_year_raw": pa.Column(str, nullable=True),
        "mileage_raw": pa.Column(str, nullable=True),
        "location_raw": pa.Column(str, nullable=True),
        "attributes_json": pa.Column(str, nullable=False),
        "bronze_schema_version": pa.Column(int, nullable=False, checks=pa.Check.ge(1)),
    },
)
"""Bronze holds raw strings; the only promises are identity and provenance."""

BRONZE_CAPTURE: Final = BRONZE_LISTINGS.update_column("listing_id", unique=True)
"""A single capture file, where a listing may appear only once."""

# --------------------------------------------------------------------------- #
# Detail — listing-page attributes, one row per listing
# --------------------------------------------------------------------------- #
BRONZE_DETAILS: Final = pa.DataFrameSchema(
    name="bronze_details",
    strict=True,
    coerce=True,
    columns={
        "listing_id": pa.Column(
            str, nullable=False, unique=True, checks=pa.Check.str_matches(_LISTING_ID_PATTERN)
        ),
        "source": pa.Column(str, nullable=False),
        "source_url": pa.Column(str, nullable=False, checks=pa.Check.str_startswith("https://")),
        "fetched_at": pa.Column("datetime64[ns, UTC]", nullable=False),
        "vehicle_type": pa.Column(str, nullable=False, checks=pa.Check.isin(VEHICLE_TYPES)),
        "attributes_json": pa.Column(str, nullable=False),
        "detail_schema_version": pa.Column(int, nullable=False, checks=pa.Check.ge(1)),
    },
)
"""The attribute table of a listing page.

``strict=True`` is doing privacy work here, not only typing: the column set is closed, so
a column carrying a seller's name, phone number or e-mail cannot reach this layer even if
something upstream started producing one. Combined with the parser's allow-list, that is
two independent barriers (Ley 1581 de 2012).

``listing_id`` is unique because this layer is keyed by vehicle rather than by capture: a
listing is enriched once and never re-fetched.
"""

# --------------------------------------------------------------------------- #
# Silver
# --------------------------------------------------------------------------- #
SILVER_LISTINGS: Final = pa.DataFrameSchema(
    name="silver_listings",
    strict=True,
    coerce=True,
    columns={
        "listing_id": pa.Column(str, nullable=False),
        "source": pa.Column(str, nullable=False),
        "source_url": pa.Column(str, nullable=False),
        "vehicle_type": pa.Column(str, nullable=False, checks=pa.Check.isin(VEHICLE_TYPES)),
        "title": pa.Column(str, nullable=True),
        # Silver deliberately keeps implausible rows so that data quality is
        # measurable; the ranges are enforced in gold, which is what models read.
        # Nullable integers need pandas' "Int64", since plain int64 cannot hold NA.
        "price_cop": pa.Column("Int64", nullable=True),
        "model_year": pa.Column("Int64", nullable=True),
        "mileage_km": pa.Column("Int64", nullable=True),
        "city": pa.Column(str, nullable=True),
        "department": pa.Column(str, nullable=True),
        "is_official_store": pa.Column(bool, nullable=False),
        "first_seen_at": pa.Column("datetime64[ns, UTC]", nullable=False),
        "last_seen_at": pa.Column("datetime64[ns, UTC]", nullable=False),
        "capture_count": pa.Column("int64", nullable=False, checks=pa.Check.ge(1)),
        "is_valid": pa.Column(bool, nullable=False),
        "invalid_reason": pa.Column(str, nullable=True),
    },
    checks=[
        pa.Check(
            lambda df: df["last_seen_at"] >= df["first_seen_at"],
            name="last_seen_after_first_seen",
            error="last_seen_at must not precede first_seen_at",
        ),
        pa.Check(
            lambda df: df["is_valid"] == df["invalid_reason"].isna(),
            name="is_valid_matches_invalid_reason",
            error="is_valid must be true exactly when invalid_reason is null",
        ),
    ],
)
"""Silver is typed and deduplicated, but still keeps rows flagged as implausible."""

# --------------------------------------------------------------------------- #
# Gold
# --------------------------------------------------------------------------- #
GOLD_LISTINGS: Final = pa.DataFrameSchema(
    name="gold_listings",
    strict=True,
    coerce=True,
    columns={
        "listing_id": pa.Column(str, nullable=False, unique=True),
        "source_url": pa.Column(str, nullable=False),
        "vehicle_type": pa.Column(str, nullable=False, checks=pa.Check.isin(VEHICLE_TYPES)),
        "title": pa.Column(str, nullable=True),
        # Resolved from the title; "Desconocida" when no alias matched, never null.
        "brand": pa.Column(str, nullable=False),
        "model": pa.Column(str, nullable=True),
        # Mined from the title, so frequently absent; the range covers both verticals.
        "engine_cc": pa.Column(
            "Int64",
            nullable=True,
            checks=[pa.Check.ge(MIN_ENGINE_CC), pa.Check.le(MAX_CAR_CC)],
        ),
        "is_quad": pa.Column(bool, nullable=False),
        # Detail-page features. Null for every listing that has not been enriched, which
        # is most of them: the pass is incremental and costs one request each.
        "body_type": pa.Column(str, nullable=True),
        "transmission": pa.Column(str, nullable=True),
        "brakes": pa.Column(str, nullable=True),
        "color": pa.Column(str, nullable=True),
        "gear_count": pa.Column(
            "Int64",
            nullable=True,
            checks=pa.Check.in_range(MIN_GEAR_COUNT, MAX_GEAR_COUNT),
        ),
        "is_single_owner": pa.Column("boolean", nullable=True),
        "has_detail": pa.Column(bool, nullable=False),
        "price_cop": pa.Column(
            "int64",
            nullable=False,
            checks=[pa.Check.ge(MIN_PRICE_COP), pa.Check.le(MAX_PRICE_COP)],
        ),
        "log_price": pa.Column(float, nullable=False),
        "model_year": pa.Column(
            "int64", nullable=False, checks=[pa.Check.ge(MIN_MODEL_YEAR), pa.Check.le(2100)]
        ),
        "vehicle_age_years": pa.Column("int64", nullable=False, checks=pa.Check.ge(0)),
        "mileage_km": pa.Column(
            "int64", nullable=False, checks=[pa.Check.ge(0), pa.Check.le(MAX_MILEAGE_KM)]
        ),
        "km_per_year": pa.Column(float, nullable=False, checks=pa.Check.ge(0)),
        "city": pa.Column(str, nullable=True),
        "department": pa.Column(str, nullable=True),
        "is_official_store": pa.Column(bool, nullable=False),
        "first_seen_at": pa.Column("datetime64[ns, UTC]", nullable=False),
        "last_seen_at": pa.Column("datetime64[ns, UTC]", nullable=False),
    },
    checks=pa.Check(
        lambda df: (
            ~((df["vehicle_type"] == "motorcycle") & (df["engine_cc"] > MAX_ENGINE_CC)).fillna(
                False
            )
        ),
        name="motorcycle_displacement_in_range",
        error=f"motorcycle engine_cc must not exceed {MAX_ENGINE_CC}",
    ),
)
"""Gold is model-ready: one row per listing, every modeling column present.

The column-level range on ``engine_cc`` has to span both verticals, so the tighter
motorcycle ceiling is enforced as a frame-level check.
"""


class LayerValidationError(ValueError):
    """Raised when a frame breaks its layer contract.

    Pandera raises ``SchemaError`` for a single failure and ``SchemaErrors`` for
    several (an unexpected column, for instance, always arrives as the plural form).
    Callers should not have to know which, so both are wrapped here.
    """

    def __init__(self, layer: str, cause: SchemaError | SchemaErrors) -> None:
        """Record the layer that failed and the underlying pandera error."""
        super().__init__(f"{layer} does not satisfy its schema:\n{cause}")
        self.layer = layer
        self.cause = cause


def _validate(schema: pa.DataFrameSchema, frame: pd.DataFrame, layer: str) -> pd.DataFrame:
    try:
        return schema.validate(frame)
    except (SchemaError, SchemaErrors) as exc:
        raise LayerValidationError(layer, exc) from exc


def validate_bronze(frame: pd.DataFrame, *, single_capture: bool = False) -> pd.DataFrame:
    """Validate a bronze frame.

    Args:
        frame: Frame read from one or more bronze captures.
        single_capture: Also require listing ids to be unique, which only holds
            inside one capture file — the same listing legitimately reappears in
            later captures.

    Returns:
        The validated frame, with dtypes coerced.

    Raises:
        LayerValidationError: If the contract is broken.
    """
    schema = BRONZE_CAPTURE if single_capture else BRONZE_LISTINGS
    return _validate(schema, frame, "bronze")


def validate_detail(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate the listing-detail layer and return it with dtypes coerced.

    Args:
        frame: Frame read from one or more enrichment runs.

    Returns:
        The validated frame.

    Raises:
        LayerValidationError: If the contract is broken — including a column that is not
            on the declared list, which is what keeps personal data out of the layer.
    """
    return _validate(BRONZE_DETAILS, frame, "detail")


def validate_silver(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate a silver frame and return it with dtypes coerced.

    Raises:
        LayerValidationError: If the contract is broken.
    """
    return _validate(SILVER_LISTINGS, frame, "silver")


def validate_gold(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate a gold frame and return it with dtypes coerced.

    Raises:
        LayerValidationError: If the contract is broken.
    """
    return _validate(GOLD_LISTINGS, frame, "gold")
