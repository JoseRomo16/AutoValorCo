"""P10-P90 price bands by conformalized quantile regression.

The band is a product requirement, not a decoration: the bargain / fair / expensive label
is exactly "where does the asking price fall relative to the band". So it has to come from
models that estimate the conditional quantiles directly, not from the spread of the point
model's residuals — that would assume the error has the same width for a 2008 Spark with
200.000 km as for a 2024 Mazda, which it does not.

Three LightGBM models are fitted with the quantile objective, one per level in
:data:`QUANTILES`. LightGBM is the backbone because it won both verticals in F2 step 3.
Each one goes through :func:`autovalor.models.trees.fit_tree`, so they inherit the frozen
category levels and the same feature specification as the point model.

**Why the conformal step is not optional.** Fitted that way and used directly, the band
covered 67 % of held-out car listings and 63 % of motorcycles against a nominal 80 %:
boosted trees fit the training quantiles tightly, and the band comes out too narrow on
rows they have not seen. A band advertised as 80 % that holds 63 % is worse than no band,
because the bargain label would fire on ordinary listings. So the levels are calibrated the
distribution-free way (Romano, Patterson & Candès, 2019): part of the training rows is held
back, the band's own error on those rows is measured, and the bounds are widened by the
quantile of that error which restores the nominal coverage. The widening is a single number
on the log scale, so it stretches the band proportionally in pesos.

Independently fitted quantiles can also come out crossed — a P10 above the P90 for some
row. That is a property of fitting them separately, not a bug to hide, so the predictions
are sorted per row and the share of rows that needed it is reported as
:attr:`FittedInterval.crossing_rate`.
"""

import logging
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd

from autovalor.models.dataset import DEFAULT_SEED, VehicleType, split_listings
from autovalor.models.metrics import IntervalReport
from autovalor.models.trees import DEFAULT_PARAMS, FittedTree, fit_tree

logger = logging.getLogger("autovalor.models")

LOWER_QUANTILE = 0.10
MEDIAN_QUANTILE = 0.50
UPPER_QUANTILE = 0.90

QUANTILES: tuple[float, float, float] = (LOWER_QUANTILE, MEDIAN_QUANTILE, UPPER_QUANTILE)
"""The levels the product asks for. P10-P90 is a nominal 80 % band, which leaves roughly
one listing in ten on each side — the bargains and the overpriced."""

NOMINAL_COVERAGE = UPPER_QUANTILE - LOWER_QUANTILE
"""Share of asking prices the band is supposed to contain, 0.80 here."""

CALIBRATION_FRACTION = 0.25
"""Share of the training rows held back to calibrate the band.

The point model still trains on all of them; only the band pays this cost. A quarter of
3.012 motorcycle rows is ~750, enough for the conformal quantile to be stable.
"""

Label = Literal["bargain", "fair", "expensive"]

BARGAIN: Label = "bargain"
FAIR: Label = "fair"
EXPENSIVE: Label = "expensive"

MIN_LABEL_COVERAGE = 0.78
MAX_LABEL_COVERAGE = 0.82
"""Coverage window the band must land in before its label may be published.

Two-sided on purpose. Under-coverage is the obvious failure — a band advertised as 80 %
that holds 76 % calls ordinary listings bargains. Over-coverage is a failure too: it means
the conformal step widened past what the data asked for, so "fair" absorbs listings that
are genuinely mispriced and the label stops discriminating. Either way the number stops
meaning what the product says it means, so the rule is a window and not a floor.
"""

MAX_LABEL_RELATIVE_WIDTH = 0.60
"""Widest band, as a share of the estimate, that still carries a usable label.

Measured as ``(upper - lower) / estimate`` in pesos. At 60 % the band runs roughly from
three quarters to one and a third of the estimate, which still separates a bargain from an
ordinary price. The motorcycle band of F2 step 4 sat at 94 %, i.e. from about half to
double: every honest listing lands inside it and the label says nothing.
"""


