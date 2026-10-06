"""Is the same vehicle cheaper in one department than another?

"The same vehicle" is the whole difficulty. Raw average prices by department mostly measure
what each region *sells* — pickups in Antioquia, small hatchbacks in Bogotá — not what it
charges. So the comparison has to hold the vehicle fixed, which is what a hedonic
regression with department dummies does: each coefficient is the price difference against
the reference department for a listing of the same brand, model class, age, mileage and
engine size.

The reference is the department with the most listings, so every difference is measured
against the best-estimated baseline. Departments under
:data:`MIN_DEPARTMENT_LISTINGS` listings are pooled into one bucket instead of carrying
their own dummy — their rows still help estimate the controls, but no claim is made about
each of them individually.

**One caveat travels with every number here**, and it is in the known-debt list of
``docs/STATUS.md``: TuCarro leaks sponsored cards across regions, so ``department`` is not
a clean sampling frame. These effects describe where listings say they are, which is close
to but not identical to where the market is.
"""

import logging

import pandas as pd

from autovalor.analysis.inference import (
    AGE_SQUARED,
    LOG_MILEAGE,
    POOLED_LEVEL,
    Effect,
    combined_effect,
    effects_frame,
    fit_ols,
    pool_rare,
    prepare,
)
from autovalor.models.dataset import VehicleType

logger = logging.getLogger("autovalor.analysis")

MIN_DEPARTMENT_LISTINGS = 30
"""Listings a department needs before it gets its own effect."""

NOT_PLACES = (POOLED_LEVEL, "Desconocido", "Desconocida")
"""Levels that are kept in the regression but never reported as a result.

The pooled bucket and the unknown-location placeholder are controls: they hold their rows
in the fit, where they help estimate the vehicle and age effects, but "listings whose
department did not parse are 22 % cheaper" is a statement about the parser, not about a
place in Colombia.
"""

MIN_VEHICLE_LISTINGS = 20
"""Pooling threshold for the vehicle control. There are 507 model tokens for cars and 802
for motorcycles, most of them thin, so without pooling the design matrix would be mostly
dummies estimated from a handful of rows each."""


def regional_effects(frame: pd.DataFrame, *, vehicle_type: VehicleType) -> pd.DataFrame:
    """Estimate each department's price difference for a comparable vehicle.

    Args:
        frame: Gold rows for one vertical.
        vehicle_type: Vertical being analysed.

    Returns:
        One row per department that cleared :data:`MIN_DEPARTMENT_LISTINGS`, with the
        difference against the reference as a percentage and its confidence interval.
        The reference department itself is included, at zero by construction.
    """
    prepared = prepare(frame)
    prepared["department_group"] = pool_rare(
        prepared["department"], min_count=MIN_DEPARTMENT_LISTINGS
    )
    # Brand and model as separate factors would be rank-deficient: a model token only ever
    # appears with one brand, so the model dummies already span the brand ones and OLS
    # warns that the parameters are not uniquely determined. One combined level set is the
    # standard fix for a nested factor, and it is also the finer control — "the same
    # vehicle" means the same model, not the same marque.
    prepared["vehicle_group"] = pool_rare(
        (prepared["brand"] + " " + prepared["model"]).rename("brand and model"),
        min_count=MIN_VEHICLE_LISTINGS,
    )

    counts = prepared["department_group"].value_counts()
    # The most listed real department, so every difference is measured against the
    # best-estimated baseline -- and never against the pooled or unknown bucket, which
    # would make the whole table a comparison with a control.
    places = [str(name) for name in counts.index if str(name) not in NOT_PLACES]
    if not places:
        msg = f"no {vehicle_type} department reaches {MIN_DEPARTMENT_LISTINGS} listings"
        raise ValueError(msg)
    reference = places[0]

    formula = (
        f"C(department_group, Treatment(reference='{reference}')) "
        f"+ vehicle_age_years + {AGE_SQUARED} + {LOG_MILEAGE} + engine_cc + engine_cc_missing "
        "+ C(vehicle_group) + is_official_store"
    )
    results = fit_ols(prepared, formula)

    effects: list[Effect] = []
    for department in counts.index:
        name = str(department)
        if name == reference or name in NOT_PLACES:
            continue
        term = f"C(department_group, Treatment(reference='{reference}'))[T.{name}]"
        # combined_effect with a single unit weight is effect_of with one code path; it
        # keeps the patsy term names in one place.
        effects.append(combined_effect(results, {term: 1.0}, name=name))

    table = effects_frame(effects)
    table["vehicle_type"] = vehicle_type
    table["listings"] = table["name"].map(counts).astype(int)
    table["is_reference"] = False

    baseline = pd.DataFrame(
        [
            {
                "name": reference,
                "pct_change": 0.0,
                "pct_ci_low": 0.0,
                "pct_ci_high": 0.0,
                "log_estimate": 0.0,
                "std_err": 0.0,
                "p_value": float("nan"),
                "significant": False,
                "n": int(results.nobs),
                "vehicle_type": vehicle_type,
                "listings": int(counts[reference]),
                "is_reference": True,
            }
        ]
    )
    table = (
        pd.concat([baseline, table], ignore_index=True)
        .rename(columns={"name": "department"})
        .sort_values("pct_change")
        .reset_index(drop=True)
    )

    spread = table["pct_change"].max() - table["pct_change"].min()
    logger.info(
        "%s regional — %d departments against %s, spread %.1f points, %d significant",
        vehicle_type,
        len(table),
        reference,
        spread,
        int(table["significant"].sum()),
    )
    return table
