from pathlib import Path

import pandas as pd
import pytest

from autovalor.models.dataset import split_listings
from autovalor.models.train import (
    build_parser,
    format_table,
    main,
    run,
    train_baseline,
)


def test_a_baseline_reports_both_sides_of_the_split(gold_cars: pd.DataFrame) -> None:
    split = split_listings(gold_cars)

    result = train_baseline(split, "full")

    assert result.train_report.n == split.n_train
    assert result.test_report.n == split.n_test


def test_the_held_out_error_is_not_better_than_the_in_sample_one(
    gold_cars: pd.DataFrame,
) -> None:
    # The reason this module exists: an in-sample figure flatters the model, and the
    # fixture's law is simple enough that the ordering must hold.
    result = train_baseline(split_listings(gold_cars), "full")

    assert result.test_report.sigma_log >= result.train_report.sigma_log * 0.9


def test_the_full_feature_set_beats_the_basic_one(gold_cars: pd.DataFrame) -> None:
    split = split_listings(gold_cars)

    basic = train_baseline(split, "basic")
    full = train_baseline(split, "full")

    assert full.test_report.mape < basic.test_report.mape


def test_metrics_are_prefixed_by_the_split_they_came_from(gold_cars: pd.DataFrame) -> None:
    result = train_baseline(split_listings(gold_cars), "basic")

    metrics = result.metrics()
    assert "test_mape" in metrics
    assert "train_mape" in metrics
    assert metrics["test_mape"] != metrics["train_mape"]


def test_params_record_the_partition_and_the_model(gold_cars: pd.DataFrame) -> None:
    result = train_baseline(split_listings(gold_cars), "full")

    assert result.params["model"] == "hedonic_ols"
    assert result.params["feature_set"] == "full"
    assert result.params["split_strategy"] == "random"
    assert int(result.params["n_features"]) > 0  # type: ignore[call-overload]


def test_run_covers_every_vertical_and_feature_set(gold_duckdb: Path) -> None:
    results = run(duckdb_path=gold_duckdb, track=False)

    assert {(result.vehicle_type, result.feature_set) for result in results} == {
        ("car", "basic"),
        ("car", "full"),
        ("motorcycle", "basic"),
        ("motorcycle", "full"),
    }


def test_the_table_stays_ascii_for_a_cp1252_console(gold_cars: pd.DataFrame) -> None:
    table = format_table([train_baseline(split_listings(gold_cars), "full")])

    table.encode("cp1252")
    assert "MAPE out" in table


def test_the_cli_prints_the_table(
    gold_duckdb: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "--vehicle-type",
            "car",
            "--feature-set",
            "full",
            "--no-mlflow",
            "--duckdb-path",
            str(gold_duckdb),
        ]
    )

    assert exit_code == 0
    assert "MAPE out" in capsys.readouterr().out


def test_the_cli_fails_cleanly_without_a_lake(tmp_path: Path) -> None:
    exit_code = main(["--no-mlflow", "--duckdb-path", str(tmp_path / "absent.duckdb")])

    assert exit_code == 1


def test_the_cli_fails_cleanly_when_a_temporal_split_is_impossible(gold_duckdb: Path) -> None:
    exit_code = main(["--split", "temporal", "--no-mlflow", "--duckdb-path", str(gold_duckdb)])

    assert exit_code == 1


def test_the_parser_defaults_to_both_verticals_and_tracking_on() -> None:
    args = build_parser().parse_args([])

    assert args.vehicle_type is None
    assert args.feature_set is None
    assert args.no_mlflow is False
    assert args.split == "random"
