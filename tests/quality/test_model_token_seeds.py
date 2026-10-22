"""Contract tests for the seeds that decide what the model token is.

Same reason as :mod:`tests.quality.test_vehicle_brands_seed`: these are data, and dbt can
check a column but not the invariants between rows and between seeds. The ones that matter
here are cross-seed — a stopword that is also somebody's model, an alias pointing at a make
nobody knows — because those fail silently, by quietly deleting a level.
"""

import csv
from pathlib import Path

import pytest

SEEDS = Path(__file__).resolve().parents[2] / "dbt" / "seeds"
VERTICALS = {"car", "motorcycle", "both"}


def _read(name: str) -> list[dict[str, str]]:
    with (SEEDS / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def tokens() -> list[dict[str, str]]:
    return _read("model_tokens.csv")


@pytest.fixture(scope="module")
def aliases() -> list[dict[str, str]]:
    return _read("model_aliases.csv")


@pytest.fixture(scope="module")
def brands() -> list[dict[str, str]]:
    return _read("vehicle_brands.csv")


def test_the_token_seed_has_the_columns_the_scan_reads(tokens: list[dict[str, str]]) -> None:
    assert tokens
    assert set(tokens[0]) == {"token", "applies_to", "rule", "reason"}


def test_the_alias_seed_has_the_columns_the_join_reads(aliases: list[dict[str, str]]) -> None:
    assert aliases
    assert set(aliases[0]) == {"alias", "model", "brand", "applies_to"}


def test_every_token_is_lowercase_and_trimmed(tokens: list[dict[str, str]]) -> None:
    # The scan lower-cases the title but not the seed, so an upper-case token would never
    # match and would do so without complaining.
    offenders = [row["token"] for row in tokens if row["token"] != row["token"].strip().lower()]
    assert offenders == []


def test_every_alias_is_lowercase_and_trimmed(aliases: list[dict[str, str]]) -> None:
    offenders = [row["alias"] for row in aliases if row["alias"] != row["alias"].strip().lower()]
    offenders += [row["model"] for row in aliases if row["model"] != row["model"].strip().lower()]
    assert offenders == []


def test_the_rule_and_scope_columns_hold_known_values(tokens: list[dict[str, str]]) -> None:
    assert {row["rule"] for row in tokens} <= {"drop", "join"}
    assert {row["applies_to"] for row in tokens} <= VERTICALS


def test_an_alias_is_scoped_to_one_vertical(aliases: list[dict[str, str]]) -> None:
    # Unlike a stopword, an alias renames a level, and the same token means different
    # vehicles in the two verticals. "both" would be a rename nobody checked twice.
    assert {row["applies_to"] for row in aliases} <= {"car", "motorcycle"}


def test_no_token_is_listed_twice_for_one_vertical(tokens: list[dict[str, str]]) -> None:
    keys = [(row["token"], row["applies_to"], row["rule"]) for row in tokens]
    assert {key for key in keys if keys.count(key) > 1} == set()


def test_no_token_is_both_dropped_and_joined(tokens: list[dict[str, str]]) -> None:
    # Which one fired would depend on the order the lists happened to be built in.
    dropped = {row["token"] for row in tokens if row["rule"] == "drop"}
    joined = {row["token"] for row in tokens if row["rule"] == "join"}
    assert dropped & joined == set()


def test_no_alias_is_listed_twice_for_one_make(aliases: list[dict[str, str]]) -> None:
    keys = [(row["alias"], row["applies_to"], row["brand"]) for row in aliases]
    assert {key for key in keys if keys.count(key) > 1} == set()


def test_no_alias_maps_a_token_to_itself(aliases: list[dict[str, str]]) -> None:
    # A no-op row reads like a decision about a spelling and is not one.
    assert [row["alias"] for row in aliases if row["alias"] == row["model"]] == []


def test_an_alias_never_points_at_another_alias(aliases: list[dict[str, str]]) -> None:
    # The join runs once, so "a -> b" and "b -> c" would leave half the listings on b.
    sources = {(row["alias"], row["applies_to"]) for row in aliases}
    chained = {
        (row["alias"], row["model"])
        for row in aliases
        if (row["model"], row["applies_to"]) in sources
    }
    assert chained == set()


def test_every_alias_make_is_a_make_the_brand_seed_knows(
    aliases: list[dict[str, str]], brands: list[dict[str, str]]
) -> None:
    # A scope naming a make that does not exist is a rule that can never fire, and the
    # usual cause is a typo in the canonical name.
    known = {row["brand"] for row in brands}
    unknown = {row["brand"] for row in aliases if row["brand"] and row["brand"] not in known}
    assert unknown == set()


def test_no_stopword_is_also_a_make_alias(
    tokens: list[dict[str, str]], brands: list[dict[str, str]]
) -> None:
    # Make aliases are dropped as model tokens by the brand seed itself, so listing one
    # here as well would hide which seed is responsible. More to the point, a `join` token
    # that is also a make would consume the token after the make name.
    makes = {
        row["alias"] for row in brands if row["alias_kind"] == "brand" and " " not in row["alias"]
    }
    assert {row["token"] for row in tokens} & makes == set()


def test_no_stopword_is_a_model_alias_target(
    tokens: list[dict[str, str]], aliases: list[dict[str, str]]
) -> None:
    # The alias runs after the scan, so a canonical model that is also a dropped token
    # would be a level the alias can never reach.
    dropped = {row["token"] for row in tokens if row["rule"] == "drop"}
    assert {row["model"] for row in aliases} & dropped == set()


def test_no_seed_value_contains_a_comma_or_quote(
    tokens: list[dict[str, str]], aliases: list[dict[str, str]]
) -> None:
    # DuckDB's CSV sniffer refuses the whole file when the dialect turns ambiguous, and
    # it reports that far from the row that caused it.
    bad = {",", '"'}
    offenders = [row["token"] for row in tokens if bad & set(row["token"])]
    offenders += [row["alias"] for row in aliases if bad & set(row["alias"])]
    offenders += [row["model"] for row in aliases if bad & set(row["model"])]
    assert offenders == []
