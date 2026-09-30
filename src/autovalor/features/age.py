"""Vehicle age feature.

Age is the strongest single predictor of a used vehicle's price, so it is the first
derived feature in the pipeline. In the Colombian market the model year runs ahead of
the calendar year: a 2027 model can legitimately be on sale during 2026.
"""

from datetime import date

MIN_MODEL_YEAR = 1900
"""Earliest model year accepted; anything below is a parsing error, not a classic car."""

MAX_YEARS_AHEAD = 1
"""How far the model year may lead the reference year (next year's models sell today)."""


def vehicle_age(model_year: int, as_of: date | None = None) -> int:
    """Return the age in years of a vehicle, in calendar-year terms.

    Args:
        model_year: Model year as advertised, e.g. ``2018``.
        as_of: Reference date. Defaults to today, which makes the feature
            non-deterministic; pass the listing's ``captured_at`` date when
            building training data so features stay reproducible.

    Returns:
        ``as_of.year - model_year``, floored at ``0`` so that next year's models
        are treated as new rather than as negative age.

    Raises:
        ValueError: If ``model_year`` is below :data:`MIN_MODEL_YEAR` or leads the
            reference year by more than :data:`MAX_YEARS_AHEAD`.

    Examples:
        >>> vehicle_age(2018, date(2026, 9, 29))
        8
        >>> vehicle_age(2027, date(2026, 9, 29))
        0
    """
    # The local calendar year is what the market uses, so a naive date is correct here.
    reference = as_of or date.today()

    if model_year < MIN_MODEL_YEAR:
        msg = f"model_year {model_year} is below the minimum accepted {MIN_MODEL_YEAR}"
        raise ValueError(msg)

    max_model_year = reference.year + MAX_YEARS_AHEAD
    if model_year > max_model_year:
        msg = f"model_year {model_year} is implausible for reference year {reference.year}"
        raise ValueError(msg)

    return max(reference.year - model_year, 0)
