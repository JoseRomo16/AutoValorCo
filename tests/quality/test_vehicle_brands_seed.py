"""Contract tests for the make-alias seed.

The seed is data, not code, and it is the one place where a careless edit silently changes
what every listing resolves to. dbt checks the column-level constraints (unique, not null,
accepted values); what it cannot check is the invariants *between* rows, which is what
decides whether a new alias is safe.
"""

import csv
from pathlib import Path

import pytest

SEED = Path(__file__).resolve().parents[2] / "dbt" / "seeds" / "vehicle_brands.csv"

MIN_ALIAS_LENGTH = 2
"""Shortest alias allowed. A single letter matches far too much, even on word boundaries."""


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    with SEED.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_the_seed_has_the_columns_the_model_reads(rows: list[dict[str, str]]) -> None:
    assert rows
    assert set(rows[0]) == {"alias", "brand", "applies_to", "alias_kind"}


def test_every_alias_is_lowercase_and_trimmed(rows: list[dict[str, str]]) -> None:
    # The match lowercases the title but not the alias, so an uppercase alias would never
    # fire and would do so silently.
    offenders = [row["alias"] for row in rows if row["alias"] != row["alias"].strip().lower()]
    assert offenders == []


def test_no_alias_is_too_short(rows: list[dict[str, str]]) -> None:
    offenders = [row["alias"] for row in rows if len(row["alias"]) < MIN_ALIAS_LENGTH]
    assert offenders == []


def test_aliases_are_unique(rows: list[dict[str, str]]) -> None:
    # Also enforced by dbt, but a duplicate here makes the ranking non-deterministic rather
    # than merely redundant, so it is worth failing fast in the unit suite too.
    aliases = [row["alias"] for row in rows]
    duplicates = {alias for alias in aliases if aliases.count(alias) > 1}
    assert duplicates == set()


def test_every_model_alias_points_at_a_make_the_seed_knows(rows: list[dict[str, str]]) -> None:
    # A model alias whose make has no brand alias of its own would introduce a make that
    # can only ever be reached through that one model -- almost always a typo in the
    # canonical name ("Royal Enfield" against "Royal enfield").
    makes = {row["brand"] for row in rows if row["alias_kind"] == "brand"}
    orphans = {
        (row["alias"], row["brand"])
        for row in rows
        if row["alias_kind"] == "model" and row["brand"] not in makes
    }
    assert orphans == set()


def test_no_model_alias_is_also_a_make(rows: list[dict[str, str]]) -> None:
    # "honda" as both a brand alias and somebody's model alias would make the ranking
    # depend on which row the join happened to see first.
    makes = {row["alias"] for row in rows if row["alias_kind"] == "brand"}
    models = {row["alias"] for row in rows if row["alias_kind"] == "model"}
    assert makes & models == set()


def test_model_aliases_are_motorcycle_only(rows: list[dict[str, str]]) -> None:
    # The unresolved-make problem is a motorcycle one: cars resolve 99,2 % of the time from
    # the make alone. Letting a model alias loose on the car vertical would add risk with
    # nothing to gain.
    leaked = [
        row["alias"]
        for row in rows
        if row["alias_kind"] == "model" and row["applies_to"] != "motorcycle"
    ]
    assert leaked == []


def test_no_alias_contains_a_comma_or_quote(rows: list[dict[str, str]]) -> None:
    # The seed is read by DuckDB's CSV sniffer, which refuses the whole file when the
    # dialect becomes ambiguous — a failure that surfaces far from its cause.
    offenders = [row["alias"] for row in rows if {",", '"'} & set(row["alias"])]
    assert offenders == []
