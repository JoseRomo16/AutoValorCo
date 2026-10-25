"""What the cleaned catalogue must look like on the real lake.

The seed contract tests check the maps against each other. These check the *result*: that
the rules, applied to 11.680 real titles, leave a catalogue a form can show. Several of
these invariants cannot be stated on synthetic rows — "no model token in the lake is a
make" is a claim about the lake.

Skipped when ``data/autovalor.duckdb`` is absent, which is every CI run: ``data/`` is not
committed ([ADR 0004](docs/adr/0004-capture-history-storage.md)), so the lake exists only
where it has been rebuilt with ``make transform``. The patterns these guard are also
covered on synthetic rows by the ``title_features_resolves_the_make`` dbt unit test, which
does run in CI; this module is the measurement on top.
"""

import csv
import re
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[2]
LAKE = ROOT / "data" / "autovalor.duckdb"
SEEDS = ROOT / "dbt" / "seeds"

pytestmark = pytest.mark.skipif(
    not LAKE.exists(), reason="no local lake; run `make transform` to build one"
)

GOLD = "main_gold.gold_listings"


def _read(name: str) -> list[dict[str, str]]:
    with (SEEDS / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _scalar(con: duckdb.DuckDBPyConnection, sql: str) -> float:
    """The one number an aggregate query returns.

    ``fetchone`` is typed as optional because a plain select can come back empty; an
    aggregate without a group by never does.
    """
    row = con.execute(sql).fetchone()
    assert row is not None, sql
    return row[0]  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def con() -> Iterator[duckdb.DuckDBPyConnection]:
    connection = duckdb.connect(str(LAKE), read_only=True)
    yield connection
    connection.close()


def test_no_model_token_is_a_make(con: duckdb.DuckDBPyConnection) -> None:
    # The make resolves a listing; it is never also the answer to "which model". Before
    # the token scan, every one of the 77 Citroëns had "citroën" as its model, because the
    # removal matched the canonical name and the title spelled it with a diaeresis.
    brands = _read("vehicle_brands.csv")
    for vertical in ("car", "motorcycle"):
        makes = [
            row["alias"]
            for row in brands
            if row["alias_kind"] == "brand"
            and row["applies_to"] in ("both", vertical)
            and " " not in row["alias"]
        ]
        placeholders = ", ".join("?" for _ in makes)
        offenders = con.execute(
            f"select distinct model from {GOLD} "
            f"where vehicle_type = ? and model in ({placeholders})",
            [vertical, *makes],
        ).fetchall()
        assert offenders == [], f"{vertical}: {offenders}"


def test_no_model_token_is_half_of_a_make(con: duckdb.DuckDBPyConnection) -> None:
    # A make written across two words has to be removed as a whole. Removing the shorter
    # alias first eats the delimiter the longer one needed, which left "benz" as the model
    # of all 481 Mercedes-Benz listings and "am" on 40 Can-Ams. The fix is an ordering, so
    # this is the test that notices if the ordering goes away.
    brands = _read("vehicle_brands.csv")
    halves = {
        word
        for row in brands
        if row["alias_kind"] == "brand" and " " in row["alias"]
        for word in row["alias"].split(" ")
    }
    halves |= {
        word
        for row in brands
        if row["alias_kind"] == "brand" and "-" in row["alias"]
        for word in row["alias"].split("-")
    }
    placeholders = ", ".join("?" for _ in halves)
    offenders = con.execute(
        f"select distinct vehicle_type, model from {GOLD} where model in ({placeholders})",
        list(halves),
    ).fetchall()
    assert offenders == []


def test_no_model_token_is_punctuation_or_blank(con: duckdb.DuckDBPyConnection) -> None:
    # "-", ",", "$" and "/" were all levels of their own, which is what a dropdown built
    # straight off the lake showed the user.
    offenders = con.execute(
        f"select distinct vehicle_type, model from {GOLD} "
        r"where model is not null and not regexp_matches(model, '[a-z0-9]')"
    ).fetchall()
    assert offenders == []


def test_no_model_token_carries_loose_punctuation(con: duckdb.DuckDBPyConnection) -> None:
    # "f800gs,", "r15/", "mt15-", "**características:**" were separate levels from the
    # same tokens written cleanly.
    offenders = con.execute(
        f"select distinct vehicle_type, model from {GOLD} "
        r"where model is not null and regexp_matches(model, '^[.-]|[.-]$|[^a-z0-9áéíóúüñ. -]')"
    ).fetchall()
    assert offenders == []


def test_a_car_model_is_never_a_displacement(con: duckdb.DuckDBPyConnection) -> None:
    # Cars advertise litres, so "1.6" is engine size and not a model. Motorcycles are the
    # opposite case and are deliberately not checked here: KTM sells a 390.
    offenders = con.execute(
        f"select distinct model from {GOLD} "
        r"where vehicle_type = 'car' and regexp_matches(coalesce(model, ''), '^[0-9][.,][0-9]$')"
    ).fetchall()
    assert offenders == []


def test_a_motorcycle_model_is_never_a_year(con: duckdb.DuckDBPyConnection) -> None:
    offenders = con.execute(
        f"select distinct model from {GOLD} where vehicle_type = 'motorcycle' "
        r"and regexp_matches(coalesce(model, ''), '^(19|20)[0-9]{2}$')"
    ).fetchall()
    assert offenders == []


def test_a_motorcycle_model_number_survives(con: duckdb.DuckDBPyConnection) -> None:
    # The mirror of the two rules above, and the reason they are scoped by vertical: a
    # bare number is a real motorcycle model, so a rule that dropped numbers outright
    # would delete KTM's and BMW's catalogues.
    kept = dict(
        con.execute(
            f"select brand, model from {GOLD} "
            "where vehicle_type = 'motorcycle' and brand in ('KTM', 'BMW') "
            "and model in ('390', '1200', '1290')"
        ).fetchall()
    )
    assert "390" in kept.values() or "1290" in kept.values()


def test_a_make_alias_never_loses_to_a_model_alias(con: duckdb.DuckDBPyConnection) -> None:
    # This is what makes the model-name aliases strictly additive: they can only fire on a
    # title that names no make at all, so adding one cannot move a listing that already
    # resolved. Without the rank, "Vendo Suzuki Agility 125" becomes a Kymco.
    brands = _read("vehicle_brands.csv")
    makes_by_alias = {
        row["alias"]: row["brand"]
        for row in brands
        if row["alias_kind"] == "brand" and row["applies_to"] in ("both", "motorcycle")
    }
    model_aliases = {
        row["alias"]: row["brand"]
        for row in brands
        if row["alias_kind"] == "model" and row["applies_to"] in ("both", "motorcycle")
    }
    rows = con.execute(
        f"select lower(title), brand from {GOLD} where vehicle_type = 'motorcycle'"
    ).fetchall()

    offenders = []
    for title, resolved in rows:
        named = {make for alias, make in makes_by_alias.items() if _word_in(alias, title)}
        if named and resolved not in named:
            # Resolved to something no make alias in the title names, which can only have
            # come from a model alias overriding a make.
            through_model = any(
                make == resolved for alias, make in model_aliases.items() if _word_in(alias, title)
            )
            if through_model:
                offenders.append((title, resolved))
    assert offenders == []


def test_a_manufacturer_beats_a_distributor(con: duckdb.DuckDBPyConnection) -> None:
    # The deliberate exception to additivity, and the only one: AKT, Victory and Auteco
    # list other makes' bikes under their own name. Every listing whose title names both
    # has to resolve to the one that built the vehicle.
    offenders = con.execute(
        f"""
        select title, brand from {GOLD}
        where vehicle_type = 'motorcycle'
          and regexp_matches(lower(title), '(^|[^a-z])(akt|auteco|victory)([^a-z]|$)')
          and regexp_matches(
              lower(title), '(^|[^a-z])(voge|sym|zontes|kymco|bajaj|ceronte)([^a-z]|$)'
          )
          and brand in ('AKT', 'Victory')
        """
    ).fetchall()
    assert offenders == []


def test_the_distributor_keeps_its_own_listings(con: duckdb.DuckDBPyConnection) -> None:
    # The other half of the rule: ranking a distributor below manufacturers must not cost
    # it the listings that name no other make.
    kept = _scalar(
        con, f"select count(*) from {GOLD} where vehicle_type = 'motorcycle' and brand = 'AKT'"
    )
    assert kept > 100


def test_auteco_is_not_a_make(con: duckdb.DuckDBPyConnection) -> None:
    # It is Colombia's largest distributor, not a manufacturer, and it used to publish a
    # nine-model catalogue made of other makes' bikes.
    assert _scalar(con, f"select count(*) from {GOLD} where brand = 'Auteco'") == 0


def test_no_bicycle_reaches_gold(con: duckdb.DuckDBPyConnection) -> None:
    offenders = con.execute(
        f"select title from {GOLD} where vehicle_type = 'motorcycle' "
        r"and regexp_matches(lower(title), 'bicicletas?|bicimoto|patineta|monopat')"
    ).fetchall()
    assert offenders == []


def test_every_department_is_written_the_canonical_way(con: duckdb.DuckDBPyConnection) -> None:
    canonical = {row["department"] for row in _read("colombian_departments.csv")}
    found = {
        name
        for (name,) in con.execute(f"select distinct department from {GOLD}").fetchall()
        if name
    }
    assert found - canonical == set()


def test_the_unknown_bucket_shrank_to_where_the_title_says_nothing(
    con: duckdb.DuckDBPyConnection,
) -> None:
    # Cars resolve from the make alone; the floor is listings whose title names a make
    # nobody sells here. This pins the gain rather than the mechanism: if a seed edit
    # takes the car bucket back above 1 %, something was removed rather than added.
    unresolved = _scalar(
        con,
        f"""
        select round(100.0 * sum(case when brand = 'Desconocida' then 1 else 0 end) / count(*), 2)
        from {GOLD} where vehicle_type = 'car'
        """,
    )
    assert unresolved < 1.0


def _word_in(alias: str, title: str) -> bool:
    """Whether an alias appears in a title on letter boundaries, as the SQL match does."""
    return re.search(r"(^|[^a-z])" + re.escape(alias) + r"([^a-z]|$)", title) is not None
