import pandas as pd
import pytest

from autovalor.analysis.catalogue import (
    CONDITION_FEATURES,
    IDENTITY_FEATURES,
    catalogue_contrast,
    hedonic_age_effect,
    pull_shares,
)
from autovalor.analysis.segments import SEGMENT_COLUMNS, segment_errors, worst_segments
from autovalor.models.dataset import Dataset, split_listings
from autovalor.models.train import ModelResult, train_model

Fitted = tuple[ModelResult, Dataset]


@pytest.fixture(scope="module")
def fitted(cars: pd.DataFrame) -> Fitted:
    """A cheap LightGBM fit on the synthetic cars, with its partition.

    Module-scoped: it is the most expensive thing in this package's tests — a fit plus a
    SHAP pass — and every test below only reads it. CI has twenty minutes for the whole
    suite, so re-fitting it five times is a cost with nothing bought.
    """
    dataset = split_listings(cars, test_size=0.3)
    result = train_model(dataset, "lightgbm", n_trials=0, intervals=False, explain=True)
    return result, dataset


def test_every_cut_is_reported(fitted: Fitted) -> None:
    result, dataset = fitted

    errors = segment_errors(result, dataset, min_rows=10)

    assert set(errors["segment_kind"]) == set(SEGMENT_COLUMNS)


def test_a_thin_segment_is_not_reported(fitted: Fitted) -> None:
    result, dataset = fitted

    generous = segment_errors(result, dataset, min_rows=1)
    strict = segment_errors(result, dataset, min_rows=200)

    assert len(strict) < len(generous)
    assert (strict["n"] >= 200).all()


def test_the_segments_are_scored_on_the_holdout(fitted: Fitted) -> None:
    result, dataset = fitted

    errors = segment_errors(result, dataset, min_rows=1)

    # Each cut partitions the same holdout, so each cut's rows add back up to it.
    for _, cut in errors.groupby("segment_kind"):
        assert cut["n"].sum() == dataset.n_test


def test_worst_segments_takes_the_top_of_each_cut(fitted: Fitted) -> None:
    result, dataset = fitted
    errors = segment_errors(result, dataset, min_rows=10)

    worst = worst_segments(errors, k=2)

    assert len(worst) <= 2 * len(SEGMENT_COLUMNS)
    for kind, cut in worst.groupby("segment_kind"):
        full = errors[errors["segment_kind"] == kind]
        assert cut["mape_pct"].min() >= full["mape_pct"].nlargest(2).min() - 1e-9


def test_the_shares_apportion_the_whole_importance() -> None:
    importance = pd.DataFrame(
        {
            "feature": ["brand", "vehicle_age_years", "city"],
            "mean_abs_phi": [0.6, 0.3, 0.1],
            "mean_abs_pct": [0.0, 0.0, 0.0],
        }
    )

    shares = pull_shares(importance)

    assert shares["identity_share_pct"] == pytest.approx(60.0)
    assert shares["condition_share_pct"] == pytest.approx(30.0)
    assert shares["other_share_pct"] == pytest.approx(10.0)
    assert sum(shares.values()) == pytest.approx(100.0)


def test_condition_and_identity_do_not_overlap() -> None:
    # The whole finding is a ratio between the two, so a feature counted in both would
    # make it meaningless.
    assert not set(CONDITION_FEATURES) & set(IDENTITY_FEATURES)


def test_an_empty_importance_table_fails_loudly() -> None:
    importance = pd.DataFrame({"feature": ["brand"], "mean_abs_phi": [0.0], "mean_abs_pct": [0.0]})

    with pytest.raises(ValueError, match="sums to zero"):
        pull_shares(importance)


def test_the_hedonic_age_effect_is_negative_and_bracketed(cars: pd.DataFrame) -> None:
    effect = hedonic_age_effect(cars, vehicle_type="car")

    assert effect["annual_depreciation_pct"] > 0
    assert effect["annual_ci_low_pct"] <= effect["annual_depreciation_pct"]
    assert effect["annual_depreciation_pct"] <= effect["annual_ci_high_pct"]
    assert effect["median_age_years"] > 0


def test_the_contrast_has_one_row_per_vertical(
    fitted: Fitted, cars: pd.DataFrame, bikes: pd.DataFrame
) -> None:
    result, _ = fitted
    assert result.importance is not None

    contrast = catalogue_contrast(
        {"car": result.importance, "motorcycle": result.importance},
        {"car": cars, "motorcycle": bikes},
    )

    assert len(contrast) == 2
    assert set(contrast["vehicle_type"]) == {"car", "motorcycle"}
    assert (contrast["identity_over_condition"] > 0).all()
