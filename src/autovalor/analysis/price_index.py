"""A hedonic price index for used vehicles, deflated with the DANE CPI.

The question is "did used cars get more expensive this month", and the obvious answer —
compare the median asking price — answers a different one. A median moves when the *mix*
moves: a month with more pickups and fewer hatchbacks looks like inflation. What is wanted
is the price of a **constant-quality** vehicle over time, which is what a hedonic index with
period fixed effects estimates: regress ``log(price)`` on the vehicle's attributes plus a
dummy per period, and the period coefficients are the price movement with the mix held
fixed. ``exp(beta_t)`` against the base period, times 100, is the index.

**Nominal and real are both reported.** A used-vehicle index that rises 6 % in a year when
everything else rose 7 % describes a market getting *cheaper* in real terms, and saying only
"+6 %" would invert the finding. Deflating needs the consumer price index, which in Colombia
is the DANE's IPC — public, free, and the reason :data:`CPI_FILE` is a file the project
reads rather than a service it pays for.

**The CPI file is not shipped with the repository.** DANE publishes the series on its site
but not at a stable machine-readable URL, and inventing index values to fill a committed
file would be worse than having none: every real figure downstream would inherit numbers
nobody can source. :func:`load_cpi` reads the two-column CSV described in its docstring, and
``docs/results/README.md`` records where to get it. Without the file the nominal index still
works and says so.

**This index does not run yet, by design.** It needs captures spread over time, and a lot
more of them than a temporal train/test split does: a period effect estimated from two weeks
is measuring a fortnight's noise. :func:`check_publishable` refuses below
:data:`MIN_INDEX_SPAN_DAYS` and names the date the lake would reach it, so the refusal is
informative rather than a bare exception. As of the lake this module was written against —
5,5 days — that date is in 2027.
"""

import logging
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from autovalor.analysis.inference import (
    AGE_SQUARED,
    LOG_MILEAGE,
    fit_ols,
    pool_rare,
    prepare,
)
from autovalor.models.dataset import VehicleType

logger = logging.getLogger("autovalor.analysis")

PERIOD_COLUMN = "period"
PERIOD_FREQ = "M"
"""Monthly periods. The product promises a *monthly* index, and a weekly one over this
sample size would report noise at a higher resolution."""

MIN_INDEX_SPAN_DAYS = 180
"""Days of capture history before an index means anything — six months, i.e. six points.

Far above the 14 days a temporal split needs, and for a different reason: a split only has
to separate past from future, while an index has to describe a *trajectory*. Two or three
points cannot distinguish a trend from the noise of two particular weeks.
"""

MIN_LISTINGS_PER_PERIOD = 200
"""Listings a period needs to carry its own dummy. Below it the period effect is an average
over too few vehicles and moves with whichever ones happened to be listed."""

MIN_VEHICLE_LISTINGS = 20
MIN_DEPARTMENT_LISTINGS = 30
"""Pooling thresholds for the quality controls, as in :mod:`autovalor.analysis.regional`."""

BASE_VALUE = 100.0
"""The base period's index value, by convention."""

CPI_FILE = Path("data/reference/ipc_dane.csv")
"""Default location of the DANE CPI series. See :func:`load_cpi` for the format."""


class IndexNotPossibleError(RuntimeError):
    """Raised when the lake cannot support an honest index yet."""


def assign_periods(frame: pd.DataFrame, *, freq: str = PERIOD_FREQ) -> pd.Series:
    """Label each listing with the period it was last seen in.

    ``last_seen_at`` rather than ``first_seen_at``: the index is about the price being asked
    during a period, and a listing that has been up for three months is asking its current
    price now.

    Args:
        frame: Gold rows.
        freq: Pandas period frequency.

    Returns:
        One period label per row, as a string like ``2026-10``.
    """
    # Dropped to naive UTC before the conversion: a period has no timezone, and pandas warns
    # rather than silently discarding one.
    seen = pd.to_datetime(frame["last_seen_at"], utc=True).dt.tz_localize(None)
    return seen.dt.to_period(freq).astype(str)


