"""Depreciation curves by brand.

What a buyer wants to know is not "what is this worth" but "what will a year cost me".
That is the age slope of the hedonic regression, and it differs by brand — the whole folk
theory of the Colombian used market is that a Toyota holds its value and something else
does not. This module estimates that slope per brand, with an interval, so the claim can
be checked instead of repeated.

**The model is log-linear in age, on purpose.** With ``log(price)`` on the left, a straight
line in age means a constant *proportional* loss per year, which is exactly what "annual
depreciation rate" means and is what makes one number per brand meaningful. An age-squared
term would fit the curve better and would make the per-brand figure a function of age
instead of a rate, so it is left out here and kept in
:mod:`autovalor.analysis.mileage`, where age is a control rather than the subject.

**Brands have to earn an estimate.** A slope needs rows and it needs those rows spread
over age: 200 listings of a brand that only exists as a 2024 model carries no information
about what year five costs. Hence the two filters in :data:`MIN_BRAND_LISTINGS` and
:data:`MIN_BRAND_MODEL_YEARS`, and everything below them is pooled rather than dropped, so
the controls still use those rows. The unknown-brand bucket is excluded outright: for
motorcycles it is the *largest* "brand" in the vertical — 19 % of titles do not resolve one
— and letting it stand would make it the reference every other brand is compared against.

**Two rates are reported, because "annual depreciation" is ambiguous and the difference is
large.** The regression controls for mileage, so the age coefficient alone is the price of
a year *holding use fixed* — the showroom-to-garage effect, which is not what a seller
experiences. A typical year also adds kilometres, and those are priced too. So:

``age_only_pct``
    The age coefficient. What a year of calendar time costs a vehicle that was not driven.
``annual_depreciation_pct``
    That, plus the mileage effect of the brand's median kilometres per year. The headline,
    and the one a product should quote.

Both come from the same fit; the total is a linear combination of two of its coefficients
with fixed weights, so its interval is exact rather than approximated.
"""

import logging

import numpy as np
import pandas as pd

from autovalor.analysis.inference import (
    LOG_MILEAGE,
    POOLED_LEVEL,
    combined_effect,
    fit_ols,
    pool_rare,
    prepare,
)
from autovalor.models.dataset import VehicleType

logger = logging.getLogger("autovalor.analysis")

MIN_BRAND_LISTINGS = 200
"""Listings a brand needs before its own age slope is reported."""

MIN_BRAND_MODEL_YEARS = 5
"""Distinct model years a brand needs. Guards against a brand that is well represented but
only as recent vehicles, where the age slope would be extrapolation dressed as an estimate.
"""

AGE_TERM = "vehicle_age_years"

MIN_DEPARTMENT_LISTINGS = 30
"""Departments thinner than this are pooled while they serve as controls here."""

UNKNOWN_BRANDS = ("Desconocida", "Desconocido")
"""Placeholders the title parser leaves when no brand could be mined.

Not a brand, so never an estimate and never the reference. The rows stay in the regression
as part of the pooled bucket — they still carry information about age and mileage — but no
depreciation rate is published for "unknown".
"""


def eligible_brands(frame: pd.DataFrame) -> list[str]:
    """Return the brands that clear both filters, most frequent first.

    Args:
        frame: Gold rows for one vertical.

    Returns:
        Brand names with at least :data:`MIN_BRAND_LISTINGS` listings spread over at least
        :data:`MIN_BRAND_MODEL_YEARS` model years, excluding :data:`UNKNOWN_BRANDS`.
    """
    grouped = frame.groupby("brand").agg(
        listings=("listing_id", "size"),
        model_years=("model_year", "nunique"),
    )
    eligible = grouped[
        (grouped["listings"] >= MIN_BRAND_LISTINGS)
        & (grouped["model_years"] >= MIN_BRAND_MODEL_YEARS)
        & (~grouped.index.isin(UNKNOWN_BRANDS))
    ]
    return [str(brand) for brand in eligible.sort_values("listings", ascending=False).index]