@dataclass(frozen=True)
class FittedInterval:
    """Three quantile models plus the conformal correction that calibrates them.

    Attributes:
        vehicle_type: Vertical they were fitted for.
        models: One fitted model per level in :data:`QUANTILES`.
        widening: Amount added to the upper bound and subtracted from the lower one, on
            the log scale. Positive means the raw band was too narrow, which is the usual
            case; negative means it was too wide and the conformal step tightened it.
        crossing_rate: Share of calibration rows whose raw quantile predictions came out
            in the wrong order and had to be sorted. A high value means the levels
            disagree about the shape of the price surface.
        n_calibration: Rows the widening was measured on.
    """

    vehicle_type: VehicleType
    models: dict[float, FittedTree]
    widening: float
    crossing_rate: float
    n_calibration: int

    def predict_log_bounds(self, frame: pd.DataFrame) -> npt.NDArray[np.float64]:
        """Predict the calibrated band on the log scale.

        Args:
            frame: Rows to score, straight from gold.

        Returns:
            An ``(n, 3)`` array of ``log(price)`` at the lower bound, the median and the
            upper bound, sorted along each row so the bounds are never crossed.
        """
        raw = np.sort(_raw_bounds(self.models, frame), axis=1)
        calibrated = raw.copy()
        calibrated[:, 0] -= self.widening
        calibrated[:, 2] += self.widening
        # Widening by a negative number can push a bound past the median; sorting again
        # keeps the three values ordered whatever the correction did.
        return np.sort(calibrated, axis=1)

    def predict_log_price(self, frame: pd.DataFrame) -> npt.NDArray[np.float64]:
        """Predict the median ``log(price)``, satisfying the point-model interface.

        Args:
            frame: Rows to score, straight from gold.

        Returns:
            The P50 prediction, one value per row.
        """
        bounds: npt.NDArray[np.float64] = self.predict_log_bounds(frame)[:, 1]
        return bounds


def _raw_bounds(models: dict[float, FittedTree], frame: pd.DataFrame) -> npt.NDArray[np.float64]:
    """Return the unsorted, uncalibrated ``(n, 3)`` predictions, in :data:`QUANTILES` order."""
    return np.column_stack([models[quantile].predict_log_price(frame) for quantile in QUANTILES])


def conformal_widening(
    log_price: npt.ArrayLike,
    log_lower: npt.ArrayLike,
    log_upper: npt.ArrayLike,
    *,
    coverage: float = NOMINAL_COVERAGE,
) -> float:
    """Return how much to widen a band so it reaches the nominal coverage.

    The conformity score of a row is how far outside the band its price fell, negative
    when it fell inside. Taking the right quantile of those scores gives a correction that
    makes the band cover ``coverage`` of exchangeable future rows, with no assumption about
    the shape of the error.

    Args:
        log_price: Observed ``log(price)`` on the calibration rows.
        log_lower: Raw lower bound predicted for those rows.
        log_upper: Raw upper bound predicted for those rows.
        coverage: Share of rows the calibrated band should contain.

    Returns:
        The widening, on the log scale. May be negative when the raw band is too wide.

    Raises:
        ValueError: If the arrays differ in length or are empty.
    """
    price = np.asarray(log_price, dtype=np.float64).ravel()
    lower = np.asarray(log_lower, dtype=np.float64).ravel()
    upper = np.asarray(log_upper, dtype=np.float64).ravel()

    if not price.shape == lower.shape == upper.shape:
        msg = f"shape mismatch: {price.shape} price, {lower.shape} lower, {upper.shape} upper"
        raise ValueError(msg)
    if price.size == 0:
        msg = "cannot calibrate a band on zero rows"
        raise ValueError(msg)

    scores = np.maximum(lower - price, price - upper)
    # The finite-sample level: with n calibration rows the guarantee needs the
    # ceil((n+1) * coverage)-th smallest score, which is why this is not simply `coverage`.
    rank = min(int(np.ceil((price.size + 1) * coverage)), price.size)
    level = rank / price.size
    return float(np.quantile(scores, level, method="higher"))


