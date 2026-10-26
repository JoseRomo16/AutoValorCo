"""How a mined token is spelled when a person reads it.

The lake stores the model as the token the title carried, lower-cased: ``cx-30``,
``mt-09``, ``clase gle``. That is the right key — it is what the trees' frozen categories
are keyed on and what ``/predict`` accepts — and the wrong label. A dropdown that offers
"cx-30" and "clase gle" looks like a debug view of somebody's database.

So the display name is derived, not stored twice. A rule covers the overwhelming majority
(an acronym goes up, a word gets a capital, a dashed name is handled segment by segment),
and :data:`DISPLAY_OVERRIDES` carries the names a rule cannot reach, because no rule
derives "bZ4X" from ``bz4x``.

Stdlib only, on purpose: ``api/labels.py`` imports this so the explanation card and the
dropdown spell a model the same way, and the API image installs no data stack.
"""

import re
import unicodedata

DISPLAY_OVERRIDES: dict[str, str] = {
    # Names whose own maker writes them against the rule.
    "4runner": "4Runner",
    "bz3x": "bZ3X",
    "bz4": "bZ4",
    "bz4x": "bZ4X",
    "bz5": "bZ5",
    "e-tron": "e-tron",
    "i10": "i10",
    "id4": "ID.4",
    "ix": "iX",
    "ix1": "iX1",
    "ix2": "iX2",
    "ix3": "iX3",
    "rninet": "R nineT",
    # Two-letter second words the short-token rule would shout.
    "santa fe": "Santa Fe",
    # Written with a dash everywhere except in the token the titles agree on.
    "nmax": "N-Max",
    "xmax": "X-Max",
}
"""Tokens whose display name the rule below cannot derive. Small by design: every entry
is a maker's own spelling, not a preference."""

WORDS_NOT_ACRONYMS = frozenset(
    {
        "ami",
        "bet",
        "box",
        "dio",
        "eco",
        "evo",
        "fat",
        "fit",
        "fly",
        "fox",
        "gol",
        "jet",
        "jog",
        "joy",
        "max",
        "neo",
        "niu",
        "one",
        "pro",
        "qin",
        "rev",
        "rio",
        "sei",
        "uno",
        "van",
        "way",
        "zoe",
    }
)
"""Short tokens that are words rather than initials.

Nothing distinguishes "Rio" from "RZR" by shape: both are three letters a maker chose. So
the short-token rule shouts by default — most short model tokens in the lake are initials
("GS", "CB", "XTZ", "TRK") — and the words are listed. Measured against the lake, not
guessed: every entry here is a token some listing actually carries."""

_DIGITS_THEN_LETTER = re.compile(r"^[0-9]+[a-z]$")
_HAS_DIGIT = re.compile(r"[0-9]")
_SHORT = 3
"""Up to three letters reads as an acronym ("GS", "CB", "XTZ"); four or more reads as a
word ("Duke", "Crox"). Measured against the tokens the lake actually holds."""


def slug(text: str) -> str:
    """Return the accent-free, lower-case, alphanumeric-only key of a name.

    Mirrors the slug ``stg_tucarro_listings`` computes in SQL, so the department a request
    carries can be matched against the level the model was fitted on however the caller
    spelled it. ``tests/features/test_naming.py`` pins the two implementations together
    against the seed.

    Args:
        text: Name as published or as a caller typed it.

    Returns:
        The key. Empty when the name carries no alphanumeric character.
    """
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", folded.lower())


def _segment(segment: str) -> str:
    """Spell one dash-separated piece of a token."""
    if not segment:
        return segment
    # "330e" and "420i" are trim letters their makers write lower case; upper-casing them
    # produces a name no Mercedes-Benz or BMW catalogue uses.
    if _DIGITS_THEN_LETTER.match(segment):
        return segment
    if _HAS_DIGIT.search(segment):
        return segment.upper()
    if len(segment) <= _SHORT and segment not in WORDS_NOT_ACRONYMS:
        return segment.upper()
    return segment[0].upper() + segment[1:]


def spell_model(token: str) -> str:
    """Return what the rule alone makes of a token, before any override.

    Separate from :func:`display_model` so a test can assert that every entry in
    :data:`DISPLAY_OVERRIDES` is a name the rule cannot reach. An override the rule
    already produces reads as a decision and is not one.

    Args:
        token: Canonical lower-case token.

    Returns:
        The spelled name.
    """
    return " ".join(
        "-".join(_segment(segment) for segment in word.split("-")) for word in token.split(" ")
    )


def display_model(token: str) -> str:
    """Return the model token as a person should read it.

    Args:
        token: Canonical lower-case token from the lake ("cx-30", "clase gle", "gs").

    Returns:
        The display name. A token that is already mixed case is returned untouched, so a
        name that arrived spelled correctly is never re-derived.
    """
    if not token or not token.islower():
        return token
    return DISPLAY_OVERRIDES.get(token) or spell_model(token)