def capture_span_days(frame: pd.DataFrame) -> float:
    """Return the spread of ``last_seen_at`` in days."""
    seen = pd.to_datetime(frame["last_seen_at"], utc=True)
    span: pd.Timedelta = seen.max() - seen.min()
    return float(span / pd.Timedelta(days=1))


def publishable_from(frame: pd.DataFrame) -> pd.Timestamp:
    """Return the date the lake will have enough history for an index.

    Args:
        frame: Gold rows.

    Returns:
        The earliest ``last_seen_at`` plus :data:`MIN_INDEX_SPAN_DAYS`, which is when the
        weekly captures will have accumulated the required span on their own.
    """
    seen = pd.to_datetime(frame["last_seen_at"], utc=True)
    return pd.Timestamp(seen.min() + timedelta(days=MIN_INDEX_SPAN_DAYS))


def check_publishable(frame: pd.DataFrame) -> None:
    """Raise unless the lake spans enough time for an index.

    Args:
        frame: Gold rows.

    Raises:
        IndexNotPossibleError: If the span is under :data:`MIN_INDEX_SPAN_DAYS`, with the
            date it would be reached.
    """
    span = capture_span_days(frame)
    if span < MIN_INDEX_SPAN_DAYS:
        reached = publishable_from(frame).date()
        msg = (
            f"the lake spans {span:.1f} days, under the {MIN_INDEX_SPAN_DAYS} an index "
            f"needs; the weekly captures reach it on {reached}"
        )
        raise IndexNotPossibleError(msg)


def hedonic_index(
    frame: pd.DataFrame,
    *,
    vehicle_type: VehicleType,
    freq: str = PERIOD_FREQ,
    enforce_span: bool = True,
) -> pd.DataFrame:
    """Estimate the constant-quality price index of one vertical.

    Args:
        frame: Gold rows for one vertical.
        vehicle_type: Vertical being indexed.
        freq: Period frequency.
        enforce_span: Whether to refuse a lake too short to index. Turned off only by the
            tests, which plant a known trend in synthetic data.

    Returns:
        One row per period, in order: the nominal index with the base period at
        :data:`BASE_VALUE`, its confidence interval, the period-on-period change and the
        listings behind it.

    Raises:
        IndexNotPossibleError: If the lake is too short, or if fewer than two periods
            clear :data:`MIN_LISTINGS_PER_PERIOD`.
    """
    if enforce_span:
        check_publishable(frame)

    prepared = prepare(frame)
    prepared[PERIOD_COLUMN] = assign_periods(frame, freq=freq)

    counts = prepared[PERIOD_COLUMN].value_counts()
    periods = sorted(str(period) for period in counts[counts >= MIN_LISTINGS_PER_PERIOD].index)
    if len(periods) < 2:
        msg = (
            f"{vehicle_type} has {len(periods)} period(s) with at least "
            f"{MIN_LISTINGS_PER_PERIOD} listings; an index needs at least two"
        )
        raise IndexNotPossibleError(msg)

    # Thin periods are dropped rather than pooled: pooling two months into one dummy would
    # produce an index point that belongs to no month.
    indexed = prepared[prepared[PERIOD_COLUMN].isin(periods)].copy()
    indexed["vehicle_group"] = pool_rare(
        (indexed["brand"] + " " + indexed["model"]).rename("brand and model"),
        min_count=MIN_VEHICLE_LISTINGS,
    )
    indexed["department_group"] = pool_rare(
        indexed["department"], min_count=MIN_DEPARTMENT_LISTINGS
    )

    base = periods[0]
    formula = (
        f"C({PERIOD_COLUMN}, Treatment(reference='{base}')) "
        f"+ vehicle_age_years + {AGE_SQUARED} + {LOG_MILEAGE} + engine_cc + engine_cc_missing "
        "+ C(vehicle_group) + C(department_group) + is_official_store"
    )
    results = fit_ols(indexed, formula)

    rows: list[dict[str, object]] = []
    for period in periods:
        if period == base:
            estimate, low, high = 0.0, 0.0, 0.0
        else:
            term = f"C({PERIOD_COLUMN}, Treatment(reference='{base}'))[T.{period}]"
            estimate = float(results.params[term])
            interval = results.conf_int().loc[term]
            low, high = float(interval.iloc[0]), float(interval.iloc[1])
        rows.append(
            {
                "vehicle_type": vehicle_type,
                "period": period,
                "is_base": period == base,
                "listings": int(counts[period]),
                "index_nominal": BASE_VALUE * float(np.exp(estimate)),
                "index_ci_low": BASE_VALUE * float(np.exp(low)),
                "index_ci_high": BASE_VALUE * float(np.exp(high)),
                "log_effect": estimate,
            }
        )

    index = pd.DataFrame(rows)
    index["change_pct"] = index["index_nominal"].pct_change() * 100.0
    logger.info(
        "%s index — %d periods from %s, nominal %.1f to %.1f (base %s = %.0f)",
        vehicle_type,
        len(index),
        base,
        index["index_nominal"].iloc[0],
        index["index_nominal"].iloc[-1],
        base,
        BASE_VALUE,
    )
    return index


