"""Error metrics for the valuation models.

Models are fitted on ``log(price)`` but judged in pesos, because the product's promise
is about pesos: the F2 target is MAPE ≤ 15 % and the bargain/fair/expensive label
depends on a peso figure. So every metric here takes predictions back to COP first.

Back-transforming matters and is easy to get wrong. If the error in log space is
symmetric, ``exp(ŷ)`` estimates the **median** price, not the mean. The median is the
right point estimate for this product — it minimises absolute error and is what a user
reading "this car is worth $X" expects — so :func:`to_pesos` applies no correction and
:func:`smearing_factor` exists for when the mean is genuinely what is wanted.
"""

from dataclasses import asdict, dataclass

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

WITHIN_TOLERANCES = (0.10, 0.20)
"""Relative tolerances reported as hit rates. 10 % reads as "close enough to negotiate"."""


def to_pesos(log_price: npt.ArrayLike) -> FloatArray:
    """Convert a ``log(price)`` prediction to a median price in COP.

    Args:
        log_price: Predictions on the natural-log scale.

    Returns:
        Prices in COP, as the conditional median. See the module docstring for why no
        variance correction is applied.
    """
    return np.exp(np.asarray(log_price, dtype=np.float64))


def smearing_factor(log_residuals: npt.ArrayLike) -> float:
    """Return Duan's smearing estimate of the mean/median ratio.

    Multiplying :func:`to_pesos` by this factor turns the median estimate into an
    estimate of the mean, without assuming the residuals are normal.

    Args:
        log_residuals: Training residuals on the log scale (``y - ŷ``).

    Returns:
        ``mean(exp(residuals))``, which is ``1.0`` for a perfectly centred fit and
        above it for any spread (Jensen's inequality).
    """
    return float(np.mean(np.exp(np.asarray(log_residuals, dtype=np.float64))))


@dataclass(frozen=True)
class RegressionReport:
    """Out-of-sample error of one model on one vertical.

    Attributes:
        n: Rows scored.
        mape: Mean absolute percentage error in COP — the F2 acceptance metric.
        median_ape: Median absolute percentage error; unlike ``mape`` it is not moved
            by a handful of mispriced listings, so a wide gap between the two says the
            tail is the problem rather than the bulk.
        mae_cop: Mean absolute error in pesos.
        rmse_cop: Root mean squared error in pesos.
        sigma_log: Standard deviation of the residuals in log space — the sigma that the
            F1 pilot reported, kept so the two are comparable.
        r2_log: Coefficient of determination in log space.
        within_10pct: Share of predictions within 10 % of the asking price.
        within_20pct: Share within 20 %.
    """

    n: int
    mape: float
    median_ape: float
    mae_cop: float
    rmse_cop: float
    sigma_log: float
    r2_log: float
    within_10pct: float
    within_20pct: float

    def as_dict(self) -> dict[str, float]:
        """Return the metrics as a flat mapping, ready to log to MLflow."""
        return {key: float(value) for key, value in asdict(self).items()}

    def summary(self) -> str:
        """Return a one-line human-readable summary."""
        # ASCII only: the Windows console this project is developed on is cp1252 and
        # raises UnicodeEncodeError on sigma, squared and plus-minus signs.
        return (
            f"n={self.n} MAPE={self.mape:.1%} median APE={self.median_ape:.1%} "
            f"sigma(log)={self.sigma_log:.3f} R2(log)={self.r2_log:.3f} "
            f"within 10%={self.within_10pct:.1%}"
        )


