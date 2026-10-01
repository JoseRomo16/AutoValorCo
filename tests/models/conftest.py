"""Synthetic gold-shaped data for the modeling tests.

The fixtures build a lake-shaped frame with a known price law, so a test can assert that
a model recovers it rather than asserting a magic number produced by a previous run.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

BRANDS = ("Chevrolet", "Renault", "Mazda", "Toyota")
MODELS = ("spark", "sandero", "cx30", "corolla")
DEPARTMENTS = ("Antioquia", "Bogota D.C.", "Valle del Cauca")

BASE_LOG_PRICE = 17.5
AGE_EFFECT = -0.08
MILEAGE_EFFECT = -0.05


def make_gold_frame(
    n: int = 400,
    *,
    vehicle_type: str = "car",
    seed: int = 7,
    duplicate_rows: int = 0,
    days_span: float = 0.0,
) -> pd.DataFrame:
    """Return a gold-shaped frame whose log price follows a known linear law.

    Args:
        n: Number of distinct vehicles.
        vehicle_type: Vertical to label the rows with.
        seed: Seed for the synthetic draws.
        duplicate_rows: How many rows to repost under a new ``listing_id``, keeping the
            vehicle identity identical — the leakage case the grouped split exists for.
        days_span: Spread of ``last_seen_at`` in days; ``0`` reproduces today's lake,
            where every row comes from one capture window.

    Returns:
        A frame with the columns ``gold_listings`` exposes.
    """
    rng = np.random.default_rng(seed)
    start = datetime(2026, 9, 30, 1, 0, tzinfo=UTC)

    age = rng.integers(0, 20, size=n)
    mileage = rng.integers(0, 250_000, size=n)
    brand_index = rng.integers(0, len(BRANDS), size=n)
    log_price = (
        BASE_LOG_PRICE
        + AGE_EFFECT * age
        + MILEAGE_EFFECT * np.log1p(mileage)
        + 0.1 * brand_index
        + rng.normal(0, 0.05, size=n)
    )
    seen = [start + timedelta(days=float(offset)) for offset in rng.uniform(0, days_span, size=n)]

    frame = pd.DataFrame(
        {
            "listing_id": [f"MCO-{index:06d}" for index in range(n)],
            "source_url": [f"https://carro.tucarro.com.co/MCO-{index:06d}" for index in range(n)],
            "vehicle_type": vehicle_type,
            "title": [f"{BRANDS[i]} {MODELS[i]} 2020 {j}" for j, i in enumerate(brand_index)],
            "brand": [BRANDS[i] for i in brand_index],
            "model": [MODELS[i] for i in brand_index],
            "engine_cc": rng.choice([1000, 1400, 1600, None], size=n),
            "is_quad": False,
            "price_cop": np.exp(log_price).round().astype("int64"),
            "log_price": log_price,
            "model_year": 2026 - age,
            "vehicle_age_years": age,
            "mileage_km": mileage,
            "km_per_year": mileage / np.maximum(age, 1),
            "city": "Medellin",
            "department": [DEPARTMENTS[i % len(DEPARTMENTS)] for i in range(n)],
            "is_official_store": rng.random(size=n) > 0.7,
            "first_seen_at": seen,
            "last_seen_at": seen,
        }
    )
    # log_price must stay the exact log of the stored integer price, as in gold.
    frame["log_price"] = np.log(frame["price_cop"])

    if duplicate_rows:
        reposted = frame.iloc[:duplicate_rows].copy()
        reposted["listing_id"] = [f"MCO-repost-{index:06d}" for index in range(duplicate_rows)]
        frame = pd.concat([frame, reposted], ignore_index=True)

    return frame.sort_values("listing_id").reset_index(drop=True)


@pytest.fixture
def gold_cars() -> pd.DataFrame:
    """A car vertical large enough to clear the minimum holdout size."""
    return make_gold_frame(600, vehicle_type="car")


@pytest.fixture
def gold_duckdb(tmp_path: Path, gold_cars: pd.DataFrame) -> Path:
    """Write a gold-shaped table to a temporary DuckDB file and return its path."""
    path = tmp_path / "autovalor.duckdb"
    bikes = make_gold_frame(600, vehicle_type="motorcycle", seed=11)
    listings = pd.concat([gold_cars, bikes], ignore_index=True)
    with duckdb.connect(str(path)) as con:
        con.execute("create schema if not exists main_gold")
        con.register("listings", listings)
        con.execute("create table main_gold.gold_listings as select * from listings")
    return path
