"""The served estimate must not sit systematically against one edge of its range.

The live audit of bundle ``2026-10-25.12948`` valued 60 combinations of make, year and
mileage in Bogotá and found the estimate at a median position of 0,32 (cars) and 0,10
(motorcycles) inside the published P10-P90, measured in log, where 0,5 is the centre.
This test rebuilds that grid from the committed bundle's own catalogue — the five makes
with most listings, each with its commonest model, model years 2012/2018/2023 and
20.000/80.000 km — and scores it through ``to_frame``, exactly as ``/predict`` would.

The thresholds come from measuring the grid on both bundles (``docs/STATUS.md``, Block 4):

=================  ==========  ===============  ==========  ===============
                   old median  old outer share  new median  new outer share
=================  ==========  ===============  ==========  ===============
cars               0,36        20 %             0,53        23 %
motorcycles        0,11        77 %             0,30        40 %
=================  ==========  ===============  ==========  ===============

"Outer share" is the share of rows below 0,2 or above 0,8. A median outside [0,25; 0,75]
or an outer share above half fails: the old motorcycle bundle fails both, the new one
passes both with some room, and a centred band would sit near 0,5 and 20 %.
"""

from collections.abc import Iterator

import numpy as np
import pandas as pd
import pytest

from autovalor.api.features import to_frame
from autovalor.api.schemas import PredictRequest
from autovalor.models.band_diagnostics import position_in_band
from autovalor.models.bundle import ARTIFACTS_DIR, ServedModel, load_served_models
from autovalor.models.dataset import VEHICLE_TYPES, VehicleType

MEDIAN_RANGE = (0.25, 0.75)
MAX_OUTER_SHARE = 0.5
GRID_YEARS = (2012, 2018, 2023)
GRID_MILEAGE = (20_000, 80_000)
GRID_DEPARTMENT = "Bogotá D.C."
GRID_YEAR_OF_VALUATION = 2026
"""Fixed so the grid does not age with the calendar."""


@pytest.fixture(scope="module")
def served() -> Iterator[dict[VehicleType, ServedModel]]:
    if not (ARTIFACTS_DIR / "car" / "model.json").exists():
        pytest.skip("no committed bundle")
    yield load_served_models(ARTIFACTS_DIR)


def _grid(model: ServedModel, vehicle_type: VehicleType) -> pd.DataFrame:
    assert model.catalog is not None
    brands = sorted(
        (brand for brand in model.catalog.brands if brand.name != "Desconocida"),
        key=lambda brand: -brand.listings,
    )[:5]
    frames = [
        to_frame(
            PredictRequest(
                vehicle_type=vehicle_type,
                brand=brand.name,
                model=max(brand.models, key=lambda entry: entry.listings).name,
                model_year=year,
                mileage_km=mileage,
                department=GRID_DEPARTMENT,
            ),
            year=GRID_YEAR_OF_VALUATION,
        )
        for brand in brands
        for year in GRID_YEARS
        for mileage in GRID_MILEAGE
    ]
    return pd.concat(frames, ignore_index=True)


@pytest.mark.parametrize("vehicle_type", VEHICLE_TYPES)
def test_the_estimate_is_not_pinned_to_an_edge_of_the_range(
    served: dict[VehicleType, ServedModel], vehicle_type: VehicleType
) -> None:
    model = served[vehicle_type]
    band = np.asarray(model.predict_published_band(_grid(model, vehicle_type)))
    position = position_in_band(band[:, 1], band[:, 0], band[:, 2])

    median = float(np.median(position))
    outer = float(np.mean((position < 0.2) | (position > 0.8)))
    assert MEDIAN_RANGE[0] <= median <= MEDIAN_RANGE[1], f"median position {median:.2f}"
    assert outer <= MAX_OUTER_SHARE, f"{outer:.0%} of the grid sits in the outer fifths"
