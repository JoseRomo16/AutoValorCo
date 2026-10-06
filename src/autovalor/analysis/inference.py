"""Shared OLS-with-robust-errors machinery for the economic results.

Every number in this package is a coefficient of ``log(price)``, so three decisions are
made once, here, instead of in each analysis:

**Robust standard errors, HC3.** Price dispersion grows with price: a 2 % error on a 20
million peso car is four hundred thousand pesos, on a 150 million peso one it is three
million. Classical OLS standard errors assume that away and come out too narrow, which
would make every effect look more certain than it is. HC3 is the small-sample variant of
White's correction (MacKinnon & White, 1985) and is the conservative default when n is in
the thousands rather than the millions — it down-weights high-leverage rows hardest, which
is exactly where this data has its outliers.

**No imputation by deletion.** ``engine_cc`` is missing for ~14 % of cars and ~19 % of
motorcycles. statsmodels would silently drop those rows, changing the population every
analysis is measured on. :func:`prepare` fills the median and adds an indicator column, so
"engine size unknown" is a level of its own rather than a quiet sample restriction.

**Rare categories are pooled, not dropped.** A department dummy estimated from four
listings is noise with a confidence interval around it. :func:`pool_rare` collapses the
thin levels into one ``Otros`` bucket, which keeps the rows in the regression while
refusing to make a claim about each of them.

The effect of a log-scale coefficient is multiplicative in pesos: ``exp(beta) - 1`` is the
proportional change, which is why :class:`Effect` reports percentages and not peso deltas.
A peso figure needs a base price, and every analysis that quotes one says which base it
used.
"""

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

logger = logging.getLogger("autovalor.analysis")

COV_TYPE = "HC3"
"""Heteroskedasticity-robust covariance estimator; see the module docstring."""

CONFIDENCE_LEVEL = 0.95
"""Two-sided level for every interval this package reports."""

TARGET = "log_price"
"""Dependent variable. The same one the models use, so the magnitudes are comparable."""

AGE_SQUARED = "vehicle_age_squared"
LOG_MILEAGE = "log_mileage_km"
ENGINE_CC_MISSING = "engine_cc_missing"

