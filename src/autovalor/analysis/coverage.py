"""How much of each vertical carries an optional feature.

The model accepts a displacement but most titles never state one, so how often gold has
it is what the methodology page has to quote when it says the field is optional. The
share moves with every capture, which is why it is measured here and exported rather than
typed into the page.
"""

import pandas as pd

#: Optional inputs whose coverage the methodology page quotes.
COVERED_FEATURES: tuple[str, ...] = ("engine_cc",)


def feature_coverage(frame: pd.DataFrame, *, vehicle_type: str) -> pd.DataFrame:
    """Return, per optional feature, how many gold rows carry a value.

    Args:
        frame: Gold rows for one vertical.
        vehicle_type: The vertical, written into every row.

    Returns:
        One row per feature in :data:`COVERED_FEATURES` with ``rows``, ``covered`` and
        ``coverage_pct`` (0 for an empty frame).
    """
    records = []
    for feature in COVERED_FEATURES:
        rows = len(frame)
        covered = int(frame[feature].notna().sum()) if feature in frame else 0
        records.append(
            {
                "vehicle_type": vehicle_type,
                "feature": feature,
                "rows": rows,
                "covered": covered,
                "coverage_pct": 100.0 * covered / rows if rows else 0.0,
            }
        )
    return pd.DataFrame.from_records(records)
