"""How a mined token is spelled, and that the slug matches the one dbt computes."""

import csv
from pathlib import Path

import pytest

from autovalor.features.naming import DISPLAY_OVERRIDES, display_model, slug, spell_model

SEEDS = Path(__file__).resolve().parents[2] / "dbt" / "seeds"
DEPARTMENTS_SEED = SEEDS / "colombian_departments.csv"


@pytest.mark.parametrize(
    ("token", "shown"),
    [
        # Acronyms go up; words get a capital. Three letters is the cut-off.
        ("gs", "GS"),
        ("xtz", "XTZ"),
        ("duke", "Duke"),
        ("gixxer", "Gixxer"),
        ("multistrada", "Multistrada"),
        # Dashes are handled segment by segment, which is the only way "CR-V" and
        # "CX-30" come out of one rule.
        ("cx-30", "CX-30"),
        ("cr-v", "CR-V"),
        ("s-cross", "S-Cross"),
        ("v-strom", "V-Strom"),
        ("mt-09", "MT-09"),
        ("f-150", "F-150"),
        # A digit anywhere makes the segment an acronym.
        ("r15", "R15"),
        ("f850gs", "F850GS"),
        ("q5", "Q5"),
        # Digits followed by one letter are a trim their maker writes lower case.
        ("330e", "330e"),
        ("420i", "420i"),
        # Family word plus the token after it, which is what the join rule produces.
        ("clase gle", "Clase GLE"),
        ("clase c", "Clase C"),
        ("serie 3", "Serie 3"),
        ("land cruiser", "Land Cruiser"),
        ("model 3", "Model 3"),
        ("africa twin", "Africa Twin"),
        # Short tokens that are words, not initials.
        ("rio", "Rio"),
        ("joy", "Joy"),
        ("dio", "Dio"),
        ("gol", "Gol"),
        # ... next to the short tokens that are.
        ("rzr", "RZR"),
        ("trk", "TRK"),
        # Overrides.
        ("nmax", "N-Max"),
        ("santa fe", "Santa Fe"),
        ("4runner", "4Runner"),
        ("x-adv", "X-ADV"),
    ],
)
def test_the_display_name_reads_like_the_maker_writes_it(token: str, shown: str) -> None:
    assert display_model(token) == shown


def test_an_empty_or_already_spelled_token_is_left_alone() -> None:
    assert display_model("") == ""
    # Nothing in gold arrives mixed case, but re-deriving a name that is already right is
    # how a correct spelling gets broken.
    assert display_model("bZ4X") == "bZ4X"


def test_every_override_is_needed() -> None:
    # An override the rule already produces is a line that looks like a decision and is
    # not one, and it rots silently when the rule changes.
    redundant = {token for token, shown in DISPLAY_OVERRIDES.items() if spell_model(token) == shown}
    assert redundant == set()


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Valle Del Cauca", "valledelcauca"),
        ("Valle del Cauca", "valledelcauca"),
        ("VALLE DEL CAUCA", "valledelcauca"),
        ("Bogotá D.C.", "bogotadc"),
        ("Quindio", "quindio"),
        ("Quindío", "quindio"),
        ("Norte De Santander", "nortedesantander"),
        ("Nariño", "narino"),
        ("", ""),
    ],
)
def test_the_slug_folds_case_accents_and_punctuation(name: str, key: str) -> None:
    assert slug(name) == key


def test_the_seed_keys_are_the_slugs_of_their_own_names() -> None:
    # The seed is keyed on the slug and dbt computes that key in SQL. If the Python slug
    # ever diverges, the API would normalise a department to a level the lake does not
    # carry -- which the trees would answer with their missing branch, silently.
    with DEPARTMENTS_SEED.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows
    keys = {row["slug"] for row in rows}
    # Every canonical name has to slug back to a key the seed carries, or a lake rebuilt
    # from its own output would stop resolving. Extra keys are fine and deliberate: a
    # department the site writes two ways gets one row per spelling.
    unreachable = sorted(row["department"] for row in rows if slug(row["department"]) not in keys)
    assert unreachable == []
