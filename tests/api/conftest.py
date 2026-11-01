"""Shared fixtures for the API tests.

The bundle lives here rather than in one test module because two of them now need a real
one: the contract tests drive it over HTTP, and the region tests call the served model
directly. Module-scoped, because training two verticals is the slow part of this package.
"""

from pathlib import Path

import pytest

from autovalor.models.bundle import save_bundle
from autovalor.models.catalog import build_catalog
from autovalor.models.dataset import split_listings
from autovalor.models.train import train_model

from ..models.conftest import make_gold_frame


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real bundle for both verticals, built from the synthetic lake."""
    root = tmp_path_factory.mktemp("artifacts")
    for vehicle_type, seed in (("car", 7), ("motorcycle", 11)):
        frame = make_gold_frame(600, vehicle_type=vehicle_type, seed=seed)
        dataset = split_listings(frame)
        result = train_model(dataset, "lightgbm", n_trials=0, explain=False)
        assert result.interval_model is not None
        assert result.interval is not None
        assert result.label is not None
        save_bundle(
            root / vehicle_type,
            vehicle_type=vehicle_type,  # type: ignore[arg-type]
            version="test.1",
            point=result.model,  # type: ignore[arg-type]
            interval=result.interval_model,
            label=result.label,
            metrics={
                "mape": result.test_report.mape,
                "median_ape": result.test_report.median_ape,
                "sigma_log": result.test_report.sigma_log,
                "r2_log": result.test_report.r2_log,
                "n_test": float(result.test_report.n),
                "interval_coverage": result.interval.coverage,
                "interval_mean_relative_width": result.interval.mean_relative_width,
                "baseline_mape": result.test_report.mape * 1.4,
            },
            lake={"rows": len(frame)},
            uncalibrated=result.interval_uncalibrated,
            metrics_temporal={"mape": result.test_report.mape * 1.1, "n_test": 60.0},
            catalog=build_catalog(dataset.train, vehicle_type=vehicle_type),  # type: ignore[arg-type]
        )
    return root
