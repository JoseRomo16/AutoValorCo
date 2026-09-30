"""Tests for the Pandera layer contracts."""

import json

import pandas as pd
import pytest

from autovalor.quality.schemas import (
    LayerValidationError,
    validate_bronze,
    validate_gold,
    validate_silver,
)

UTC_NOW = pd.Timestamp("2026-09-29 14:05:00", tz="UTC")


def bronze_frame(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "listing_id": "MCO-1686772601",
        "source": "tucarro",
        "source_url": "https://articulo.tucarro.com.co/MCO-1686772601-hb20-_JM",
        "captured_at": UTC_NOW,
        "vehicle_type": "car",
        "title": "Hyundai Hb20 2026",
        "price_raw": "78.990.000",
        "currency": "$",
        "model_year_raw": "2026",
        "mileage_raw": "0 Km",
        "location_raw": "Armenia - Quindio",
        "attributes_json": json.dumps({"official_store": "true"}),
        "bronze_schema_version": 1,
    }
    return pd.DataFrame([row | overrides])


def silver_frame(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "listing_id": "MCO-1686772601",
        "source": "tucarro",
        "source_url": "https://articulo.tucarro.com.co/MCO-1686772601-hb20-_JM",
        "vehicle_type": "car",
        "title": "Hyundai Hb20 2026",
        "price_cop": 78_990_000,
        "model_year": 2026,
        "mileage_km": 0,
        "city": "Armenia",
        "department": "Quindio",
        "is_official_store": True,
        "first_seen_at": UTC_NOW,
        "last_seen_at": UTC_NOW,
        "capture_count": 1,
        "is_valid": True,
        "invalid_reason": None,
    }
    return pd.DataFrame([row | overrides])


def gold_frame(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "listing_id": "MCO-1686772601",
        "source_url": "https://articulo.tucarro.com.co/MCO-1686772601-hb20-_JM",
        "vehicle_type": "car",
        "title": "Hyundai Hb20 2026",
        "brand": "Hyundai",
        "model": "hb20",
        "price_cop": 78_990_000,
        "log_price": 18.18,
        "model_year": 2019,
        "vehicle_age_years": 7,
        "mileage_km": 72_000,
        "km_per_year": 10_285.7,
        "city": "Armenia",
        "department": "Quindio",
        "is_official_store": True,
        "first_seen_at": UTC_NOW,
        "last_seen_at": UTC_NOW,
    }
    return pd.DataFrame([row | overrides])


# --------------------------------------------------------------------------- #
# Bronze
# --------------------------------------------------------------------------- #
def test_accepts_a_well_formed_capture() -> None:
    validated = validate_bronze(bronze_frame(), single_capture=True)
    assert len(validated) == 1


def test_bronze_rejects_unknown_vehicle_type() -> None:
    with pytest.raises(LayerValidationError):
        validate_bronze(bronze_frame(vehicle_type="truck"))


def test_bronze_rejects_a_malformed_listing_id() -> None:
    with pytest.raises(LayerValidationError):
        validate_bronze(bronze_frame(listing_id="12345"))


def test_bronze_rejects_extra_columns() -> None:
    """strict=True: an unexpected column means the scraper changed without the schema."""
    frame = bronze_frame()
    frame["seller_name"] = "Autama Hyundai"
    with pytest.raises(LayerValidationError):
        validate_bronze(frame)


def test_bronze_allows_missing_optional_strings() -> None:
    validated = validate_bronze(bronze_frame(mileage_raw=None, location_raw=None))
    assert validated["mileage_raw"].isna().all()


def test_bronze_allows_repeats_across_captures_but_not_within_one() -> None:
    frame = pd.concat([bronze_frame(), bronze_frame()], ignore_index=True)
    assert len(validate_bronze(frame)) == 2
    with pytest.raises(LayerValidationError):
        validate_bronze(frame, single_capture=True)


# --------------------------------------------------------------------------- #
# Silver
# --------------------------------------------------------------------------- #
def test_silver_keeps_flagged_rows() -> None:
    """Implausible prices survive into silver so data quality stays measurable."""
    frame = silver_frame(price_cop=1, is_valid=False, invalid_reason="price_too_low")
    assert len(validate_silver(frame)) == 1


def test_silver_rejects_inconsistent_validity_flags() -> None:
    with pytest.raises(LayerValidationError):
        validate_silver(silver_frame(is_valid=True, invalid_reason="price_too_low"))


def test_silver_rejects_last_seen_before_first_seen() -> None:
    earlier = UTC_NOW - pd.Timedelta(days=1)
    with pytest.raises(LayerValidationError):
        validate_silver(silver_frame(last_seen_at=earlier))


def test_silver_allows_missing_parsed_values() -> None:
    frame = silver_frame(price_cop=None, is_valid=False, invalid_reason="price_missing")
    assert validate_silver(frame)["price_cop"].isna().all()


# --------------------------------------------------------------------------- #
# Gold
# --------------------------------------------------------------------------- #
def test_gold_accepts_a_model_ready_row() -> None:
    assert len(validate_gold(gold_frame())) == 1


def test_gold_requires_one_row_per_listing() -> None:
    frame = pd.concat([gold_frame(), gold_frame()], ignore_index=True)
    with pytest.raises(LayerValidationError):
        validate_gold(frame)


def test_gold_rejects_missing_price() -> None:
    with pytest.raises(LayerValidationError):
        validate_gold(gold_frame(price_cop=None))


def test_gold_rejects_implausible_price() -> None:
    with pytest.raises(LayerValidationError):
        validate_gold(gold_frame(price_cop=500))


def test_gold_rejects_negative_age() -> None:
    with pytest.raises(LayerValidationError):
        validate_gold(gold_frame(vehicle_age_years=-1))
