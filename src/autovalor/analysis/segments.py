"""Where the served model's error actually lands.

One MAPE for a vertical is an average over a market that is not uniform. A model at 11,3 %
overall can be at 8 % on the brands it has thousands of rows for and at 25 % on a thin one,
and only the second number tells you whether to show a price for that listing. This module
breaks the held-out error down three ways — by brand, by price quartile and by department —
using the same partition, the same tuned LightGBM and the same metric as ``make train``, so
the segment figures add up to the published one.

**Measured on the holdout only.** A per-segment error read off the training rows would say
more about which cells the trees memorised than about what a user would experience.

**Thin segments are reported as thin, not hidden.** A cell under
:data:`MIN_SEGMENT_ROWS` held-out rows gets no MAPE: with 20 listings the figure moves
several points if two of them are odd, so publishing it would invite exactly the
comparison it cannot support.
"""

import logging

import pandas as pd

from autovalor.analysis.mileage import price_segments
from autovalor.models.dataset import Dataset
from autovalor.models.hedonic import TARGET
from autovalor.models.metrics import regression_report
from autovalor.models.train import ModelResult

logger = logging.getLogger("autovalor.analysis")

MIN_SEGMENT_ROWS = 40
"""Held-out rows a segment needs before its MAPE is reported."""

SEGMENT_COLUMNS = ("brand", "price_segment", "department")
"""The three cuts. Price is binned into quartiles; the other two are taken as they are."""

PREDICTED = "predicted_log_price"
"""Column the model's holdout prediction is parked in while the breakdowns slice rows."""

COLUMNS = (
    "vehicle_type",
    "model",
    "segment_kind",
    "segment",
    "n",
    "mape_pct",
    "median_ape_pct",
    "sigma_log",
    "within_10pct",
)
"""Shape of the result, declared so an empty run still returns a sliceable frame."""


def segment_errors(
    result: ModelResult,
    dataset: Dataset,
    *,
    min_rows: int = MIN_SEGMENT_ROWS,
) -> pd.DataFrame:
    """Break one model's held-out error down by brand, price quartile and department.

    Args:
        result: A fit from :func:`autovalor.models.train.train_model`, normally the tuned
            LightGBM.
        dataset: The partition it was fitted on; only ``dataset.test`` is scored.
        min_rows: Held-out rows a segment needs to be reported.

    Returns:
        One row per segment, with its MAPE, median APE, sigma in log space and row count,
        sorted worst MAPE first within each cut. Segments under ``min_rows`` are dropped
        and counted in the log.
    """
    test = dataset.test.copy()
    test["price_segment"] = price_segments(test)
    # Carried as a column rather than a parallel array: every breakdown below slices rows,
    # and a positional array would have to be re-aligned at each one.
    test[PREDICTED] = result.model.predict_log_price(test)

    rows: list[dict[str, object]] = []
    skipped = 0
    for column in SEGMENT_COLUMNS:
        for value, group in test.groupby(test[column].fillna("Desconocido").astype(str)):
            if len(group) < min_rows:
                skipped += 1
                continue
            report = regression_report(group[TARGET], group[PREDICTED])
            rows.append(
                {
                    "vehicle_type": result.vehicle_type,
                    "model": result.model_kind,
                    "segment_kind": column,
                    "segment": str(value),
                    "n": report.n,
                    "mape_pct": report.mape * 100.0,
                    "median_ape_pct": report.median_ape * 100.0,
                    "sigma_log": report.sigma_log,
                    "within_10pct": report.within_10pct * 100.0,
                }
            )

    if not rows:
        # Every cut was too thin. An empty frame with the right columns lets the caller
        # keep slicing it instead of branching, which a bare DataFrame() would not.
        logger.warning(
            "%s segment errors — nothing reported, all %d segments under %d rows",
            result.vehicle_type,
            skipped,
            min_rows,
        )
        return pd.DataFrame(columns=list(COLUMNS))

    errors = (
        pd.DataFrame(rows)
        .sort_values(["segment_kind", "mape_pct"], ascending=[True, False])
        .reset_index(drop=True)
    )
    logger.info(
        "%s segment errors — %d segments reported, %d under %d rows, MAPE from %.1f%% to %.1f%%",
        result.vehicle_type,
        len(errors),
        skipped,
        min_rows,
        errors["mape_pct"].min(),
        errors["mape_pct"].max(),
    )
    return errors


def worst_segments(errors: pd.DataFrame, *, k: int = 5) -> pd.DataFrame:
    """Return the ``k`` worst segments of each cut — the shortlist F3 has to explain.

    Args:
        errors: Output of :func:`segment_errors`.
        k: Segments per cut.

    Returns:
        The worst ``k`` rows per ``segment_kind``, by MAPE.
    """
    if errors.empty:
        return errors
    return (
        errors.sort_values("mape_pct", ascending=False)
        .groupby(["vehicle_type", "segment_kind"], as_index=False)
        .head(k)
        .reset_index(drop=True)
    )
