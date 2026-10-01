from pathlib import Path

import pandas as pd
import pytest

from autovalor.models.dataset import (
    MIN_TEMPORAL_SPAN_DAYS,
    Dataset,
    SplitNotPossibleError,
    group_keys,
    load_gold,
    load_split,
    split_listings,
    temporal_span_days,
)

from .conftest import make_gold_frame


def test_split_holds_out_the_requested_share(gold_cars: pd.DataFrame) -> None:
    split = split_listings(gold_cars, test_size=0.2)

    assert split.n_train + split.n_test == len(gold_cars)
    # Whole groups move, so the holdout lands near the target rather than exactly on it.
    assert split.n_test == pytest.approx(len(gold_cars) * 0.2, abs=5)


def test_split_is_reproducible_for_a_seed(gold_cars: pd.DataFrame) -> None:
    first = split_listings(gold_cars, seed=123)
    second = split_listings(gold_cars, seed=123)

    assert first.test["listing_id"].tolist() == second.test["listing_id"].tolist()


def test_a_different_seed_moves_rows(gold_cars: pd.DataFrame) -> None:
    first = split_listings(gold_cars, seed=1)
    second = split_listings(gold_cars, seed=2)

    assert first.test["listing_id"].tolist() != second.test["listing_id"].tolist()


def test_train_and_test_never_share_a_listing(gold_cars: pd.DataFrame) -> None:
    split = split_listings(gold_cars)

    overlap = set(split.train["listing_id"]) & set(split.test["listing_id"])
    assert overlap == set()


def test_a_reposted_vehicle_stays_on_one_side() -> None:
    # This is the whole reason the split works on groups: a dealer reposting a vehicle
    # gets a new listing_id, and a row-wise split would leave its twin in training.
    frame = make_gold_frame(500, duplicate_rows=120)

    split = split_listings(frame)

    train_keys = set(group_keys(split.train))
    test_keys = set(group_keys(split.test))
    assert train_keys & test_keys == set()


def test_split_rejects_a_holdout_too_small_to_measure() -> None:
    frame = make_gold_frame(200)

    with pytest.raises(SplitNotPossibleError, match="below the 100"):
        split_listings(frame, test_size=0.1)


def test_split_rejects_an_impossible_test_size(gold_cars: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="test_size must be in"):
        split_listings(gold_cars, test_size=1.0)


def test_split_rejects_mixed_verticals(gold_cars: pd.DataFrame) -> None:
    mixed = pd.concat([gold_cars, make_gold_frame(600, vehicle_type="motorcycle")])

    with pytest.raises(ValueError, match="single vertical"):
        split_listings(mixed)


def test_temporal_split_refuses_a_single_capture_window(gold_cars: pd.DataFrame) -> None:
    # Today's lake: every row seen inside one scraping run. Failing loudly here is the
    # point — a "temporal" holdout over three hours would be a random split in disguise.
    assert temporal_span_days(gold_cars) == pytest.approx(0.0)

    with pytest.raises(SplitNotPossibleError, match="under the 14"):
        split_listings(gold_cars, strategy="temporal")


def test_temporal_split_holds_out_the_most_recent_rows() -> None:
    frame = make_gold_frame(600, days_span=MIN_TEMPORAL_SPAN_DAYS * 3)

    split = split_listings(frame, strategy="temporal")

    assert split.strategy == "temporal"
    assert split.cutoff is not None
    train_seen = pd.to_datetime(split.train["last_seen_at"], utc=True)
    assert train_seen.max() <= split.cutoff


def test_describe_reports_the_partition_parameters(gold_cars: pd.DataFrame) -> None:
    split = split_listings(gold_cars, seed=99)

    described = split.describe()
    assert described["split_strategy"] == "random"
    assert described["split_seed"] == 99
    assert described["split_cutoff"] is None
    assert described["n_test"] == split.n_test


def test_load_gold_reads_one_vertical(gold_duckdb: Path) -> None:
    frame = load_gold("motorcycle", duckdb_path=gold_duckdb)

    assert set(frame["vehicle_type"]) == {"motorcycle"}
    assert frame["listing_id"].is_monotonic_increasing


def test_load_gold_reports_a_missing_database(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="make transform"):
        load_gold("car", duckdb_path=tmp_path / "absent.duckdb")


def test_load_split_returns_a_partition(gold_duckdb: Path) -> None:
    split = load_split("car", duckdb_path=gold_duckdb)

    assert isinstance(split, Dataset)
    assert split.n_train > split.n_test > 0