POOLED_LEVEL = "Otros"
"""Name of the bucket rare categories collapse into. Spanish because it reaches the UI."""


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of gold rows with the regression columns this package needs.

    Mirrors :func:`autovalor.models.hedonic.add_derived` — age squared and log mileage,
    for the same reasons — and additionally resolves the missing engine sizes that OLS
    would otherwise drop.

    Args:
        frame: Gold rows for one vertical.

    Returns:
        A copy carrying :data:`AGE_SQUARED`, :data:`LOG_MILEAGE`, a median-filled
        ``engine_cc`` and the :data:`ENGINE_CC_MISSING` indicator.
    """
    prepared = frame.copy()
    age = prepared["vehicle_age_years"].astype("float64")
    prepared[AGE_SQUARED] = age**2
    # log1p so a genuinely new vehicle sits at zero instead of minus infinity.
    prepared[LOG_MILEAGE] = np.log1p(prepared["mileage_km"].astype("float64"))

    engine = prepared["engine_cc"].astype("float64")
    prepared[ENGINE_CC_MISSING] = engine.isna().astype("float64")
    prepared["engine_cc"] = engine.fillna(engine.median())

    for column in ("brand", "model", "department", "city"):
        if column in prepared.columns:
            prepared[column] = prepared[column].fillna("Desconocido").astype(str)
    return prepared


def pool_rare(values: pd.Series, *, min_count: int, pooled: str = POOLED_LEVEL) -> pd.Series:
    """Collapse the levels of a categorical column that are too thin to estimate.

    Args:
        values: The column to pool.
        min_count: Levels with fewer rows than this are replaced by ``pooled``.
        pooled: Name of the bucket they are replaced by.

    Returns:
        A series of the same length, with rare levels renamed.
    """
    counts = values.value_counts()
    rare = set(counts[counts < min_count].index)
    if not rare:
        return values.astype(str)
    logger.info(
        "pooled %d of %d levels of %s under %d listings into %r",
        len(rare),
        len(counts),
        values.name,
        min_count,
        pooled,
    )
    return values.where(~values.isin(rare), pooled).astype(str)


def fit_ols(frame: pd.DataFrame, formula: str) -> Any:
    """Fit an OLS regression of :data:`TARGET` with robust standard errors.

    Args:
        frame: Rows already passed through :func:`prepare`.
        formula: Patsy formula for the right-hand side, without the dependent variable.

    Returns:
        The fitted statsmodels results object, with a :data:`COV_TYPE` covariance.

    Raises:
        ValueError: If the frame is empty, which would otherwise surface as an opaque
            linear-algebra error.
    """
    if frame.empty:
        msg = "cannot fit a regression on zero rows"
        raise ValueError(msg)

    model = smf.ols(f"{TARGET} ~ {formula}", data=frame)
    results = model.fit(cov_type=COV_TYPE)
    logger.info(
        "fitted OLS on %d rows, %d parameters, R2 %.3f (%s errors)",
        int(results.nobs),
        len(results.params),
        results.rsquared,
        COV_TYPE,
    )
    return results


@dataclass(frozen=True)
class Effect:
    """One estimated effect on ``log(price)``, with its interval.

    Attributes:
        name: What the effect is about — a brand, a department, a segment.
        log_estimate: The coefficient, or a linear combination of coefficients, on the
            log-price scale.
        log_ci_low: Lower end of the :data:`CONFIDENCE_LEVEL` interval, same scale.
        log_ci_high: Upper end, same scale.
        std_err: Robust standard error of the estimate.
        p_value: Two-sided p-value against zero.
        n: Rows the effect was estimated on.
    """

    name: str
    log_estimate: float
    log_ci_low: float
    log_ci_high: float
    std_err: float
    p_value: float
    n: int

    @property
    def pct_estimate(self) -> float:
        """The effect as a percentage change in pesos, ``exp(beta) - 1``."""
        return float(np.expm1(self.log_estimate)) * 100.0

    @property
    def pct_ci_low(self) -> float:
        """Lower end of the interval, as a percentage change in pesos."""
        return float(np.expm1(self.log_ci_low)) * 100.0

    @property
    def pct_ci_high(self) -> float:
        """Upper end of the interval, as a percentage change in pesos."""
        return float(np.expm1(self.log_ci_high)) * 100.0

    @property
    def is_significant(self) -> bool:
        """Whether the interval excludes zero at :data:`CONFIDENCE_LEVEL`."""
        return self.log_ci_low > 0.0 or self.log_ci_high < 0.0


def effect_of(results: Any, term: str, *, name: str | None = None) -> Effect:
    """Read one coefficient out of a fitted model as an :class:`Effect`.

    Args:
        results: Object returned by :func:`fit_ols`.
        term: Exact parameter name, as patsy built it.
        name: Label for the effect; defaults to ``term``.

    Returns:
        The coefficient with its robust interval.

    Raises:
        KeyError: If the model has no such term — a typo in a formula should fail loudly
            rather than quietly report a zero.
    """
    if term not in results.params.index:
        msg = f"{term!r} is not a parameter of this model"
        raise KeyError(msg)

    alpha = 1.0 - CONFIDENCE_LEVEL
    interval = results.conf_int(alpha=alpha).loc[term]
    return Effect(
        name=name or term,
        log_estimate=float(results.params[term]),
        log_ci_low=float(interval.iloc[0]),
        log_ci_high=float(interval.iloc[1]),
        std_err=float(results.bse[term]),
        p_value=float(results.pvalues[term]),
        n=int(results.nobs),
    )


def combined_effect(results: Any, terms: dict[str, float], *, name: str) -> Effect:
    """Estimate a linear combination of coefficients, with its interval.

    This is what an interaction needs. A brand's own age slope is
    ``beta_age + beta_age:brand``, and the interval on that sum is **not** the sum of the
    two intervals: the coefficients covary, usually negatively, so adding the intervals
    would overstate the uncertainty. statsmodels' ``t_test`` carries the full robust
    covariance through the combination, which is the only correct way to do this.

    Args:
        results: Object returned by :func:`fit_ols`.
        terms: Parameter name to weight. ``{"a": 1.0, "b": 1.0}`` estimates ``a + b``.
        name: Label for the resulting effect.

    Returns:
        The combination with its robust interval.

    Raises:
        KeyError: If any term is not a parameter of the model.
    """
    missing = [term for term in terms if term not in results.params.index]
    if missing:
        msg = f"not parameters of this model: {missing}"
        raise KeyError(msg)

    contrast = np.zeros(len(results.params))
    index = {str(term): position for position, term in enumerate(results.params.index)}
    for term, weight in terms.items():
        contrast[index[term]] = weight

    test = results.t_test(contrast)
    low, high = test.conf_int(alpha=1.0 - CONFIDENCE_LEVEL)[0]
    return Effect(
        name=name,
        log_estimate=float(np.ravel(test.effect)[0]),
        log_ci_low=float(low),
        log_ci_high=float(high),
        std_err=float(np.ravel(test.sd)[0]),
        p_value=float(np.ravel(test.pvalue)[0]),
        n=int(results.nobs),
    )


def effects_frame(effects: list[Effect]) -> pd.DataFrame:
    """Render effects as a table, ready to export.

    Args:
        effects: Effects to tabulate.

    Returns:
        One row per effect, with both the log-scale estimate and its peso-percentage
        reading, sorted by estimate.
    """
    frame = pd.DataFrame(
        [
            {
                "name": effect.name,
                "pct_change": effect.pct_estimate,
                "pct_ci_low": effect.pct_ci_low,
                "pct_ci_high": effect.pct_ci_high,
                "log_estimate": effect.log_estimate,
                "std_err": effect.std_err,
                "p_value": effect.p_value,
                "significant": effect.is_significant,
                "n": effect.n,
            }
            for effect in effects
        ]
    )
    if frame.empty:
        return frame
    return frame.sort_values("pct_change").reset_index(drop=True)
