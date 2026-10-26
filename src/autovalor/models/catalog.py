"""What the served model knows how to be asked about.

``/predict`` accepts a brand, a model token, a department and a year, and the trees were
fitted with those as **frozen categorical levels**: a make the model never saw lands outside
its categories and goes down the missing branch, which produces a confident-looking estimate
built on nothing. A free-text form is therefore the wrong input surface, and the frontend
needs the real lists — not a hand-written one that drifts the first time the lake grows.

So the lists are derived from the rows the served model was fitted on, at export time, and
travel inside the bundle. That is the property worth protecting: the catalogue cannot
describe a different population than the model, because it is built from the same frame in
the same run.

Counts ride along with every entry. The frontend decides what to do with them — order by
popularity, or hide a model token with two listings behind "show all" — and that decision
does not belong in the API. Nothing is filtered out here: a rare level is still a level the
model knows, and dropping it would make a legitimate vehicle unaskable.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from autovalor.features.naming import display_model
from autovalor.models.dataset import VehicleType

logger = logging.getLogger("autovalor.models")

CATALOG_NAME = "catalog.json"
"""File written next to the manifest, one per vertical."""

CATALOG_FORMAT = 2
"""What :func:`build_catalog` writes. Read separately from the bundle format: a bundle
exported before catalogues existed is still a loadable bundle, it just cannot answer
``/catalog``, and that is better than refusing to serve predictions over a missing list."""

READABLE_FORMATS = frozenset({1, 2})
"""What :func:`load_catalog` accepts. Format 2 added a display name per level; a format-1
file is read with each level displaying as itself, which is what it meant. The service and
the bundle it serves are deployed separately, so a build that refused the previous format
would turn an ordinary deploy order into an outage."""

BRAND_COLUMN = "brand"
MODEL_COLUMN = "model"
DEPARTMENT_COLUMN = "department"
YEAR_COLUMN = "model_year"
ENGINE_COLUMN = "engine_cc"


class CatalogError(RuntimeError):
    """Raised when a catalogue file is unreadable or of an unknown format."""


@dataclass(frozen=True)
class NamedCount:
    """One categorical level, how it is spelled for a reader, and how many listings it has.

    ``name`` is the level the model was fitted on and the string ``/predict`` expects.
    ``display_name`` is the same level spelled for a person. They differ for model tokens,
    which are mined out of titles in lower case, and are equal for makes and departments,
    which already carry their own capitalisation. Resolving it here rather than in the
    frontend keeps one spelling of a model across the dropdown, the explanation card and
    anything else that reads the catalogue.
    """

    name: str
    listings: int
    display_name: str

    def to_json(self) -> dict[str, Any]:
        """Return the JSON form."""
        return {
            "name": self.name,
            "listings": self.listings,
            "display_name": self.display_name,
        }


@dataclass(frozen=True)
class BrandEntry:
    """One make, with the model tokens seen under it.

    The nesting is what the form needs: picking a make should narrow the model list, and a
    flat list of 507 tokens shared across 47 makes cannot do that.
    """

    name: str
    listings: int
    models: tuple[NamedCount, ...]
    display_name: str

    def to_json(self) -> dict[str, Any]:
        """Return the JSON form."""
        return {
            "name": self.name,
            "listings": self.listings,
            "display_name": self.display_name,
            "models": [model.to_json() for model in self.models],
        }


@dataclass(frozen=True)
class NumericRange:
    """The closed range of a numeric input, as the training rows observed it."""

    min: float
    max: float

    def to_json(self) -> dict[str, Any]:
        """Return the JSON form."""
        return {"min": self.min, "max": self.max}


@dataclass(frozen=True)
class VehicleCatalog:
    """Everything a form needs to build a valid request for one vertical.

    Attributes:
        vehicle_type: Vertical the lists belong to.
        n_rows: Training rows they were derived from.
        brands: Makes, each carrying its own model tokens.
        departments: Departments the model has levels for.
        model_year: Range of model years in the training rows.
        engine_cc: Range of displacements, or ``None`` when the vertical records none.
    """

    vehicle_type: VehicleType
    n_rows: int
    brands: tuple[BrandEntry, ...]
    departments: tuple[NamedCount, ...]
    model_year: NumericRange
    engine_cc: NumericRange | None

    def to_json(self) -> dict[str, Any]:
        """Return the JSON form written into the bundle."""
        return {
            "format": CATALOG_FORMAT,
            "vehicle_type": self.vehicle_type,
            "n_rows": self.n_rows,
            "brands": [brand.to_json() for brand in self.brands],
            "departments": [department.to_json() for department in self.departments],
            "model_year": self.model_year.to_json(),
            "engine_cc": None if self.engine_cc is None else self.engine_cc.to_json(),
        }


def _counts(
    frame: pd.DataFrame, column: str, *, display: Callable[[str], str] = lambda name: name
) -> tuple[NamedCount, ...]:
    """Count the levels of one column, alphabetically.

    Alphabetical rather than by frequency because these land in a ``<select>``, where a
    user scans for a name. The count travels with each entry, so a client that wants
    popularity order has what it needs.
    """
    counts = frame[column].dropna().astype(str).value_counts()
    return tuple(
        NamedCount(name=name, listings=int(counts[name]), display_name=display(name))
        for name in sorted(counts.index)
    )


def _named_count(payload: dict[str, Any]) -> NamedCount:
    """Read one level back, defaulting its display name to the level itself.

    The default is what lets this build read a format-1 catalogue's shape without a
    special case: a level with no stored display name is one that needs none.
    """
    return NamedCount(
        name=payload["name"],
        listings=int(payload["listings"]),
        display_name=payload.get("display_name", payload["name"]),
    )


def _range(frame: pd.DataFrame, column: str) -> NumericRange | None:
    """Return the observed range of a numeric column, or ``None`` when it is all null."""
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    return NumericRange(min=float(values.min()), max=float(values.max()))


def build_catalog(frame: pd.DataFrame, *, vehicle_type: VehicleType) -> VehicleCatalog:
    """Derive the catalogue from the rows a model was fitted on.

    Args:
        frame: Gold-shaped training rows for a single vertical — the same frame the point
            model saw, which is what makes the lists and the model's categories agree.
        vehicle_type: Vertical being described.

    Returns:
        The catalogue, ready to be written into the bundle.

    Raises:
        CatalogError: If the frame is missing a column the catalogue is built from, or
            holds no model years at all. Both mean the frame is not gold-shaped, and a
            catalogue silently missing a list would be worse than a failed export.
    """
    required = (BRAND_COLUMN, MODEL_COLUMN, DEPARTMENT_COLUMN, YEAR_COLUMN)
    missing = [column for column in required if column not in frame.columns]
    if missing:
        msg = f"cannot build a {vehicle_type} catalogue, the frame has no {', '.join(missing)}"
        raise CatalogError(msg)

    known_brand = frame.dropna(subset=[BRAND_COLUMN])
    brands = [
        BrandEntry(
            name=str(name),
            listings=len(group),
            models=_counts(group, MODEL_COLUMN, display=display_model),
            display_name=str(name),
        )
        for name, group in known_brand.groupby(
            known_brand[BRAND_COLUMN].astype(str), sort=True, observed=True
        )
    ]

    years = _range(frame, YEAR_COLUMN)
    if years is None:
        msg = f"the {vehicle_type} frame holds no model years"
        raise CatalogError(msg)

    catalog = VehicleCatalog(
        vehicle_type=vehicle_type,
        n_rows=len(frame),
        brands=tuple(brands),
        departments=_counts(frame, DEPARTMENT_COLUMN),
        model_year=NumericRange(min=float(int(years.min)), max=float(int(years.max))),
        engine_cc=_range(frame, ENGINE_COLUMN) if ENGINE_COLUMN in frame.columns else None,
    )
    logger.info(
        "%s catalogue — %d makes, %d model tokens, %d departments over %d rows",
        vehicle_type,
        len(catalog.brands),
        sum(len(brand.models) for brand in catalog.brands),
        len(catalog.departments),
        catalog.n_rows,
    )
    return catalog


def save_catalog(directory: Path, catalog: VehicleCatalog) -> Path:
    """Write a catalogue next to a bundle's manifest.

    Args:
        directory: The vertical's bundle directory, created if missing.
        catalog: What to write.

    Returns:
        The path written.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / CATALOG_NAME
    path.write_text(
        json.dumps(catalog.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def load_catalog(directory: Path) -> VehicleCatalog | None:
    """Read a bundle's catalogue.

    Args:
        directory: The vertical's bundle directory.

    Returns:
        The catalogue, or ``None`` when the bundle does not carry one — a bundle exported
        before this existed still serves predictions, and ``/catalog`` says it has no lists
        rather than the service refusing to start.

    Raises:
        CatalogError: If the file exists but is of an unknown format. A present-but-stale
            catalogue is a real mismatch between the lists and the model, so it is loud.
    """
    path = directory / CATALOG_NAME
    if not path.exists():
        logger.warning("no catalogue at %s; /catalog will have nothing to list", path)
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") not in READABLE_FORMATS:
        msg = f"{path} is catalogue format {payload.get('format')!r}, this build reads "
        raise CatalogError(msg + ", ".join(str(known) for known in sorted(READABLE_FORMATS)))

    engine = payload.get("engine_cc")
    return VehicleCatalog(
        vehicle_type=payload["vehicle_type"],
        n_rows=int(payload["n_rows"]),
        brands=tuple(
            BrandEntry(
                name=brand["name"],
                listings=int(brand["listings"]),
                models=tuple(_named_count(model) for model in brand["models"]),
                display_name=brand.get("display_name", brand["name"]),
            )
            for brand in payload["brands"]
        ),
        departments=tuple(_named_count(entry) for entry in payload["departments"]),
        model_year=NumericRange(
            min=float(payload["model_year"]["min"]), max=float(payload["model_year"]["max"])
        ),
        engine_cc=None
        if engine is None
        else NumericRange(min=float(engine["min"]), max=float(engine["max"])),
    )
