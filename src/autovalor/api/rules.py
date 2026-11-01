"""One place where a request is checked against what the served model actually knows.

The audit of the deployed service found the same shape of bug five times: ``/catalog``
publishes the valid inputs, ``/predict`` validated against something else, and the gap came
back as a confident number instead of a rejection. A 1954 car answered 200 with 37,6 M, a
2028 one with 127,2 M, a car with a 50 cc engine moved the estimate by five million, an
asking price of 59 pesos came back labelled "Ganga · Pides 100 % menos", and ``"toyota"``
valued 20 % under ``"Toyota"`` because the make was matched case-sensitively.

So the rules live here and are read **from the catalogue the bundle carries**, not typed
into :mod:`autovalor.api.schemas` a second time. The schema keeps only the bounds that are
about the wire format — an integer that fits, a string that is not empty — and everything
that is about this model's training data is resolved here. Two sources of truth for the same
rule is how they came to disagree.

Three kinds of outcome, and which one a field gets is a product decision rather than a
technical one:

**Rejected (422).** The model cannot answer, and a number would be a guess dressed as an
estimate: a year or a displacement outside the training range, an asking price three orders
of magnitude below anything in the data, a make the trees have no category for.

**Accepted with a warning.** The model can answer, less well, and the caller deserves to
know. An unknown model token is dropped and valued as "make only", which is exactly what
omitting it would have done; an uncovered department is answered and flagged. These come
back in ``warnings`` as codes, so the frontend writes the sentence in the reader's language.

**Silently normalised.** Spelling. ``"toyota"``, ``"TOYOTA"`` and ``"Toyota"`` are one make,
``"Bogota D.C."`` is Bogotá. Nobody needs telling that their capitalisation was accepted.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import HTTPException, status

from autovalor.api.schemas import PredictRequest
from autovalor.features.naming import slug
from autovalor.models.catalog import NumericRange, VehicleCatalog

MODEL_NOT_COVERED = "model_not_covered"
"""The model token is not one this make was trained with; valued without it."""

DEPARTMENT_NOT_COVERED = "department_not_covered"
"""The department is not one the model was trained on."""

MAX_YEARS_AHEAD = 1
"""How far past the current year a model year may be, whatever the catalogue says.