def load_cpi(path: Path = CPI_FILE) -> pd.Series:
    """Read the DANE CPI series.

    The file is a two-column CSV with a header, ``period,cpi``, one row per month::

        period,cpi
        2026-09,142.37
        2026-10,142.91

    ``period`` matches the labels :func:`assign_periods` produces, and ``cpi`` is the index
    level — any base, since only ratios are used. The DANE publishes this under *Índice de
    Precios al Consumidor (IPC)*; it is free and public, but not behind a stable
    machine-readable URL, so the file is downloaded by hand and committed.

    Args:
        path: CSV to read.

    Returns:
        The CPI level indexed by period label, sorted.

    Raises:
        FileNotFoundError: If the file is not there, with what to do about it.
        ValueError: If the columns are not the two expected ones.
    """
    if not path.exists():
        msg = (
            f"{path} does not exist. Download the monthly IPC series from the DANE "
            "(estadisticas-por-tema > precios y costos > IPC) and save it as a CSV with "
            "the columns period,cpi — see load_cpi's docstring for the exact shape"
        )
        raise FileNotFoundError(msg)

    frame = pd.read_csv(path, dtype={"period": str})
    missing = {"period", "cpi"} - set(frame.columns)
    if missing:
        msg = f"{path} is missing the columns {sorted(missing)}"
        raise ValueError(msg)

    series = frame.set_index("period")["cpi"].astype("float64").sort_index()
    series.name = "cpi"
    logger.info("loaded %d CPI periods from %s", len(series), path)
    return series


def deflate(index: pd.DataFrame, cpi: pd.Series) -> pd.DataFrame:
    """Add the real (CPI-deflated) index beside the nominal one.

    The real index divides the nominal one by how much the general price level moved over
    the same stretch, both measured against the base period. A real index above 100 means
    used vehicles outpaced inflation; below it, they lagged.

    Args:
        index: Output of :func:`hedonic_index`.
        cpi: CPI levels by period, from :func:`load_cpi`.

    Returns:
        A copy with ``cpi``, ``index_real`` and ``real_change_pct`` added. Periods with no
        CPI value get NaN rather than an assumed one.

    Raises:
        ValueError: If the base period has no CPI value, which would leave every real
            figure undefined.
    """
    deflated = index.copy()
    deflated["cpi"] = deflated["period"].map(cpi)

    base_rows = deflated[deflated["is_base"]]
    base_cpi = float(base_rows["cpi"].iloc[0]) if not base_rows.empty else float("nan")
    if not np.isfinite(base_cpi):
        base_period = base_rows["period"].iloc[0] if not base_rows.empty else "unknown"
        msg = f"the base period {base_period} has no CPI value; the real index is undefined"
        raise ValueError(msg)

    deflated["index_real"] = deflated["index_nominal"] * (base_cpi / deflated["cpi"])
    deflated["real_change_pct"] = deflated["index_real"].pct_change() * 100.0
    return deflated
