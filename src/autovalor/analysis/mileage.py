"""What 10.000 extra kilometres cost, by vertical and by price segment.

The regression carries mileage as ``log1p(km)``, because the price effect of use is
proportional rather than linear — the first 10.000 km of a new car cost far more than the
tenth 10.000 of an old one. That is the right model and the wrong unit for an answer: an
elasticity is not something a seller can act on.

So the elasticity is converted at a stated point. For a vehicle sitting at the segment's
median mileage, going 10.000 km further changes log price by
``beta * (log1p(m + 10.000) - log1p(m))``, and multiplying the segment's median price by
``exp(that) - 1`` turns it into pesos. **Both medians are reported next to the figure**,
because the peso number is only true near them; quoting it as "10.000 km costs X pesos"
without the base price would be a sleight of hand.

Segments are price quartiles, fitted separately rather than pooled with an interaction.
Separate fits let every coefficient — age, brand, department — differ by segment too, which
is the realistic assumption: a 15 million peso car and a 150 million one are not the same
market with a different intercept.

**The segment is a property of the vehicle, not of the listing.** Cutting on the listing's
own asking price would be conditioning on the dependent variable: inside a narrow price
band a high-mileage listing has to be compensated by something else — newer, a dearer model
— so the mileage coefficient is pushed toward zero by construction. Measured that way the
first three car quartiles came out at effectively no mileage effect at all, which is an
artefact of the cut and not a fact about the market. So the cut is made on the **median
price of the vehicle's own brand-and-model group**, which is a price *class* fixed before
this listing was written: within a class, price still varies with age and use, which is
exactly the variation the coefficient needs.
"""

import logging

import numpy as np
import pandas as pd

from autovalor.analysis.inference import (
    AGE_SQUARED,
    LOG_MILEAGE,
    effect_of,
    fit_ols,
    pool_rare,
    prepare,
)
from autovalor.models.dataset import VehicleType

logger = logging.getLogger("autovalor.analysis")

MILEAGE_STEP_KM = 10_000
"""The step the effect is quoted for."""

PRICE_SEGMENTS = 4
"""Number of price segments, i.e. quartiles."""

MIN_SEGMENT_ROWS = 200
"""Below this a segment regression is too thin to report; it is skipped, loudly."""

MIN_CLASS_LISTINGS = 10
"""Listings a model needs before its own median defines its price class; below it the
brand's median stands in."""

MIN_BRAND_LISTINGS = 20
MIN_DEPARTMENT_LISTINGS = 30
"""Pooling thresholds for the controls inside a segment, where every level is thinner than
in the vertical as a whole."""

ALL_SEGMENTS = "all"
"""Label of the whole-vertical row, fitted alongside the segments."""


def vehicle_price_class(frame: pd.DataFrame) -> pd.Series:
    """Return each listing's price class: the median asking price of its model.

    The median of a vehicle's own brand-and-model group — "what a Mazda 3 goes for" —
    rather than what this particular one is asking. Models too thin to have a reliable
    median fall back to their brand's, and a listing with neither falls back to the
    vertical's.

    Args:
        frame: Gold rows for one vertical.

    Returns:
        One price class per row, in COP.
    """
    by_model = frame.groupby(["brand", "model"], dropna=False)["price_cop"].transform("median")
    by_brand = frame.groupby("brand", dropna=False)["price_cop"].transform("median")
    model_counts = frame.groupby(["brand", "model"], dropna=False)["price_cop"].transform("size")
    thin = model_counts < MIN_CLASS_LISTINGS
    return by_model.where(~thin, by_brand).fillna(frame["price_cop"].median())


def price_segments(frame: pd.DataFrame, *, segments: int = PRICE_SEGMENTS) -> pd.Series:
    """Label each row with the quartile of its vehicle's price class.

    See the module docstring for why this cuts on the class and not on the listing's own
    price.

    Args:
        frame: Gold rows for one vertical.
        segments: Number of quantile bins.

    Returns:
        A series of labels like ``Q1`` to ``Q4``, ordered from cheapest to dearest.
    """
    labels = [f"Q{index + 1}" for index in range(segments)]
    # duplicates="drop" guards a vertical whose class distribution has a quantile tie; it
    # would otherwise raise instead of just producing fewer bins.
    binned = pd.qcut(
        vehicle_price_class(frame).rank(method="first"),
        q=segments,
        labels=labels,
        duplicates="drop",
    )
    return binned.astype(str)