Dealers list the coming model year, so next year is a real listing. The catalogue's own
maximum is capped by this because it is a property of the lake's newest capture, not a
promise about the future: a bundle trained in 2026 and served in 2029 would otherwise keep
accepting 2027 as "the newest year" long after that stopped being the point.
"""


def current_year() -> int:
    """The year a request is judged against. A function so tests can freeze it."""
    return datetime.now(UTC).year


@dataclass
class Resolved:
    """A request rewritten as the model knows it, plus what the caller should be told.

    ``request`` is safe to score: every categorical field is a level the trees carry, or
    explicitly absent. ``warnings`` is never an error — the estimate is real, it just came
    with less to go on than the caller supplied.
    """

    request: PredictRequest
    warnings: list[str] = field(default_factory=list)


def _reject(message: str) -> None:
    """Refuse the request with a 422 that says what the valid input is."""
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)


def _match(value: str, known: tuple[str, ...]) -> str | None:
    """Return the level ``value`` spells, ignoring case, accents and padding."""
    key = slug(value)
    for level in known:
        if slug(level) == key:
            return level
    return None


def year_range(catalog: VehicleCatalog, *, year: int | None = None) -> tuple[int, int]:
    """The model years this vertical accepts, as whole years.

    The catalogue's observed range, with the top capped at the current year plus
    :data:`MAX_YEARS_AHEAD`. Published through ``/catalog`` so the form and the service
    cannot disagree about it.
    """
    as_of = current_year() if year is None else year
    lowest = int(catalog.model_year.min)
    highest = min(int(catalog.model_year.max), as_of + MAX_YEARS_AHEAD)
    # A bundle older than the cap would otherwise invert the range and reject everything.
    return lowest, max(highest, lowest)


def resolve(
    request: PredictRequest, catalog: VehicleCatalog | None, *, year: int | None = None
) -> Resolved:
    """Check a request against one vertical's catalogue and return it as the model knows it.

    Args:
        request: The schema-validated request.
        catalog: The served bundle's catalogue, or ``None`` on a bundle exported before
            catalogues existed. With no catalogue nothing here can be checked, so the
            request passes through untouched — the alternative is refusing every request
            over a missing list, which would turn a stale bundle into an outage.
        year: Year to judge the model year against; defaults to the current one.

    Returns:
        The resolved request and any warnings the caller should see.

    Raises:
        HTTPException: 422 when the model cannot honestly answer. Each message names the
            valid input, because "invalid year" tells the caller nothing they can act on.
    """
    if catalog is None:
        return Resolved(request=request)

    changes: dict[str, object] = {}
    warnings: list[str] = []

    lowest, highest = year_range(catalog, year=year)
    if not lowest <= request.model_year <= highest:
        _reject(
            f"model_year {request.model_year} is outside the {request.vehicle_type} range "
            f"{lowest}-{highest}; outside it the model extrapolates rather than estimates"
        )

    if request.engine_cc is not None and catalog.engine_cc is not None:
        _check_engine(request, catalog.engine_cc)

    if request.asking_price_cop is not None and catalog.asking_price_cop is not None:
        _check_asking_price(request, catalog.asking_price_cop)

    brands = tuple(brand.name for brand in catalog.brands)
    brand = _match(request.brand, brands)
    if brand is None:
        _reject(
            f"brand {request.brand!r} is not one the {request.vehicle_type} model was "
            f"trained on; see /catalog for the {len(brands)} it knows"
        )
    elif brand != request.brand:
        changes["brand"] = brand

    # Resolved against the chosen make, not globally: a model token belongs to a make, and
    # "mazda 3" under Toyota is as unanswerable as a token that exists nowhere.
    if request.model is not None and request.model.strip() != "":
        tokens = next(
            (
                tuple(entry.name for entry in entry_brand.models)
                for entry_brand in catalog.brands
                if entry_brand.name == brand
            ),
            (),
        )
        token = _match(request.model, tokens)
        if token is None:
            # Dropped rather than rejected, because the field is optional: valuing without
            # it is a real answer and exactly what leaving it blank would have produced.
            # It used to be scored as-is, so "zzz" came back at 93,3 M — more than a
            # Corolla — with nothing to say the token meant nothing.
            changes["model"] = None
            warnings.append(MODEL_NOT_COVERED)
        elif token != request.model:
            changes["model"] = token

    departments = tuple(entry.name for entry in catalog.departments)
    department = _match(request.department, departments)
    if department is None:
        # Answered, not refused: "we have no listings from your department" is a real
        # answer, and rejecting it would leave whoever lives there with no service.
        warnings.append(DEPARTMENT_NOT_COVERED)
    elif department != request.department:
        changes["department"] = department

    resolved = request.model_copy(update=changes) if changes else request
    return Resolved(request=resolved, warnings=warnings)


def _check_engine(request: PredictRequest, allowed: NumericRange) -> None:
    """Reject a displacement the vertical never saw."""
    lowest, highest = int(allowed.min), int(allowed.max)
    if not lowest <= request.engine_cc <= highest:  # type: ignore[operator]
        _reject(
            f"engine_cc {request.engine_cc} is outside the {request.vehicle_type} range "
            f"{lowest}-{highest}; leave it empty rather than guessing"
        )


def _check_asking_price(request: PredictRequest, allowed: NumericRange) -> None:
    """Reject an asking price far below anything the vertical was trained on.

    Only the floor is enforced, and the asymmetry is deliberate. A price under the floor is
    a typo — 59 pesos came back as "Ganga · Pides 100 % menos" — while a price above the
    ceiling is a listing that really is asking too much, which is precisely what the
    expensive label exists to say. Rejecting it would delete the answer the caller came for.
    """
    if request.asking_price_cop < int(allowed.min):  # type: ignore[operator]
        _reject(
            f"asking_price_cop {request.asking_price_cop} is below the lowest "
            f"{request.vehicle_type} price the model was trained on, {int(allowed.min)}; "
            "that is a typo rather than a bargain"
        )
