"""The motorcycle "catalogue" finding, made falsifiable.

F2's SHAP table produced the sharpest claim of the project so far: the motorcycle model
behaves like a price catalogue. It pulls most of its signal from *identity* — brand,
displacement, model — and almost none from *condition* — age, mileage. Cars are the other
way round, with age their second strongest driver. If that is true it explains both the
MAPE and the useless band width at once, and it also says more identity columns will not
help, which is why it decided against further enrichment.

But SHAP alone cannot carry that conclusion. Mean ``|phi|`` measures how much of the price
variance a feature *explains*; it does not say whether the relationship is right, and a
small value has two readings that matter very differently:

1. Age really matters less for motorcycles than for cars.
2. Age matters just as much, and brand and model have already absorbed it — a 2015 Pulsar
   and a 2024 Pulsar being different model tokens would do exactly that.

This module separates them by asking a second, independent question: what does the hedonic
regression say a year of age is worth in each vertical, with age entered explicitly and
brand held fixed? If the hedonic also finds a small age effect for motorcycles, reading 1
survives. If the hedonic finds a large one that SHAP does not use, the model is leaving
money on the table and reading 2 is the story.

The two numbers are not the same quantity and the export says so: SHAP's share is relative
importance inside one model, the hedonic's is a coefficient. What is comparable is their
*ordering* across the two verticals, which is the claim being tested.
"""

import logging

import pandas as pd

from autovalor.analysis.inference import (
    AGE_SQUARED,
    LOG_MILEAGE,
    combined_effect,
    fit_ols,
    pool_rare,
    prepare,
)
from autovalor.models.dataset import VehicleType

logger = logging.getLogger("autovalor.analysis")

CONDITION_FEATURES = ("vehicle_age_years", "mileage_km", "km_per_year")
"""What the listing's state is: how old, how used, how hard.

``km_per_year`` is condition and not identity — it is mileage normalised by age.
"""

IDENTITY_FEATURES = ("brand", "model", "engine_cc", "is_quad")
"""What the vehicle *is*. Fixed at the factory; nothing about this particular example."""

MIN_BRAND_LISTINGS = 20
MIN_DEPARTMENT_LISTINGS = 30


def pull_shares(importance: pd.DataFrame) -> dict[str, float]:
    """Split a SHAP importance table into condition, identity and the rest.

    Args:
        importance: Output of :func:`autovalor.models.explain.global_importance`.

    Returns:
        The share of total mean ``|phi|`` that falls on condition features, on identity
        features and on everything else (location, seller type), as percentages summing
        to 100.

    Raises:
        ValueError: If the table carries no importance at all, which would make every
            share a division by zero.
    """
    total = float(importance["mean_abs_phi"].sum())
    if total <= 0.0:
        msg = "the importance table sums to zero; nothing to apportion"
        raise ValueError(msg)

    def share(features: tuple[str, ...]) -> float:
        selected = importance[importance["feature"].isin(features)]
        return float(selected["mean_abs_phi"].sum()) / total * 100.0

    condition = share(CONDITION_FEATURES)
    identity = share(IDENTITY_FEATURES)
    return {
        "condition_share_pct": condition,
        "identity_share_pct": identity,
        "other_share_pct": 100.0 - condition - identity,
    }


def hedonic_age_effect(frame: pd.DataFrame, *, vehicle_type: VehicleType) -> dict[str, float]:
    """Estimate what one year of age is worth, with brand and model held fixed.

    Age enters linearly *and* squared, so the reported figure is the slope at the vertical's
    median age rather than an average over a curve — the honest reading of "one more year"
    for a typical listing.

    Args:
        frame: Gold rows for one vertical.
        vehicle_type: Vertical being analysed.

    Returns:
        The annual depreciation at the median age, as a percentage with its interval, plus
        the median age it was evaluated at.
    """
    prepared = prepare(frame)
    prepared["brand_group"] = pool_rare(prepared["brand"], min_count=MIN_BRAND_LISTINGS)
    prepared["department_group"] = pool_rare(
        prepared["department"], min_count=MIN_DEPARTMENT_LISTINGS
    )

    formula = (
        f"vehicle_age_years + {AGE_SQUARED} + {LOG_MILEAGE} + engine_cc + engine_cc_missing "
        "+ C(brand_group) + C(department_group)"
    )
    results = fit_ols(prepared, formula)
    median_age = float(prepared["vehicle_age_years"].median())

    # d log(price) / d age at the median age is beta_age + 2 * beta_age2 * age. The weights
    # are fixed numbers, so this is a linear combination and its interval comes out exact
    # from the robust covariance rather than being approximated from the linear term alone.
    slope = combined_effect(
        results,
        {"vehicle_age_years": 1.0, AGE_SQUARED: 2.0 * median_age},
        name="age at the median",
    )
    return {
        "median_age_years": median_age,
        "annual_depreciation_pct": -slope.pct_estimate,
        "annual_ci_low_pct": -slope.pct_ci_high,
        "annual_ci_high_pct": -slope.pct_ci_low,
        "age_slope_log": slope.log_estimate,
        "age_p_value": slope.p_value,
        "n": float(results.nobs),
    }


def catalogue_contrast(
    importances: dict[VehicleType, pd.DataFrame],
    frames: dict[VehicleType, pd.DataFrame],
) -> pd.DataFrame:
    """Contrast SHAP's condition/identity split with the hedonic age effect, per vertical.

    Args:
        importances: SHAP importance table per vertical, from the training run.
        frames: Gold rows per vertical.

    Returns:
        One row per vertical: the SHAP shares, the hedonic annual depreciation at the
        median age, and the identity-to-condition ratio that is the finding's headline.
    """
    rows: list[dict[str, object]] = []
    for vehicle_type, importance in importances.items():
        shares = pull_shares(importance)
        hedonic = hedonic_age_effect(frames[vehicle_type], vehicle_type=vehicle_type)
        condition = shares["condition_share_pct"]
        rows.append(
            {
                "vehicle_type": vehicle_type,
                **shares,
                # The ratio is the single number the finding rests on: above 1 the model
                # leans on what the vehicle is, below 1 on what shape it is in.
                "identity_over_condition": (
                    shares["identity_share_pct"] / condition if condition > 0 else float("inf")
                ),
                **hedonic,
            }
        )

    contrast = pd.DataFrame(rows)
    for _, row in contrast.iterrows():
        logger.info(
            "%s catalogue — SHAP identity %.1f%% vs condition %.1f%% (ratio %.1f), "
            "hedonic says %.1f%% per year at age %.1f",
            row["vehicle_type"],
            row["identity_share_pct"],
            row["condition_share_pct"],
            row["identity_over_condition"],
            row["annual_depreciation_pct"],
            row["median_age_years"],
        )
    return contrast