def regression_report(
    log_price_true: npt.ArrayLike,
    log_price_pred: npt.ArrayLike,
) -> RegressionReport:
    """Score predictions against the asking prices they tried to reproduce.

    Both arguments are on the log scale because that is what the models emit; the
    peso-denominated metrics are computed after back-transforming.

    Args:
        log_price_true: Observed ``log(price)``.
        log_price_pred: Predicted ``log(price)``.

    Returns:
        The error report.

    Raises:
        ValueError: If the arrays differ in length, are empty, or hold non-finite
            values — a silent ``nan`` here would be reported as a result.
    """
    true_log = np.asarray(log_price_true, dtype=np.float64).ravel()
    pred_log = np.asarray(log_price_pred, dtype=np.float64).ravel()

    if true_log.shape != pred_log.shape:
        msg = f"shape mismatch: {true_log.shape} true vs {pred_log.shape} predicted"
        raise ValueError(msg)
    if true_log.size == 0:
        msg = "cannot score an empty prediction set"
        raise ValueError(msg)
    if not (np.isfinite(true_log).all() and np.isfinite(pred_log).all()):
        msg = "predictions and targets must be finite; got nan or inf"
        raise ValueError(msg)

    residuals_log = true_log - pred_log
    true_cop = to_pesos(true_log)
    pred_cop = to_pesos(pred_log)
    absolute_error = np.abs(true_cop - pred_cop)
    # Prices in gold are strictly positive (a plausibility rule), so this cannot divide
    # by zero.
    relative_error = absolute_error / true_cop

    total_variance = float(np.sum((true_log - true_log.mean()) ** 2))
    residual_variance = float(np.sum(residuals_log**2))
    # A constant target makes R² undefined rather than zero; say so with nan.
    r2_log = 1.0 - residual_variance / total_variance if total_variance > 0 else float("nan")

    within = [float(np.mean(relative_error <= tolerance)) for tolerance in WITHIN_TOLERANCES]

    return RegressionReport(
        n=int(true_log.size),
        mape=float(np.mean(relative_error)),
        median_ape=float(np.median(relative_error)),
        mae_cop=float(np.mean(absolute_error)),
        rmse_cop=float(np.sqrt(np.mean(absolute_error**2))),
        sigma_log=float(np.std(residuals_log, ddof=1)) if residuals_log.size > 1 else 0.0,
        r2_log=r2_log,
        within_10pct=within[0],
        within_20pct=within[1],
    )


@dataclass(frozen=True)
class IntervalReport:
    """Quality of a predicted P10-P90 price band.

    A band is only useful if it is both calibrated and tight: 80 % coverage reached by
    quoting "between 10 and 200 million" tells a user nothing.

    Attributes:
        n: Rows scored.
        coverage: Share of asking prices that fell inside the band. Should approach the
            band's nominal width (0.80 for P10-P90).
        mean_relative_width: Mean of ``(upper - lower) / prediction``, in COP terms.
        below_rate: Share falling under the lower bound — these are the "bargain" calls.
        above_rate: Share above the upper bound — the "expensive" calls.
    """

    n: int
    coverage: float
    mean_relative_width: float
    below_rate: float
    above_rate: float

    def as_dict(self) -> dict[str, float]:
        """Return the metrics as a flat mapping, ready to log to MLflow."""
        return {key: float(value) for key, value in asdict(self).items()}


def interval_report(
    log_price_true: npt.ArrayLike,
    log_price_lower: npt.ArrayLike,
    log_price_upper: npt.ArrayLike,
) -> IntervalReport:
    """Score a predicted price band against the asking prices.

    Args:
        log_price_true: Observed ``log(price)``.
        log_price_lower: Predicted lower bound (P10) on the log scale.
        log_price_upper: Predicted upper bound (P90) on the log scale.

    Returns:
        The interval report.

    Raises:
        ValueError: If the arrays differ in length, are empty, or any lower bound
            exceeds its upper bound — crossed quantiles are a modeling bug, not a
            result to be averaged away.
    """
    true_log = np.asarray(log_price_true, dtype=np.float64).ravel()
    lower_log = np.asarray(log_price_lower, dtype=np.float64).ravel()
    upper_log = np.asarray(log_price_upper, dtype=np.float64).ravel()

    if not true_log.shape == lower_log.shape == upper_log.shape:
        msg = (
            f"shape mismatch: {true_log.shape} true, {lower_log.shape} lower, "
            f"{upper_log.shape} upper"
        )
        raise ValueError(msg)
    if true_log.size == 0:
        msg = "cannot score an empty prediction set"
        raise ValueError(msg)
    if np.any(lower_log > upper_log):
        crossed = int(np.sum(lower_log > upper_log))
        msg = f"{crossed} intervals have lower > upper (crossed quantiles)"
        raise ValueError(msg)

    lower_cop = to_pesos(lower_log)
    upper_cop = to_pesos(upper_log)
    centre_cop = to_pesos((lower_log + upper_log) / 2.0)

    below = true_log < lower_log
    above = true_log > upper_log

    return IntervalReport(
        n=int(true_log.size),
        coverage=float(np.mean(~(below | above))),
        mean_relative_width=float(np.mean((upper_cop - lower_cop) / centre_cop)),
        below_rate=float(np.mean(below)),
        above_rate=float(np.mean(above)),
    )
