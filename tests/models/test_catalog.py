"""Tests for the served model's catalogue.

The property that matters is not "the JSON has brands in it": it is that the lists and the
model's frozen categories describe the same population. A catalogue built from a different
frame than the model was fitted on would let the form offer a make the trees have no
category for, and the resulting estimate would look exactly as confident as a real one.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from autovalor.models.catalog import (
    CATALOG_NAME,
    CatalogError,
    build_catalog,
    load_catalog,
    save_catalog,
)
from autovalor.models.trees import fit_tree

from .conftest import make_gold_frame


@pytest.fixture
def cars() -> pd.DataFrame:
    return make_gold_frame(300, vehicle_type="car")


def test_models_are_nested_under_their_make(cars: pd.DataFrame) -> None:
    catalog = build_catalog(cars, vehicle_type="car")

    for brand in catalog.brands:
        seen = set(cars.loc[cars["brand"] == brand.name, "model"].dropna())
        assert {model.name for model in brand.models} == seen


def test_the_counts_add_up(cars: pd.DataFrame) -> None:
    catalog = build_catalog(cars, vehicle_type="car")

    assert catalog.n_rows == len(cars)
    assert sum(brand.listings for brand in catalog.brands) == len(cars)
    # A listing with no model token still counts towards its make, so the models of a make
    # can sum to less than the make itself. Never to more.
    for brand in catalog.brands:
        assert sum(model.listings for model in brand.models) <= brand.listings


def test_levels_are_alphabetical(cars: pd.DataFrame) -> None:
    # These land in a <select>, where a reader scans for a name. The count travels with
    # each entry, so a client that wants popularity order can still have it.
    catalog = build_catalog(cars, vehicle_type="car")

    assert [brand.name for brand in catalog.brands] == sorted(
        brand.name for brand in catalog.brands
    )
    assert [entry.name for entry in catalog.departments] == sorted(
        entry.name for entry in catalog.departments
    )


def test_every_listed_level_is_one_the_model_has_a_category_for(cars: pd.DataFrame) -> None:
    # The whole point of deriving the catalogue from the training frame. If this can fail,
    # the form can offer a make the trees route down their missing branch.
    model = fit_tree(cars, model_kind="lightgbm", vehicle_type="car")
    catalog = build_catalog(cars, vehicle_type="car")

    known_brands = set(model.levels["brand"].astype(str))
    known_models = set(model.levels["model"].astype(str))
    assert {brand.name for brand in catalog.brands} <= known_brands
    assert {m.name for brand in catalog.brands for m in brand.models} <= known_models


def test_the_year_range_comes_from_the_rows(cars: pd.DataFrame) -> None:
    catalog = build_catalog(cars, vehicle_type="car")

    assert catalog.model_year.min == float(cars["model_year"].min())
    assert catalog.model_year.max == float(cars["model_year"].max())


def test_an_all_null_displacement_is_null_rather_than_zero(cars: pd.DataFrame) -> None:
    # Reporting 0-0 would make a form offer an impossible range; None says "not recorded".
    cars = cars.assign(engine_cc=None)

    assert build_catalog(cars, vehicle_type="car").engine_cc is None


def test_a_frame_that_is_not_gold_shaped_is_refused() -> None:
    with pytest.raises(CatalogError, match="brand"):
        build_catalog(pd.DataFrame({"price_cop": [1]}), vehicle_type="car")


def test_a_frame_without_model_years_is_refused(cars: pd.DataFrame) -> None:
    with pytest.raises(CatalogError, match="no model years"):
        build_catalog(cars.assign(model_year=None), vehicle_type="car")


def test_the_round_trip_is_exact(cars: pd.DataFrame, tmp_path: Path) -> None:
    catalog = build_catalog(cars, vehicle_type="car")
    save_catalog(tmp_path, catalog)

    assert load_catalog(tmp_path) == catalog


def test_a_bundle_without_a_catalogue_loads_as_none(tmp_path: Path) -> None:
    # An older bundle still serves predictions; only /catalog is unavailable.
    assert load_catalog(tmp_path) is None


def test_an_unknown_catalogue_format_is_loud(tmp_path: Path) -> None:
    (tmp_path / CATALOG_NAME).write_text(json.dumps({"format": 99}), encoding="utf-8")

    with pytest.raises(CatalogError, match="format"):
        load_catalog(tmp_path)


def test_the_shipped_catalogues_match_the_shipped_models() -> None:
    # Against the real artifacts, not a fixture: these two files are what the image serves,
    # and a catalogue regenerated from a different lake than the boosters would be a
    # mismatch no synthetic test can see.
    root = Path(__file__).resolve().parents[2] / "artifacts" / "models"
    for vehicle_type in ("car", "motorcycle"):
        directory = root / vehicle_type
        if not (directory / CATALOG_NAME).exists():
            pytest.skip(f"no {vehicle_type} bundle in this checkout")

        catalog = load_catalog(directory)
        manifest = json.loads((directory / "model.json").read_text(encoding="utf-8"))
        assert catalog is not None
        assert catalog.vehicle_type == vehicle_type
        assert catalog.n_rows == manifest["lake"]["n_train"]
        assert {brand.name for brand in catalog.brands} <= set(manifest["levels"]["brand"])
        assert {m.name for brand in catalog.brands for m in brand.models} <= set(
            manifest["levels"]["model"]
        )
        assert {entry.name for entry in catalog.departments} <= set(
            manifest["levels"]["department"]
        )