def fit_interval(
    train: pd.DataFrame,
    *,
    vehicle_type: VehicleType,
    params: dict[str, Any] | None = None,
    seed: int = DEFAULT_SEED,
    calibration_fraction: float = CALIBRATION_FRACTION,
) -> FittedInterval:
    """Fit one LightGBM quantile model per level and calibrate the band.

    Args:
        train: Training rows from gold. Part of them is held back for calibration, so the
            quantile models see fewer rows than the point model does.
        vehicle_type: Vertical being modeled.
        params: Base hyperparameters, normally the ones tuned for the point model. The
            quantile objective and its level are set here and override anything passed in.
        seed: Seed for the calibration split and the models.
        calibration_fraction: Share of ``train`` held back to measure the widening.

    Returns:
        The three fitted models with the conformal correction that calibrates them.
    """
    base = dict(DEFAULT_PARAMS["lightgbm"] if params is None else params)
    # The objective is this module's business, not the caller's: a point-model parameter
    # set carries no objective, and a tuned one must not silently override the level.
    base.pop("objective", None)
    base.pop("alpha", None)

    # Reuses the grouped splitter, so a reposted vehicle cannot sit in both the fitting and
    # the calibration half -- the same leakage that would flatter the widening downwards.
    inner = split_listings(train, test_size=calibration_fraction, seed=seed)

    models = {
        quantile: fit_tree(
            inner.train,
            model_kind="lightgbm",
            vehicle_type=vehicle_type,
            params={**base, "objective": "quantile", "alpha": quantile},
            seed=seed,
        )
        for quantile in QUANTILES
    }

    raw = _raw_bounds(models, inner.test)
    crossing_rate = float(np.mean(np.any(np.diff(raw, axis=1) < 0, axis=1)))
    ordered = np.sort(raw, axis=1)
    widening = conformal_widening(inner.test["log_price"], ordered[:, 0], ordered[:, 2])

    logger.info(
        "%s band — fitted on %d rows, calibrated on %d, widening %+.3f in log space, "
        "crossed on %.1f%% of calibration rows",
        vehicle_type,
        inner.n_train,
        inner.n_test,
        widening,
        crossing_rate * 100,
    )
    return FittedInterval(
        vehicle_type=vehicle_type,
        models=models,
        widening=widening,
        crossing_rate=crossing_rate,
        n_calibration=inner.n_test,
    )


def classify(
    asking_log_price: npt.ArrayLike,
    log_lower: npt.ArrayLike,
    log_upper: npt.ArrayLike,
) -> list[Label]:
    """Label each asking price against its predicted band.

    The comparison happens on the log scale because that is where the models work, and it
    gives the same answer as comparing pesos — the exponential is monotone.

    Args:
        asking_log_price: Observed ``log(price)`` of the listing.
        log_lower: Predicted lower bound on the log scale.
        log_upper: Predicted upper bound on the log scale.

    Returns:
        One label per row: ``bargain`` below the band, ``expensive`` above it, ``fair``
        inside it, bounds included.

    Raises:
        ValueError: If the arrays differ in length or any lower bound exceeds its upper
            bound — a crossed band cannot produce a meaningful label.
    """
    asking = np.asarray(asking_log_price, dtype=np.float64).ravel()
    lower = np.asarray(log_lower, dtype=np.float64).ravel()
    upper = np.asarray(log_upper, dtype=np.float64).ravel()

    if not asking.shape == lower.shape == upper.shape:
        msg = f"shape mismatch: {asking.shape} asking, {lower.shape} lower, {upper.shape} upper"
        raise ValueError(msg)
    if np.any(lower > upper):
        crossed = int(np.sum(lower > upper))
        msg = f"{crossed} bands have lower > upper; sort them before classifying"
        raise ValueError(msg)

    labels: list[Label] = []
    for price, low, high in zip(asking, lower, upper, strict=True):
        if price < low:
            labels.append(BARGAIN)
        elif price > high:
            labels.append(EXPENSIVE)
        else:
            labels.append(FAIR)
    return labels


