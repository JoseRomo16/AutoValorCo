from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from autovalor.analysis.price_index import (
    BASE_VALUE,
    MIN_INDEX_SPAN_DAYS,
    MIN_LISTINGS_PER_PERIOD,
    IndexNotPossibleError,
    assign_periods,
    capture_span_days,
    check_publishable,
    deflate,
    hedonic_index,
    load_cpi,
    publishable_from,
)

from .conftest import make_gold_frame

MONTHS = 7
"""Enough months that the span clears MIN_INDEX_SPAN_DAYS, which six would not."""

PER_MONTH = 400
MONTHLY_DRIFT = 0.02
"""The trend planted in the synthetic lake: 2 % per month, compounding in log space."""


def make_dated_frame(
    *,
    months: int = MONTHS,
    per_month: int = PER_MONTH,
    drift: float = MONTHLY_DRIFT,
    vehicle_type: str = "car",
) -> pd.DataFrame:
    """Return a lake spread over several months, with a known price trend planted in it.

    Every month draws the same kind of vehicles — same brands, same age law — and the only
    thing that changes over time is a proportional shift in price. An index that works has
    to find exactly that shift; one that is really measuring the mix will not, because the
    mix does not move here.
    """
    start = datetime(2026, 1, 15, tzinfo=UTC)
    parts: list[pd.DataFrame] = []
    for month in range(months):
        part = make_gold_frame(per_month, vehicle_type=vehicle_type, seed=100 + month)
        part["listing_id"] = [f"MCO-{month:02d}-{index:06d}" for index in range(len(part))]
        seen = start + timedelta(days=31 * month)
        part["first_seen_at"] = seen
        part["last_seen_at"] = seen
        part["price_cop"] = (part["price_cop"] * np.exp(drift * month)).round()
        part["log_price"] = np.log(part["price_cop"])
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def test_periods_come_from_when_the_listing_was_last_seen() -> None:
    frame = make_dated_frame(months=2, per_month=50)

    periods = assign_periods(frame)

    assert set(periods) == {"2026-01", "2026-02"}


def test_a_short_lake_refuses_to_produce_an_index(cars: pd.DataFrame) -> None:
    # Today's lake spans days, not months. The refusal is the feature.
    assert capture_span_days(cars) < MIN_INDEX_SPAN_DAYS

    with pytest.raises(IndexNotPossibleError, match="under the 180"):
        check_publishable(cars)


def test_the_refusal_says_when_it_will_be_possible(cars: pd.DataFrame) -> None:
    # A bare "not enough data" sends someone to read the source; a date does not.
    reached = publishable_from(cars)
    first_seen = pd.to_datetime(cars["last_seen_at"], utc=True).min()

    assert (reached - first_seen).days == MIN_INDEX_SPAN_DAYS
    with pytest.raises(IndexNotPossibleError, match=str(reached.date())):
        check_publishable(cars)


def test_a_long_enough_lake_passes_the_check() -> None:
    # No assertion to make beyond "this does not raise", which is the whole contract.
    check_publishable(make_dated_frame())


def test_the_index_recovers_the_planted_trend() -> None:
    index = hedonic_index(make_dated_frame(), vehicle_type="car")

    assert len(index) == MONTHS
    assert index["index_nominal"].iloc[0] == pytest.approx(BASE_VALUE)
    # The planted drift compounds in log space, so the last period is exp(drift * steps).
    expected = BASE_VALUE * np.exp(MONTHLY_DRIFT * (MONTHS - 1))
    assert index["index_nominal"].iloc[-1] == pytest.approx(expected, rel=0.02)


def test_the_index_rises_monotonically_when_the_trend_does() -> None:
    index = hedonic_index(make_dated_frame(), vehicle_type="car")

    assert (np.diff(index["index_nominal"].to_numpy()) > 0).all()


def test_the_base_period_is_fixed_at_a_hundred_with_no_interval() -> None:
    index = hedonic_index(make_dated_frame(), vehicle_type="car")
    base = index[index["is_base"]]

    assert len(base) == 1
    assert base["index_nominal"].iloc[0] == pytest.approx(BASE_VALUE)
    assert base["index_ci_low"].iloc[0] == pytest.approx(BASE_VALUE)


def test_a_flat_market_produces_a_flat_index() -> None:
    index = hedonic_index(make_dated_frame(drift=0.0), vehicle_type="car")

    assert index["index_nominal"].to_numpy() == pytest.approx(BASE_VALUE, abs=2.0)


def test_thin_periods_are_dropped_rather_than_pooled() -> None:
    frame = make_dated_frame(months=3)
    thin = frame[frame["last_seen_at"] != frame["last_seen_at"].unique()[1]]
    kept = frame[frame["last_seen_at"] == frame["last_seen_at"].unique()[1]].head(10)
    frame = pd.concat([thin, kept], ignore_index=True)

    index = hedonic_index(frame, vehicle_type="car", enforce_span=False)

    assert len(index) == 2
    assert (index["listings"] >= MIN_LISTINGS_PER_PERIOD).all()


def test_one_usable_period_is_not_an_index() -> None:
    with pytest.raises(IndexNotPossibleError, match="at least two"):
        hedonic_index(make_dated_frame(months=1), vehicle_type="car", enforce_span=False)


def test_the_cpi_file_says_what_to_do_when_it_is_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="DANE"):
        load_cpi(tmp_path / "nope.csv")


def test_a_malformed_cpi_file_fails_loudly(tmp_path: Path) -> None:
    path = tmp_path / "ipc.csv"
    path.write_text("mes,valor\n2026-01,100\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing the columns"):
        load_cpi(path)


def test_the_cpi_file_is_read_as_a_series(tmp_path: Path) -> None:
    path = tmp_path / "ipc.csv"
    path.write_text("period,cpi\n2026-02,101.0\n2026-01,100.0\n", encoding="utf-8")

    cpi = load_cpi(path)

    assert list(cpi.index) == ["2026-01", "2026-02"]
    assert cpi["2026-02"] == pytest.approx(101.0)


def test_deflating_by_the_same_trend_leaves_a_flat_real_index() -> None:
    # Prices rose 2 % a month and so did everything else: in real terms nothing happened,
    # and an index that still reported +10 % would be describing inflation as a car market.
    index = hedonic_index(make_dated_frame(), vehicle_type="car")
    cpi = pd.Series(
        {
            period: 100.0 * np.exp(MONTHLY_DRIFT * step)
            for step, period in enumerate(index["period"])
        }
    )

    deflated = deflate(index, cpi)

    assert deflated["index_real"].to_numpy() == pytest.approx(BASE_VALUE, abs=2.0)
    assert deflated["index_nominal"].iloc[-1] > BASE_VALUE + 5


def test_a_period_without_a_cpi_value_is_null_not_assumed() -> None:
    index = hedonic_index(make_dated_frame(months=3), vehicle_type="car", enforce_span=False)
    cpi = pd.Series({index["period"].iloc[0]: 100.0, index["period"].iloc[1]: 102.0})

    deflated = deflate(index, cpi)

    assert np.isnan(deflated["index_real"].iloc[2])
    assert not np.isnan(deflated["index_real"].iloc[1])


def test_a_base_period_without_a_cpi_value_is_an_error() -> None:
    index = hedonic_index(make_dated_frame(months=3), vehicle_type="car", enforce_span=False)
    cpi = pd.Series({index["period"].iloc[1]: 102.0})

    with pytest.raises(ValueError, match="no CPI value"):
        deflate(index, cpi)
