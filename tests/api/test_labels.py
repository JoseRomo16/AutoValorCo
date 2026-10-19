"""Tests for the human names and formatted values of /explain.

Formatting lives in the API because it depends on what a feature *means*: 1600 is cc, 8 is
years and False is "No". These tests pin the unit to the feature, which is the part a
frontend cannot re-derive from a number and a column name.
"""

import numpy as np
import pytest

from autovalor.api.labels import FEATURE_LABELS, MISSING, feature_label, format_value


def test_every_label_is_translated_and_is_not_the_column_name() -> None:
    for feature, label in FEATURE_LABELS.items():
        assert label.es and label.en
        assert label.es != feature, "showing a column name is the bug this table fixes"


def test_an_unnamed_feature_falls_back_to_its_column_name() -> None:
    # An unlabelled factor is still a true factor; dropping it would silently shorten the
    # explanation, which is worse than showing a raw name.
    assert feature_label("some_new_column").es == "some_new_column"


@pytest.mark.parametrize(
    ("feature", "value", "spanish", "english"),
    [
        ("mileage_km", 60_000.0, "60.000 km", "60,000 km"),
        ("mileage_km", 0.0, "0 km", "0 km"),
        ("engine_cc", 1600.0, "1.600 cc", "1,600 cc"),
        ("km_per_year", 7500.0, "7.500 km/año", "7,500 km/yr"),
        ("vehicle_age_years", 8.0, "8 años", "8 years"),
        ("vehicle_age_years", 1.0, "1 año", "1 year"),
        ("vehicle_age_years", 0.0, "0 años", "0 years"),
        ("brand", "BMW", "BMW", "BMW"),
        ("department", "Antioquia", "Antioquia", "Antioquia"),
        ("is_official_store", True, "Sí", "Yes"),
        ("is_quad", False, "No", "No"),
    ],
)
def test_values_carry_their_unit(feature: str, value: object, spanish: str, english: str) -> None:
    formatted = format_value(feature, value)

    assert formatted.es == spanish
    assert formatted.en == english


def test_a_model_token_is_capitalised_but_a_make_is_left_alone() -> None:
    # Model tokens are mined from titles in lower case; makes carry their own
    # capitalisation and "BMW" must not become "Bmw".
    assert format_value("model", "corolla").es == "Corolla"
    assert format_value("model", "cx-30").es == "Cx-30"
    assert format_value("brand", "Mercedes-Benz").es == "Mercedes-Benz"


def test_the_unknown_bucket_is_translated() -> None:
    # "Desconocida" is a level in the lake, not a word to print at an English reader.
    assert format_value("city", "Desconocida").en == "Unknown"
    assert format_value("city", "Desconocida").es == "Desconocida"


@pytest.mark.parametrize("missing", [None, float("nan"), np.nan])
def test_an_unsupplied_feature_says_so_rather_than_showing_a_zero(missing: object) -> None:
    # The model treats a missing displacement as its own signal, so it still carries a
    # contribution; "0 cc" would be a value nobody supplied.
    assert format_value("engine_cc", missing) == MISSING


def test_a_numpy_boolean_is_rendered_as_a_boolean() -> None:
    # The scored frame comes back from pandas, where a boolean column is np.bool_ and not
    # bool. Treated as a number it would print "1".
    assert format_value("is_official_store", np.bool_(True)).es == "Sí"