@dataclass(frozen=True)
class LabelPolicy:
    """Whether a vertical has earned the right to show the bargain/fair/expensive label.

    The label is a claim about where a price sits inside a band, so it is only worth as
    much as the band. Two measured properties decide it, and both have to hold:

    * **Coverage** inside ``[MIN_LABEL_COVERAGE, MAX_LABEL_COVERAGE]`` — the band holds
      what it says it holds.
    * **Mean relative width** at or below :data:`MAX_LABEL_RELATIVE_WIDTH` — the band is
      narrow enough that falling outside it means something.

    When either fails the vertical still ships: an estimated price and the range, with
    :attr:`precision_notice` explaining what is missing. Dropping the vertical would be an
    overreaction; showing a label the measurement does not support would be a false claim.

    The gate reads a held-out :class:`~autovalor.models.metrics.IntervalReport`, never a
    training one. Deciding on in-sample coverage would wave through exactly the bands this
    exists to stop.

    Attributes:
        vehicle_type: Vertical the decision applies to.
        coverage: Held-out share of asking prices that fell inside the band.
        mean_relative_width: Held-out mean of ``(upper - lower) / estimate``, in pesos.
        n: Rows both figures were measured on.
        failures: One message per rule that failed, empty when the label is published.
    """

    vehicle_type: VehicleType
    coverage: float
    mean_relative_width: float
    n: int
    failures: tuple[str, ...]

    @property
    def publishes_label(self) -> bool:
        """Whether the bargain/fair/expensive label may be shown for this vertical."""
        return not self.failures

    @property
    def precision_notice(self) -> str | None:
        """What to tell the user instead of a label, or ``None`` when one is published.

        Phrased as the product's own caveat rather than a model diagnostic, because this
        string exists to be rendered next to the estimate.
        """
        if self.publishes_label:
            return None
        return (
            "Estimate and range only: the price band for this vertical is not precise "
            f"enough to call a listing a bargain or expensive ({'; '.join(self.failures)})."
        )

    def labels(
        self,
        asking_log_price: npt.ArrayLike,
        log_lower: npt.ArrayLike,
        log_upper: npt.ArrayLike,
    ) -> list[Label] | None:
        """Classify the rows, or return ``None`` when the band has not earned a label.

        This is the call sites' entry point, so a caller cannot skip the gate by reaching
        for :func:`classify` without noticing.

        Args:
            asking_log_price: Observed ``log(price)`` of the listings.
            log_lower: Predicted lower bound on the log scale.
            log_upper: Predicted upper bound on the log scale.

        Returns:
            One label per row when :attr:`publishes_label` holds, ``None`` otherwise.
        """
        if not self.publishes_label:
            return None
        return classify(asking_log_price, log_lower, log_upper)


def label_policy(report: IntervalReport, *, vehicle_type: VehicleType) -> LabelPolicy:
    """Decide whether a measured band may carry the label.

    Args:
        report: Held-out quality of the band, from
            :func:`autovalor.models.metrics.interval_report`.
        vehicle_type: Vertical the band was fitted for.

    Returns:
        The decision, carrying the numbers it was taken on so a report can quote them.
    """
    failures: list[str] = []
    if not MIN_LABEL_COVERAGE <= report.coverage <= MAX_LABEL_COVERAGE:
        failures.append(
            f"coverage {report.coverage:.1%} outside "
            f"{MIN_LABEL_COVERAGE:.0%}-{MAX_LABEL_COVERAGE:.0%}"
        )
    if report.mean_relative_width > MAX_LABEL_RELATIVE_WIDTH:
        failures.append(
            f"mean width {report.mean_relative_width:.0%} of the estimate, "
            f"above {MAX_LABEL_RELATIVE_WIDTH:.0%}"
        )

    policy = LabelPolicy(
        vehicle_type=vehicle_type,
        coverage=report.coverage,
        mean_relative_width=report.mean_relative_width,
        n=report.n,
        failures=tuple(failures),
    )
    logger.info(
        "%s label — %s (coverage %.1f%%, mean width %.0f%% on %d held-out rows)",
        vehicle_type,
        "published" if policy.publishes_label else "withheld: " + "; ".join(failures),
        report.coverage * 100,
        report.mean_relative_width * 100,
        report.n,
    )
    return policy
