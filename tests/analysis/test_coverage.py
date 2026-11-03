import numpy as np
import pandas as pd

from autovalor.analysis.coverage import feature_coverage


def test_coverage_counts_the_rows_that_carry_a_displacement() -> None:
    frame = pd.DataFrame({"engine_cc": [1600.0, np.nan, 2000.0, np.nan]})

    table = feature_coverage(frame, vehicle_type="car")

    row = table.iloc[0]
    assert row["vehicle_type"] == "car"
    assert row["feature"] == "engine_cc"
    assert (row["rows"], row["covered"]) == (4, 2)
    assert row["coverage_pct"] == 50.0


def test_an_empty_vertical_reports_zero_rather_than_dividing_by_it() -> None:
    table = feature_coverage(pd.DataFrame({"engine_cc": []}), vehicle_type="motorcycle")

    assert table.iloc[0]["coverage_pct"] == 0.0


def test_a_frame_without_the_column_is_uncovered() -> None:
    table = feature_coverage(pd.DataFrame({"brand": ["Yamaha"]}), vehicle_type="motorcycle")

    assert (table.iloc[0]["rows"], table.iloc[0]["covered"]) == (1, 0)
