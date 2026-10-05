"""SHAP attributions for the LightGBM valuation model — what feeds ``/explain``.

The model predicts ``log(price)``, and that single fact decides the shape of everything
here. SHAP values are additive **in log space**: ``base + sum(phi) == predicted log
price``, exactly, which is the invariant :mod:`tests.models.test_explain` asserts on every
row. Pesos are not additive, so "the model year adds $3.200.000" cannot be said without
lying about what the model did.

What is exactly true is the multiplicative reading. Since
``price = exp(base) * prod(exp(phi_i))``, each ``exp(phi_i)`` is a factor on the price:
``exp(-0.46) = 0.63`` means "this vehicle is worth 37 % less because of its age". That is
the primary output of this module, it is exact rather than approximate, and it happens to
be how a buyer already thinks about a used vehicle.

A peso figure is still offered, because a product has to show money, but as a derived and
clearly labelled approximation — see :func:`_approximate_pesos` for what it does and when
it refuses to answer.

LightGBM only. CatBoost would need its own path and is not the served model; which of the
two survives is still an open decision in ``docs/STATUS.md``.
"""

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from autovalor.models.trees import UNKNOWN_CATEGORY, FittedTree

EXPLAINED_KIND: Final = "lightgbm"
"""The only model this module explains."""

CANCELLATION_TOLERANCE: Final = 1e-6
"""Below this total log contribution the peso approximation is left undefined.

The approximation shares the price delta out in proportion to each ``phi``. When the
contributions cancel, the total is near zero while the individual terms are not, so the
shares would be arbitrarily large and signed almost at random. Returning ``NaN`` says "no
honest peso figure exists for this row" instead of printing a confident wrong number.
"""


@dataclass(frozen=True)
class Explanation:
    """Attribution of one batch of predictions.

    Attributes:
        base_log_price: The explainer's expected ``log(price)`` over the fitting data —
            where every explanation starts before any feature moves it.
        contributions: One row per listing and feature. ``phi`` is the log-space
            contribution, ``factor`` is ``exp(phi)``, and ``approx_cop`` is the labelled
            peso approximation.
        predicted_log_price: The model's prediction per listing, in frame order.
    """

    base_log_price: float
    contributions: pd.DataFrame
    predicted_log_price: npt.NDArray[np.float64]

    @property
    def base_price_cop(self) -> float:
        """The starting price every explanation departs from, in pesos."""
        return float(np.exp(self.base_log_price))


