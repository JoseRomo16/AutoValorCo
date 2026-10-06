"""Loading the gold layer and partitioning it into train and test sets.

Every quality figure produced before this module existed was in-sample: an OLS fitted
and scored on the same rows. This module defines the partition that all later numbers
are measured against, so it is deliberately the first piece of F2.

Two split strategies live here:

``random``
    Shuffle listings with a fixed seed. Correct while the lake holds a single capture
    window, which is the case today.
``temporal``
    Hold out the most recently seen listings. This is what the monthly price index
    ultimately requires — a model must never be scored on rows it could have seen in
    the future — but it needs captures spread over time, so it stays unavailable until
    the weekly workflow has accumulated :data:`MIN_TEMPORAL_SPAN_DAYS` of history.

Examples:
    >>> frame = load_gold("car")                       # doctest: +SKIP
    >>> split = split_listings(frame, strategy="random")  # doctest: +SKIP
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

import duckdb
import pandas as pd

from autovalor.config import get_settings

logger = logging.getLogger("autovalor.models")

GOLD_TABLE = "main_gold.gold_listings"
"""Model-ready table written by dbt; see ``dbt/models/gold/gold_listings.sql``."""

VehicleType = Literal["car", "motorcycle"]
"""Verticals are modeled separately: a 125 cc motorcycle and a sedan share no price curve."""

VEHICLE_TYPES: tuple[VehicleType, ...] = get_args(VehicleType)

SplitStrategy = Literal["random", "temporal"]

DEFAULT_TEST_SIZE = 0.2
"""Fraction of listings held out. 20 % of the smaller vertical is ~750 rows, enough to
separate a 15 % MAPE from an 18 % one."""

DEFAULT_SEED = 20260930
"""Fixed so that a rerun compares models, not partitions."""

MIN_TEMPORAL_SPAN_DAYS = 14
"""Minimum spread of ``last_seen_at`` before a temporal holdout means anything. Below
this the cutoff would separate hours, not market movement."""

MIN_TEST_ROWS = 100
"""Below this a MAPE is too noisy to compare two models; refuse rather than mislead."""

DUPLICATE_KEY_COLUMNS = ("title", "model_year", "mileage_km")
"""Columns that identify the same physical vehicle across listings.

``silver_listings`` collapses repetitions of one ``listing_id``, but a dealer reposting a
vehicle gets a new id, and roughly 7 % of car rows belong to such a group. Splitting by
row would leave a near-identical twin on the other side of the partition and quietly
flatter the holdout, so the split moves whole groups instead.
"""


class SplitNotPossibleError(RuntimeError):
    """Raised when the requested strategy cannot produce an honest partition."""


@dataclass(frozen=True)
class Dataset:
    """A train/test partition of one vertical, plus how it was produced.

    Attributes:
        vehicle_type: Vertical these rows belong to.
        train: Rows used for fitting.
        test: Held-out rows, never seen during fitting or tuning.
        strategy: Strategy that produced the partition.
        seed: Seed used by the ``random`` strategy (``None`` for ``temporal``).
        cutoff: First ``last_seen_at`` in the test set, for ``temporal`` splits.
        n_groups: Distinct vehicle groups the rows collapsed into; see
            :data:`DUPLICATE_KEY_COLUMNS`.
    """

    vehicle_type: VehicleType
    train: pd.DataFrame
    test: pd.DataFrame
    strategy: SplitStrategy
    seed: int | None = None
    cutoff: pd.Timestamp | None = None
    n_groups: int = 0

    @property
    def n_train(self) -> int:
        """Number of training rows."""
        return len(self.train)

    @property
    def n_test(self) -> int:
        """Number of held-out rows."""
        return len(self.test)

    def describe(self) -> dict[str, object]:
        """Return the partition's parameters, for logging as MLflow run params."""
        return {
            "vehicle_type": self.vehicle_type,
            "split_strategy": self.strategy,
            "split_seed": self.seed,
            "split_cutoff": None if self.cutoff is None else self.cutoff.isoformat(),
            "n_train": self.n_train,
            "n_test": self.n_test,
            "n_groups": self.n_groups,
        }


