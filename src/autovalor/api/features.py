"""Turning a request into the row the model was trained on.

The served model reads gold columns, so a request has to become a gold-shaped row before it
can be scored. Two of those columns are derived, and they are derived **here exactly as
``gold_listings`` derives them** — the same `greatest(..., 0)` floor on age, the same
`greatest(..., 1)` divisor on kilometres per year. A model fed a differently-derived feature
is being asked a question it was not trained on, and the error would be invisible: the
prediction would still look plausible.

The duplication is deliberate and tested. The alternative — running dbt inside the API
container to derive two columns — would drag dbt and DuckDB into an image that has to fit
in 512 MB. ``docs/STATUS.md`` already lists ``vehicle_age`` being implemented twice as known
debt; this is the third site and the test below is what keeps the three honest.
"""

from datetime import UTC, datetime

import pandas as pd

from autovalor.api.schemas import PredictRequest

UNKNOWN_CITY = "Desconocida"
"""Cities are not asked for: a user knows their department, and the model gets most of the
geography from it. The level the trees saw for an unparsed city is this one."""


def current_year() -> int:
    """The year used to age a vehicle. A function so tests can freeze it."""
    return datetime.now(UTC).year


def to_frame(request: PredictRequest, *, year: int | None = None) -> pd.DataFrame:
    """Return the one-row, gold-shaped frame the model scores.

    Args:
        request: The validated request.
        year: Year to age the vehicle against; defaults to the current one. Gold ages a
            listing against the year it was last seen, which for a live request is now.

    Returns:
        A single-row frame carrying every column the tree specification reads.
    """
    as_of = current_year() if year is None else year
    # Mirrors gold_listings: a model year in the future floors to zero rather than going
    # negative, and the per-year divisor floors to one so a current-year vehicle does not
    # divide by zero.
    age = max(as_of - request.model_year, 0)
    km_per_year = request.mileage_km / max(as_of - request.model_year, 1)

    return pd.DataFrame(
        [
            {
                "brand": request.brand,
                "model": request.model,
                "department": request.department,
                "city": UNKNOWN_CITY,
                "vehicle_age_years": float(age),
                "mileage_km": float(request.mileage_km),
                "engine_cc": None if request.engine_cc is None else float(request.engine_cc),
                "km_per_year": float(km_per_year),
                "is_official_store": False,
                # Only read for motorcycles. A request cannot say "this is a quad", and
                # guessing from the brand would be worse than the default: the flag exists
                # to let the model separate a population it saw while fitting.
                "is_quad": False,
            }
        ]
    )