def shap_contributions(fitted: FittedTree, frame: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Return the raw log-space SHAP values and the base value.

    Args:
        fitted: A fitted LightGBM model.
        frame: Rows to explain, straight from gold.

    Returns:
        A wide frame of ``phi`` — the frame's index, one column per feature in fitting
        order — and the expected ``log(price)``.

    Raises:
        ValueError: If ``fitted`` is not a LightGBM model.
    """
    _require_lightgbm(fitted)
    import shap

    prepared = fitted.design_matrix(frame)
    explainer = shap.TreeExplainer(fitted.estimator)
    values = np.asarray(explainer.shap_values(prepared), dtype=np.float64)
    base = float(np.ravel(explainer.expected_value)[0])
    return pd.DataFrame(values, index=frame.index, columns=list(fitted.spec.columns)), base


def explain_predictions(fitted: FittedTree, frame: pd.DataFrame) -> Explanation:
    """Explain every row of ``frame``, in log space, as factors and in pesos.

    Args:
        fitted: A fitted LightGBM model.
        frame: Rows to explain, straight from gold.

    Returns:
        The explanation. ``contributions`` is long rather than wide — one row per listing
        and feature — because that is the shape both the API response and a bar chart
        want, and it keeps the displayed feature value next to its contribution.

    Raises:
        ValueError: If ``fitted`` is not a LightGBM model.
    """
    phi, base = shap_contributions(fitted, frame)
    predicted = fitted.predict_log_price(frame)

    long = _to_long(phi, "phi")
    long = long.merge(_to_long(_displayed_values(fitted, frame), "value"), on=["row", "feature"])
    long["factor"] = np.exp(long["phi"])
    long["approx_cop"] = _approximate_pesos(long, phi=phi, base=base, predicted=predicted)

    if "listing_id" in frame.columns:
        long.insert(0, "listing_id", frame.loc[long["row"], "listing_id"].to_numpy())

    ordered = ["row", "feature", "value", "phi", "factor", "approx_cop"]
    if "listing_id" in long.columns:
        ordered.insert(0, "listing_id")
    contributions = _rank_within_rows(long.loc[:, ordered])
    return Explanation(
        base_log_price=base,
        contributions=contributions,
        predicted_log_price=predicted,
    )


def global_importance(fitted: FittedTree, frame: pd.DataFrame) -> pd.DataFrame:
    """Rank the features by mean absolute contribution.

    Args:
        fitted: A fitted LightGBM model.
        frame: Rows to average over — the holdout, normally.

    Returns:
        One row per feature, most important first, with the mean ``|phi|`` in log space
        and the same figure read as a typical percentage swing in price.

    Raises:
        ValueError: If ``fitted`` is not a LightGBM model.
    """
    phi, _ = shap_contributions(fitted, frame)
    mean_abs = phi.abs().mean().sort_values(ascending=False)
    return pd.DataFrame(
        {
            "feature": mean_abs.index,
            "mean_abs_phi": mean_abs.to_numpy(),
            # exp(|phi|) - 1: the typical size of this feature's pull on the price,
            # ignoring its direction.
            "mean_abs_pct": np.expm1(mean_abs.to_numpy()),
        }
    ).reset_index(drop=True)


def top_drivers(fitted: FittedTree, frame: pd.DataFrame, *, k: int = 5) -> pd.DataFrame:
    """Return the ``k`` largest contributions per listing — what ``/explain`` will answer.

    Args:
        fitted: A fitted LightGBM model.
        frame: Rows to explain.
        k: How many contributions to keep per listing.

    Returns:
        The ``contributions`` frame of :func:`explain_predictions`, truncated to the ``k``
        largest absolute contributions of each row.

    Raises:
        ValueError: If ``k`` is below 1, or ``fitted`` is not a LightGBM model.
    """
    if k < 1:
        msg = f"k must be 1 or greater, got {k}"
        raise ValueError(msg)

    contributions = explain_predictions(fitted, frame).contributions
    return contributions.groupby("row", sort=False).head(k).reset_index(drop=True)


def _to_long(wide: pd.DataFrame, value_name: str) -> pd.DataFrame:
    """Melt a row-by-feature frame into ``row``, ``feature`` and one value column."""
    return wide.reset_index(names="row").melt(
        id_vars="row", var_name="feature", value_name=value_name
    )


def _rank_within_rows(long: pd.DataFrame) -> pd.DataFrame:
    """Order the contributions by listing, largest absolute contribution first."""
    ranked = long.assign(_magnitude=long["phi"].abs())
    ordered = ranked.sort_values(["row", "_magnitude"], ascending=[True, False])
    return ordered.drop(columns="_magnitude").reset_index(drop=True)


def _require_lightgbm(fitted: FittedTree) -> None:
    if fitted.model_kind != EXPLAINED_KIND:
        msg = (
            f"only {EXPLAINED_KIND} predictions are explained, got {fitted.model_kind!r}; "
            "CatBoost needs its own path and is not the served model"
        )
        raise ValueError(msg)


def _displayed_values(fitted: FittedTree, frame: pd.DataFrame) -> pd.DataFrame:
    """Return the feature values as strings, for an explanation a human can read.

    "brand: +12 %" is unreadable without the level that produced it. A categorical that
    fell outside the fitted levels reads as unknown, which is exactly what the model saw:
    those rows went down the missing branch.
    """
    prepared = fitted.design_matrix(frame)
    shown = pd.DataFrame(index=frame.index, columns=list(fitted.spec.columns), dtype=object)
    for column in fitted.spec.columns:
        values = prepared[column]
        if column in fitted.spec.categorical:
            text = values.astype("string")
        elif column in fitted.spec.boolean:
            # _model_matrix casts booleans to 0.0/1.0; "1" would be unreadable.
            text = values.map({1.0: "true", 0.0: "false"}).astype("string")
        else:
            text = values.map(_format_number).astype("string")
        shown[column] = text.fillna(UNKNOWN_CATEGORY)
    return shown


def _format_number(value: float) -> str | None:
    """Render a numeric feature without the noise of trailing zeros."""
    if value is None or not np.isfinite(value):
        return None
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}"


def _approximate_pesos(
    long: pd.DataFrame,
    *,
    phi: pd.DataFrame,
    base: float,
    predicted: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Share the peso delta out in proportion to each log contribution.

    This is **approximate and labelled as such**. Two properties are worth knowing before
    showing the number to anyone:

    * It adds up exactly. The shares sum to ``exp(predicted) - exp(base)``, so a waterfall
      built from them lands on the predicted price.
    * No single share is exact, because ``exp`` is not additive. The error grows with the
      size of the contribution, which is precisely where someone would care.

    When the contributions cancel — total log movement near zero while individual terms
    are not — the shares are undefined and come back as ``NaN``. The factors in
    ``factor`` are exact in every case; this column never is.
    """
    total_phi = pd.Series(phi.sum(axis=1), index=phi.index)
    delta = pd.Series(np.exp(predicted) - np.exp(base), index=phi.index)

    row_total = total_phi.loc[long["row"]].to_numpy()
    row_delta = delta.loc[long["row"]].to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        shares = long["phi"].to_numpy() / row_total * row_delta
    return np.where(np.abs(row_total) < CANCELLATION_TOLERANCE, np.nan, shares)