def load_gold(
    vehicle_type: VehicleType,
    *,
    duckdb_path: Path | None = None,
) -> pd.DataFrame:
    """Read one vertical out of the gold table.

    Args:
        vehicle_type: Vertical to read.
        duckdb_path: Database written by dbt. Defaults to the configured path.

    Returns:
        One row per listing, ordered by ``listing_id`` so the frame is reproducible
        regardless of how DuckDB happened to lay the rows out.

    Raises:
        FileNotFoundError: If the database does not exist — the lake has to be built
            with ``make transform`` first.
        SplitNotPossibleError: If the vertical has no rows.
    """
    path = duckdb_path or get_settings().duckdb_path
    if not path.exists():
        msg = f"{path} does not exist; run `make transform` to build the lake first"
        raise FileNotFoundError(msg)

    with duckdb.connect(str(path), read_only=True) as con:
        frame = con.execute(
            f"select * from {GOLD_TABLE} where vehicle_type = ? order by listing_id",
            [vehicle_type],
        ).df()

    if frame.empty:
        msg = f"gold holds no {vehicle_type} rows"
        raise SplitNotPossibleError(msg)

    logger.info("loaded %d %s listings from %s", len(frame), vehicle_type, path)
    return frame


def temporal_span_days(frame: pd.DataFrame) -> float:
    """Return the spread of ``last_seen_at`` in days.

    Args:
        frame: Gold rows.

    Returns:
        Days between the earliest and latest ``last_seen_at``. Zero for a single
        capture window.
    """
    seen = pd.to_datetime(frame["last_seen_at"], utc=True)
    span: pd.Timedelta = seen.max() - seen.min()
    return float(span / pd.Timedelta(days=1))


def split_listings(
    frame: pd.DataFrame,
    *,
    strategy: SplitStrategy = "random",
    test_size: float = DEFAULT_TEST_SIZE,
    seed: int = DEFAULT_SEED,
) -> Dataset:
    """Partition a vertical into train and test.

    Args:
        frame: Gold rows for a single vertical, as returned by :func:`load_gold`.
        strategy: ``random`` or ``temporal``; see the module docstring.
        test_size: Fraction of rows held out, exclusive of 0 and 1.
        seed: Seed for the ``random`` strategy.

    Returns:
        The partition and the parameters that produced it.

    Raises:
        ValueError: If ``test_size`` is not strictly between 0 and 1, or the frame
            mixes verticals.
        SplitNotPossibleError: If the holdout would be smaller than
            :data:`MIN_TEST_ROWS`, or a temporal split is asked of data that spans
            less than :data:`MIN_TEMPORAL_SPAN_DAYS`.
    """
    if not 0.0 < test_size < 1.0:
        msg = f"test_size must be in (0, 1), got {test_size}"
        raise ValueError(msg)

    verticals = set(frame["vehicle_type"].unique())
    if len(verticals) != 1:
        msg = f"expected a single vertical, got {sorted(verticals)}"
        raise ValueError(msg)
    vehicle_type: VehicleType = frame["vehicle_type"].iloc[0]

    n_test = round(len(frame) * test_size)
    if n_test < MIN_TEST_ROWS:
        msg = (
            f"a {test_size:.0%} holdout of {len(frame)} {vehicle_type} rows is "
            f"{n_test} rows, below the {MIN_TEST_ROWS} needed for a usable metric"
        )
        raise SplitNotPossibleError(msg)

    if strategy == "temporal":
        return _temporal_split(frame, vehicle_type, n_test)
    return _random_split(frame, vehicle_type, n_test, seed)


def group_keys(frame: pd.DataFrame) -> pd.Series:
    """Return a per-row key identifying the same physical vehicle.

    Args:
        frame: Gold rows.

    Returns:
        A string key built from :data:`DUPLICATE_KEY_COLUMNS`. Rows sharing a key are
        treated as one unit by the splitters.
    """
    parts = [frame[column].astype(str).fillna("") for column in DUPLICATE_KEY_COLUMNS]
    return pd.Series(["␟".join(values) for values in zip(*parts, strict=True)], index=frame.index)


