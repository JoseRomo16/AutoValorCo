"""The dbt vars must mirror the Python thresholds, or silver and Pandera disagree."""

from pathlib import Path
from typing import Any

import yaml

from autovalor.quality import schemas

DBT_PROJECT = Path(__file__).parents[2] / "dbt" / "dbt_project.yml"


def dbt_vars() -> dict[str, Any]:
    with DBT_PROJECT.open(encoding="utf-8") as handle:
        project: dict[str, Any] = yaml.safe_load(handle)
    return dict(project["vars"])


def test_thresholds_match_the_dbt_project() -> None:
    assert dbt_vars() == {
        "min_price_cop": schemas.MIN_PRICE_COP,
        "max_price_cop": schemas.MAX_PRICE_COP,
        "min_model_year": schemas.MIN_MODEL_YEAR,
        "max_mileage_km": schemas.MAX_MILEAGE_KM,
        "min_engine_cc": schemas.MIN_ENGINE_CC,
        "max_engine_cc": schemas.MAX_ENGINE_CC,
        "min_car_cc": schemas.MIN_CAR_CC,
        "max_car_cc": schemas.MAX_CAR_CC,
        "min_gear_count": schemas.MIN_GEAR_COUNT,
        "max_gear_count": schemas.MAX_GEAR_COUNT,
    }