def mileage_effects(frame: pd.DataFrame, *, vehicle_type: VehicleType) -> pd.DataFrame:
    """Estimate the cost of :data:`MILEAGE_STEP_KM` more kilometres, overall and by segment.

    Args:
        frame: Gold rows for one vertical.
        vehicle_type: Vertical being analysed.

    Returns:
        One row per segment plus one for the whole vertical, carrying the elasticity, the
        peso effect at the segment's medians, and the medians themselves.
    """
    prepared = prepare(frame)
    prepared["price_segment"] = price_segments(prepared)

    rows: list[dict[str, object]] = [_segment_effect(prepared, vehicle_type, ALL_SEGMENTS)]
    for segment in sorted(prepared["price_segment"].unique()):
        subset = prepared[prepared["price_segment"] == segment]
        if len(subset) < MIN_SEGMENT_ROWS:
            logger.warning(
                "%s segment %s has %d rows, under the %d needed; skipped",
                vehicle_type,
                segment,
                len(subset),
                MIN_SEGMENT_ROWS,
            )
            continue
        rows.append(_segment_effect(subset, vehicle_type, str(segment)))

    effects = pd.DataFrame(rows)
    overall = effects[effects["segment"] == ALL_SEGMENTS].iloc[0]
    logger.info(
        "%s mileage — %s km costs %.0f COP at the median listing (elasticity %.4f)",
        vehicle_type,
        f"{MILEAGE_STEP_KM:,}",
        overall["cop_per_step"],
        overall["elasticity"],
    )
    return effects


def _segment_effect(
    frame: pd.DataFrame, vehicle_type: VehicleType, segment: str
) -> dict[str, object]:
    """Fit one segment and convert its mileage elasticity into pesos."""
    fitted = frame.copy()
    fitted["brand_group"] = pool_rare(fitted["brand"], min_count=MIN_BRAND_LISTINGS)
    fitted["department_group"] = pool_rare(fitted["department"], min_count=MIN_DEPARTMENT_LISTINGS)

    formula = (
        f"{LOG_MILEAGE} + vehicle_age_years + {AGE_SQUARED} + engine_cc + engine_cc_missing "
        "+ C(brand_group) + C(department_group)"
    )
    results = fit_ols(fitted, formula)
    elasticity = effect_of(results, LOG_MILEAGE, name=segment)

    median_km = float(fitted["mileage_km"].median())
    median_price = float(fitted["price_cop"].median())
    step = _log_step(median_km)

    return {
        "vehicle_type": vehicle_type,
        "segment": segment,
        "n": int(results.nobs),
        "median_price_cop": median_price,
        "median_mileage_km": median_km,
        "elasticity": elasticity.log_estimate,
        # Signed as a change in price: negative means the kilometres cost money. The
        # conversion is monotone in the elasticity, so the interval ends keep their order
        # -- they are not swapped here, unlike the depreciation rates, which report the
        # effect with its sign flipped.
        "pct_per_step": _pct_for_step(elasticity.log_estimate, step),
        "pct_ci_low": _pct_for_step(elasticity.log_ci_low, step),
        "pct_ci_high": _pct_for_step(elasticity.log_ci_high, step),
        "cop_per_step": _cop_for_step(elasticity.log_estimate, step, median_price),
        "cop_ci_low": _cop_for_step(elasticity.log_ci_low, step, median_price),
        "cop_ci_high": _cop_for_step(elasticity.log_ci_high, step, median_price),
        "std_err": elasticity.std_err,
        "p_value": elasticity.p_value,
        "significant": elasticity.is_significant,
    }


def _log_step(median_km: float) -> float:
    """Change in ``log1p(km)`` from driving :data:`MILEAGE_STEP_KM` more at ``median_km``."""
    return float(np.log1p(median_km + MILEAGE_STEP_KM) - np.log1p(median_km))


def _pct_for_step(elasticity: float, log_step: float) -> float:
    """The step's effect as a percentage of the price."""
    return float(np.expm1(elasticity * log_step)) * 100.0


def _cop_for_step(elasticity: float, log_step: float, median_price: float) -> float:
    """The step's effect in pesos at a base price.

    Negative when more use means a lower price, which is the expected sign.
    """
    return float(np.expm1(elasticity * log_step)) * median_price