def depreciation_curves(frame: pd.DataFrame, *, vehicle_type: VehicleType) -> pd.DataFrame:
    """Estimate the annual depreciation rate of every eligible brand.

    The regression interacts age with brand and controls for mileage, engine size and
    department, so the slope is "a year of age, holding the rest of the listing fixed"
    rather than "older vehicles happen to be cheaper models".

    Args:
        frame: Gold rows for one vertical.
        vehicle_type: Vertical being analysed, carried into the result for export.

    Returns:
        One row per brand: the annual depreciation rate as a percentage with its
        confidence interval, the age-only rate beside it, the half-life in years, and the
        rows behind it. Sorted from the brand that holds its value best to the one that
        loses it fastest.

    Raises:
        ValueError: If no brand clears the filters, which means the vertical cannot
            support this analysis at all.
    """
    prepared = prepare(frame)
    brands = eligible_brands(prepared)
    if not brands:
        msg = (
            f"no {vehicle_type} brand reaches {MIN_BRAND_LISTINGS} listings over "
            f"{MIN_BRAND_MODEL_YEARS} model years"
        )
        raise ValueError(msg)

    # The reference level is the most frequent eligible brand, so the interaction terms are
    # all estimated against the best-measured baseline instead of an arbitrary one.
    reference = brands[0]
    prepared["brand_group"] = prepared["brand"].where(prepared["brand"].isin(brands), POOLED_LEVEL)
    prepared["department_group"] = pool_rare(
        prepared["department"], min_count=MIN_DEPARTMENT_LISTINGS
    )

    formula = (
        f"{AGE_TERM} * C(brand_group, Treatment(reference='{reference}')) "
        f"+ {LOG_MILEAGE} + engine_cc + engine_cc_missing + C(department_group)"
    )
    results = fit_ols(prepared, formula)

    counts = prepared.groupby("brand_group").size()
    years = prepared.groupby("brand_group")["model_year"].nunique()

    rows: list[dict[str, object]] = []
    for brand in brands:
        own = prepared[prepared["brand_group"] == brand]
        mileage_weight = _annual_mileage_weight(own)
        age_terms = {AGE_TERM: 1.0}
        if brand != reference:
            interaction = (
                f"{AGE_TERM}:C(brand_group, Treatment(reference='{reference}'))[T.{brand}]"
            )
            age_terms[interaction] = 1.0

        age_only = combined_effect(results, age_terms, name=brand)
        # A year is age *and* the kilometres a year brings. Both coefficients come from this
        # same fit and the weights are fixed numbers, so the total keeps an exact interval.
        total = combined_effect(results, {**age_terms, LOG_MILEAGE: mileage_weight}, name=brand)

        # The slope is the proportional change per year, so the depreciation rate is its
        # sign flipped: a slope of -0.08 is a 7.7 % annual loss, not 8 %.
        rows.append(
            {
                "vehicle_type": vehicle_type,
                "brand": brand,
                "is_reference": brand == reference,
                "listings": int(counts.get(brand, 0)),
                "model_years": int(years.get(brand, 0)),
                "annual_depreciation_pct": -total.pct_estimate,
                # The interval flips with the sign, so the ends swap.
                "ci_low_pct": -total.pct_ci_high,
                "ci_high_pct": -total.pct_ci_low,
                "age_only_pct": -age_only.pct_estimate,
                "median_km_per_year": float(own["km_per_year"].median()),
                "half_life_years": _half_life(total.log_estimate),
                "slope_log_per_year": total.log_estimate,
                "std_err": total.std_err,
                "p_value": total.p_value,
                "significant": total.is_significant,
            }
        )

    curves = pd.DataFrame(rows).sort_values("annual_depreciation_pct").reset_index(drop=True)
    logger.info(
        "%s depreciation — %d brands, %.1f%% to %.1f%% per year including typical use "
        "(%.1f%% to %.1f%% from age alone), reference %s",
        vehicle_type,
        len(curves),
        curves["annual_depreciation_pct"].min(),
        curves["annual_depreciation_pct"].max(),
        curves["age_only_pct"].min(),
        curves["age_only_pct"].max(),
        reference,
    )
    return curves


def _annual_mileage_weight(frame: pd.DataFrame) -> float:
    """How much ``log1p(km)`` moves in a typical year for these listings.

    Evaluated at the group's median odometer and median kilometres per year, so the figure
    describes the brand's own usage rather than the vertical's average.

    Args:
        frame: Rows of one brand, already passed through :func:`prepare`.

    Returns:
        ``log1p(median_km + median_km_per_year) - log1p(median_km)``, zero when either
        median is missing.
    """
    median_km = float(frame["mileage_km"].median())
    per_year = float(frame["km_per_year"].median())
    if not np.isfinite(median_km) or not np.isfinite(per_year):
        return 0.0
    return float(np.log1p(median_km + per_year) - np.log1p(median_km))


def _half_life(slope_log_per_year: float) -> float:
    """Years for the price to halve at a constant proportional slope.

    Args:
        slope_log_per_year: The age coefficient on the log-price scale, normally negative.

    Returns:
        ``log(0.5) / slope``, or NaN when the slope is non-negative — a brand that does not
        lose value has no half-life, and reporting a huge number would imply one.
    """
    if slope_log_per_year >= 0.0:
        return float("nan")
    return float(np.log(0.5) / slope_log_per_year)


def depreciation_at_ages(
    curves: pd.DataFrame, ages: tuple[int, ...] = (1, 3, 5, 10)
) -> pd.DataFrame:
    """Turn the rates into the retained share of value at a few ages.

    A rate per year is the honest estimate; "worth 61 % of new at five years" is the
    readable one. Both go to the export, from the same coefficient.

    Args:
        curves: Output of :func:`depreciation_curves`.
        ages: Ages in years to evaluate.

    Returns:
        One row per brand and age, with the retained share as a percentage.
    """
    rows = [
        {
            "vehicle_type": row["vehicle_type"],
            "brand": row["brand"],
            "age_years": age,
            "retained_value_pct": float(np.exp(row["slope_log_per_year"] * age)) * 100.0,
        }
        for _, row in curves.iterrows()
        for age in ages
    ]
    return pd.DataFrame(rows)