def _take_groups(
    frame: pd.DataFrame,
    keys: pd.Series,
    ordered_keys: Sequence[str],
    n_test: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Assign whole groups to the holdout, following ``ordered_keys``, until it fills.

    Args:
        frame: Gold rows.
        keys: Group key per row, aligned with ``frame``.
        ordered_keys: Distinct keys in the order they should enter the holdout.
        n_test: Target holdout size in rows.

    Returns:
        The train and test frames, each with a fresh index.
    """
    sizes = keys.value_counts()
    chosen: list[str] = []
    taken = 0
    for key in ordered_keys:
        if taken >= n_test:
            break
        chosen.append(key)
        taken += int(sizes[key])

    in_test = keys.isin(set(chosen))
    test = frame.loc[in_test].reset_index(drop=True)
    train = frame.loc[~in_test].reset_index(drop=True)
    return train, test


def _random_split(
    frame: pd.DataFrame,
    vehicle_type: VehicleType,
    n_test: int,
    seed: int,
) -> Dataset:
    """Shuffle vehicle groups with a fixed seed and slice off the holdout."""
    keys = group_keys(frame)
    shuffled_keys = keys.drop_duplicates().sample(frac=1.0, random_state=seed).tolist()
    train, test = _take_groups(frame, keys, shuffled_keys, n_test)
    logger.info(
        "random split of %s: %d train / %d test over %d vehicle groups (seed %d)",
        vehicle_type,
        len(train),
        len(test),
        len(shuffled_keys),
        seed,
    )
    return Dataset(
        vehicle_type=vehicle_type,
        train=train,
        test=test,
        strategy="random",
        seed=seed,
        n_groups=len(shuffled_keys),
    )


def _temporal_split(frame: pd.DataFrame, vehicle_type: VehicleType, n_test: int) -> Dataset:
    """Hold out the most recently seen listings.

    Raises:
        SplitNotPossibleError: If the capture history is too narrow to split on time.
    """
    span = temporal_span_days(frame)
    if span < MIN_TEMPORAL_SPAN_DAYS:
        msg = (
            f"{vehicle_type} rows span {span:.2f} days of last_seen_at, under the "
            f"{MIN_TEMPORAL_SPAN_DAYS} needed for a temporal holdout; use "
            "strategy='random' until the weekly capture has accumulated history"
        )
        raise SplitNotPossibleError(msg)

    keys = group_keys(frame)
    # A reposted vehicle belongs wholly to the later side, so the holdout stays strictly
    # "what the market did after the cutoff".
    latest_per_group = (
        pd.to_datetime(frame["last_seen_at"], utc=True).groupby(keys).max().sort_values()
    )
    newest_first = latest_per_group.index[::-1].tolist()
    train, test = _take_groups(frame, keys, newest_first, n_test)

    cutoff = pd.to_datetime(test["last_seen_at"], utc=True).min()
    logger.info(
        "temporal split of %s at %s: %d train / %d test over %d vehicle groups",
        vehicle_type,
        cutoff.isoformat(),
        len(train),
        len(test),
        len(latest_per_group),
    )
    return Dataset(
        vehicle_type=vehicle_type,
        train=train,
        test=test,
        strategy="temporal",
        cutoff=cutoff,
        n_groups=len(latest_per_group),
    )


def load_split(
    vehicle_type: VehicleType,
    *,
    strategy: SplitStrategy = "random",
    test_size: float = DEFAULT_TEST_SIZE,
    seed: int = DEFAULT_SEED,
    duckdb_path: Path | None = None,
    only_enriched: bool = False,
) -> Dataset:
    """Load a vertical from gold and partition it in one call.

    Args:
        vehicle_type: Vertical to model.
        strategy: ``random`` or ``temporal``.
        test_size: Fraction of rows held out.
        seed: Seed for the ``random`` strategy.
        duckdb_path: Database written by dbt. Defaults to the configured path.
        only_enriched: Keep only listings that have a detail row. This is what makes a
            with-and-without comparison of the detail features honest: both fits then see
            exactly the same rows, so the difference is attributable to the features and
            not to a different population.

    Returns:
        The train/test partition for that vertical.

    Raises:
        SplitNotPossibleError: If ``only_enriched`` leaves no rows.
    """
    frame = load_gold(vehicle_type, duckdb_path=duckdb_path)
    if only_enriched:
        frame = frame.loc[frame["has_detail"].fillna(False)].reset_index(drop=True)
        if frame.empty:
            msg = f"no {vehicle_type} listing has been enriched yet; run the enrichment first"
            raise SplitNotPossibleError(msg)
        logger.info("kept %d enriched %s listings", len(frame), vehicle_type)
    return split_listings(frame, strategy=strategy, test_size=test_size, seed=seed)
