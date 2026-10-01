import math

import numpy as np
import pytest

from autovalor.models.metrics import (
    interval_report,
    regression_report,
    smearing_factor,
    to_pesos,
)


def test_a_perfect_fit_scores_zero_error() -> None:
    truth = np.log([20_000_000, 35_000_000, 50_000_000])

    report = regression_report(truth, truth)

    assert report.mape == 0.0
    assert report.mae_cop == 0.0
    assert report.sigma_log == 0.0
    assert report.r2_log == 1.0
    assert report.within_10pct == 1.0


def test_mape_is_measured_in_pesos_not_in_log_space() -> None:
    # A listing at 20M predicted as 22M is a 10 % error; in log space the gap is 0.095,
    # and reporting that as the error would understate what a user experiences.
    truth = np.log([20_000_000.0])
    predicted = np.log([22_000_000.0])

    report = regression_report(truth, predicted)

    assert report.mape == pytest.approx(0.10)
    assert report.mae_cop == pytest.approx(2_000_000.0)


def test_median_ape_ignores_a_single_wild_miss() -> None:
    truth = np.log([20_000_000.0] * 10)
    predicted = np.log([20_000_000.0] * 9 + [200_000_000.0])

    report = regression_report(truth, predicted)

    assert report.median_ape == pytest.approx(0.0)
    assert report.mape > 0.8


def test_hit_rates_count_the_tolerance_band() -> None:
    truth = np.log([10_000_000.0, 10_000_000.0, 10_000_000.0])
    predicted = np.log([10_400_000.0, 11_500_000.0, 20_000_000.0])

    report = regression_report(truth, predicted)

    assert report.within_10pct == pytest.approx(1 / 3)
    assert report.within_20pct == pytest.approx(2 / 3)


def test_report_rejects_mismatched_shapes() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        regression_report([1.0, 2.0], [1.0])


def test_report_rejects_an_empty_prediction_set() -> None:
    with pytest.raises(ValueError, match="empty"):
        regression_report([], [])


def test_report_rejects_non_finite_predictions() -> None:
    # A nan slipping through would be logged to MLflow as a result.
    with pytest.raises(ValueError, match="finite"):
        regression_report([17.0, 17.5], [17.0, float("nan")])


def test_r2_is_undefined_for_a_constant_target() -> None:
    report = regression_report([17.0, 17.0], [17.0, 17.1])

    assert math.isnan(report.r2_log)


def test_as_dict_is_flat_and_numeric() -> None:
    report = regression_report([17.0, 17.5], [17.1, 17.4])

    as_dict = report.as_dict()
    assert set(as_dict) == {
        "n",
        "mape",
        "median_ape",
        "mae_cop",
        "rmse_cop",
        "sigma_log",
        "r2_log",
        "within_10pct",
        "within_20pct",
    }
    assert all(isinstance(value, float) for value in as_dict.values())


def test_summary_stays_ascii() -> None:
    # The development console is cp1252 and raises on sigma or plus-minus signs.
    summary = regression_report([17.0, 17.5], [17.1, 17.4]).summary()

    summary.encode("cp1252")


def test_to_pesos_inverts_the_log() -> None:
    assert to_pesos(np.log([25_000_000.0]))[0] == pytest.approx(25_000_000.0)


def test_smearing_is_one_for_a_centred_fit_and_above_it_for_spread() -> None:
    assert smearing_factor([0.0, 0.0]) == pytest.approx(1.0)
    assert smearing_factor([-0.4, 0.4]) > 1.0


def test_interval_coverage_counts_prices_inside_the_band() -> None:
    truth = np.log([10_000_000.0, 20_000_000.0, 30_000_000.0, 40_000_000.0])
    lower = np.log([9_000_000.0, 19_000_000.0, 31_000_000.0, 20_000_000.0])
    upper = np.log([11_000_000.0, 21_000_000.0, 35_000_000.0, 30_000_000.0])

    report = interval_report(truth, lower, upper)

    assert report.coverage == pytest.approx(0.5)
    assert report.below_rate == pytest.approx(0.25)
    assert report.above_rate == pytest.approx(0.25)
    assert report.mean_relative_width > 0


def test_interval_report_rejects_crossed_quantiles() -> None:
    with pytest.raises(ValueError, match="crossed quantiles"):
        interval_report([17.0], [18.0], [16.0])


def test_interval_report_rejects_mismatched_shapes() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        interval_report([17.0, 17.5], [16.0], [18.0])


def test_interval_report_rejects_an_empty_prediction_set() -> None:
    with pytest.raises(ValueError, match="empty"):
        interval_report([], [], [])


def test_interval_as_dict_is_flat_and_numeric() -> None:
    report = interval_report([17.0], [16.5], [17.5])

    assert set(report.as_dict()) == {
        "n",
        "coverage",
        "mean_relative_width",
        "below_rate",
        "above_rate",
    }
