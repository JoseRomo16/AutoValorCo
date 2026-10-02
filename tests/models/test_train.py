from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from autovalor.models import train as train_module
from autovalor.models.dataset import split_listings
from autovalor.models.train import (
    MODEL_KINDS,
    build_parser,
    format_table,
    main,
    run,
    train_baseline,
    train_model,
)
from autovalor.models.tuning import SearchResult


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

    assert result.params["model"] == "hedonic"
    assert result.params["variant"] == "full"
    assert result.params["split_strategy"] == "random"
    assert int(result.params["n_features"]) > 0  # type: ignore[call-overload]


def test_run_covers_every_vertical_and_feature_set(gold_duckdb: Path) -> None:
    results = run(duckdb_path=gold_duckdb, model_kinds=("hedonic",), track=False)

    assert {(result.vehicle_type, result.variant) for result in results} == {
        ("car", "basic"),
        ("car", "full"),
        ("motorcycle", "basic"),
        ("motorcycle", "full"),
    }


def test_run_expands_feature_sets_only_for_the_baseline(gold_duckdb: Path) -> None:
    # The trees take the full tree specification; asking for two feature sets must not
    # fit them twice.
    results = run(
        duckdb_path=gold_duckdb,
        vehicle_types=("car",),
        model_kinds=("hedonic", "lightgbm"),
        n_trials=0,
        track=False,
    )

    kinds = [result.model_kind for result in results]
    assert kinds.count("hedonic") == 2
    assert kinds.count("lightgbm") == 1


def test_a_tree_without_a_search_reports_no_cv_score(gold_cars: pd.DataFrame) -> None:
    result = train_model(split_listings(gold_cars), "lightgbm", n_trials=0)

    assert result.variant == "default"
    assert result.cv_mape is None
    assert result.trials is None
    assert "cv_mape" not in result.metrics()


def test_the_search_never_sees_the_holdout(
    gold_cars: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The central claim of the tuning protocol, and the one nothing else would catch:
    # a holdout used to choose hyperparameters is a second training set, and the reported
    # MAPE goes back to being in-sample. Spy on the search to pin down what it receives.
    split = split_listings(gold_cars)
    received: list[pd.DataFrame] = []

    def spy(train: pd.DataFrame, **kwargs: Any) -> SearchResult:
        received.append(train)
        return SearchResult(
            model_kind=kwargs["model_kind"],
            vehicle_type=kwargs["vehicle_type"],
            best_params={"n_estimators": 20},
            cv_mape=0.2,
            n_trials=1,
            trials=pd.DataFrame({"number": [0]}),
        )

    monkeypatch.setattr(train_module, "search", spy)
    train_model(split, "lightgbm", n_trials=1)

    assert len(received) == 1
    passed = set(received[0]["listing_id"])
    assert passed == set(split.train["listing_id"])
    assert passed & set(split.test["listing_id"]) == set()


def test_a_tuned_tree_reports_its_cv_score(gold_cars: pd.DataFrame) -> None:
    result = train_model(split_listings(gold_cars), "lightgbm", n_trials=2)

    assert result.variant == "tuned"
    assert result.cv_mape is not None
    assert result.trials is not None
    assert result.metrics()["cv_mape"] == result.cv_mape


def test_the_table_marks_how_far_each_model_sits_from_the_baseline(
    gold_cars: pd.DataFrame,
) -> None:
    # This column is the F2 verdict: a tree only earns its complexity by coming in below
    # the baseline.
    split = split_listings(gold_cars)
    results = [train_baseline(split, "full"), train_model(split, "lightgbm", n_trials=0)]

    table = format_table(results)

    assert "base" in table
    assert "pt" in table


def test_the_table_handles_a_run_without_the_baseline(gold_cars: pd.DataFrame) -> None:
    table = format_table([train_model(split_listings(gold_cars), "lightgbm", n_trials=0)])

    assert "n/a" in table


def test_train_model_rejects_an_unknown_model(gold_cars: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="unknown model"):
        train_model(split_listings(gold_cars), "prophet")  # type: ignore[arg-type]


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
            "--model",
            "hedonic",
            "--feature-set",
            "full",
            "--no-mlflow",
            "--duckdb-path",
            str(gold_duckdb),
        ]
    )

    assert exit_code == 0
    assert "MAPE out" in capsys.readouterr().out


def test_the_cli_dispatches_to_a_tree_model(
    gold_duckdb: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "--vehicle-type",
            "car",
            "--model",
            "lightgbm",
            "--trials",
            "0",
            "--no-mlflow",
            "--duckdb-path",
            str(gold_duckdb),
        ]
    )

    assert exit_code == 0
    assert "lightgbm" in capsys.readouterr().out


def test_the_cli_fails_cleanly_without_a_lake(tmp_path: Path) -> None:
    exit_code = main(["--no-mlflow", "--duckdb-path", str(tmp_path / "absent.duckdb")])

    assert exit_code == 1


def test_the_cli_fails_cleanly_when_a_temporal_split_is_impossible(gold_duckdb: Path) -> None:
    exit_code = main(["--split", "temporal", "--no-mlflow", "--duckdb-path", str(gold_duckdb)])

    assert exit_code == 1


def test_the_parser_defaults_to_everything_and_tracking_on() -> None:
    args = build_parser().parse_args([])

    assert args.vehicle_type is None
    assert args.model is None
    assert args.feature_set is None
    # None, not a number: the budget then comes from the per-model defaults.
    assert args.trials is None
    assert args.no_mlflow is False
    assert args.split == "random"


def test_every_model_kind_is_reachable_from_the_cli() -> None:
    args = build_parser().parse_args(
        [argument for kind in MODEL_KINDS for argument in ("--model", kind)]
    )

    assert args.model == list(MODEL_KINDS)
