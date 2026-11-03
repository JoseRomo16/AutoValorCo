"""FastAPI application — the F4 product surface.

Six routes, and the shape of each one follows from a decision taken earlier in the project
rather than from REST habit:

``/predict``
    An estimate **and** a P10-P90 range, always. The label only when the vertical's band
    passed the quality gate; otherwise the same payload carries the precision notice.
``/explain``
    Multiplicative factors, because SHAP is additive in log space and ``exp(phi)`` is an
    exact factor on the price. Peso deltas would be an approximation dressed as arithmetic.
    The estimate it reports is the same one ``/predict`` publishes, by construction: both
    read :meth:`~autovalor.models.bundle.ServedModel.predict_published_band`'s centre.
``/catalog``
    The makes, models, departments and ranges the served model was fitted on. The form is
    built from these because the trees' categories are frozen, so a make outside the list
    is a question the model cannot answer honestly.
``/market``
    The F3 result tables, served from the files ``make results`` wrote. The dashboard reads
    them; it does not recompute them, and neither does this service.
``/health`` and ``/model-info``
    Real, not stubs. ``/health`` separates "the process is up" from "a model is loaded",
    because a checkout without artifacts is the second and a platform probe needs to tell.

``/`` redirects to ``/docs`` and is kept out of the schema: it is a courtesy for whoever
opens the deployed URL, not part of the contract the frontend is written against.

Models load once at start-up and live in application state. A per-request load would read
and parse four boosters per call; a module-level global would make the tests fight over one
instance.
"""

import json
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from autovalor import __version__
from autovalor.api.features import to_frame
from autovalor.api.labels import Localized, feature_label, format_value
from autovalor.api.regions import AVERAGE_REGION, average_band, average_contributions, weights
from autovalor.api.rules import DEPARTMENT_NOT_COVERED, resolve, year_range
from autovalor.api.schemas import (
    MAX_MILEAGE_KM,
    CatalogBrand,
    CatalogEntry,
    CatalogRange,
    CatalogResponse,
    ErrorResponse,
    ExplainResponse,
    Factor,
    HealthResponse,
    LabelGate,
    LocalizedText,
    ModelInfoResponse,
    PrecisionCode,
    PredictRequest,
    PredictResponse,
    PriceBand,
    VerticalCatalog,
    VerticalInfo,
)
from autovalor.config import Settings, get_settings
from autovalor.models.bundle import ARTIFACTS_DIR, ServedModel, load_served_models
from autovalor.models.catalog import NamedCount, VehicleCatalog
from autovalor.models.dataset import VehicleType
from autovalor.models.explain import shap_contributions
from autovalor.models.serving import SERVING_ASSUMPTIONS

logger = logging.getLogger("autovalor.api")

RESULTS_DIR = Path(__file__).resolve().parents[3] / "docs" / "results"
"""Where ``make results`` writes the F3 tables that ``/market`` serves."""

TOP_FACTORS = 5
"""How many contributions ``/explain`` returns. Five is what fits in a product card."""

NOT_READY = "No model is loaded for this vertical. The service was started without artifacts."


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load the served models once, at start-up."""
    app.state.models = load_served_models(ARTIFACTS_DIR)
    yield
    app.state.models = {}


app = FastAPI(
    title="AutoValor CO",
    description="Used car and motorcycle valuation for the Colombian market.",
    version=__version__,
    lifespan=lifespan,
)

settings_at_import = get_settings()
app.add_middleware(
    CORSMiddleware,
    # The frontend is a static site on another origin, so it cannot talk to this service
    # without an explicit allow-list. Configured rather than wildcarded: "*" plus
    # credentials is rejected by browsers anyway, and an allow-list is one env var.
    allow_origins=settings_at_import.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

SettingsDep = Annotated[Settings, Depends(get_settings)]


def _models(request: Request) -> dict[VehicleType, ServedModel]:
    models: dict[VehicleType, ServedModel] = getattr(request.app.state, "models", {})
    return models


ModelsDep = Annotated[dict[VehicleType, ServedModel], Depends(_models)]


def _require(models: dict[VehicleType, ServedModel], vehicle_type: VehicleType) -> ServedModel:
    """Return the model for a vertical, or fail with a message that says what to do."""
    model = models.get(vehicle_type)
    if model is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=NOT_READY)
    return model


def _average_over(model: ServedModel, warnings: list[str]) -> tuple[tuple[str, float], ...]:
    """Departments to average over, or empty when the request names a covered one.

    The decision is read off the warning the rules layer already produced, so "which
    departments does this model know" is answered in exactly one place.
    """
    if DEPARTMENT_NOT_COVERED not in warnings or model.catalog is None:
        return ()
    return weights(model.catalog)


def _precision_codes(model: ServedModel) -> list[PrecisionCode]:
    """Return the label-gate failures as codes a client can translate."""
    return [
        PrecisionCode(
            code=failure.code,
            value=failure.value,
            limit=failure.limit,
            message=failure.message,
        )
        for failure in model.label.failure_codes
    ]


def _known_departments(model: ServedModel) -> tuple[str, ...]:
    """Department levels the served model was fitted on, for spelling-tolerant matching."""
    if model.catalog is None:
        return ()
    return tuple(entry.name for entry in model.catalog.departments)


def _year_range(catalog: VehicleCatalog) -> CatalogRange:
    """The model years ``/predict`` accepts, as ``/catalog`` publishes them."""
    lowest, highest = year_range(catalog)
    return CatalogRange(min=float(lowest), max=float(highest))


def _catalog_entry(level: NamedCount) -> CatalogEntry:
    """Return one catalogue level as the API publishes it."""
    return CatalogEntry(name=level.name, listings=level.listings, display_name=level.display_name)


@app.get(
    "/",
    summary="Go to the interactive documentation",
    response_class=RedirectResponse,
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    include_in_schema=False,
)
def root() -> RedirectResponse:
    """Send the root to ``/docs``.

    The deployed URL is what gets pasted into a CV and a README, and a bare FastAPI root
    answers ``{"detail":"Not Found"}`` there. 307 rather than 301: a permanent redirect is
    cached by the browser indefinitely, which would outlive any later decision to serve
    something else at the root.
    """
    return RedirectResponse(url="/docs", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/health", summary="Liveness and readiness")
def health(models: ModelsDep) -> HealthResponse:
    """Report whether the service is up and whether it can actually answer."""
    return HealthResponse(
        status="ok" if models else "degraded",
        version=__version__,
        models_loaded=sorted(models),
    )


@app.get("/model-info", summary="Served model metadata")
def model_info(models: ModelsDep) -> ModelInfoResponse:
    """Describe every model backing ``/predict``, including what each one may publish."""
    verticals = [
        VerticalInfo(
            vehicle_type=model.vehicle_type,
            model_version=model.version,
            mape=model.metrics["mape"],
            interval_coverage=model.metrics["interval_coverage"],
            interval_mean_relative_width=model.metrics["interval_mean_relative_width"],
            publishes_label=model.label.publishes_label,
            label_withheld_because=list(model.label.failures),
            label_withheld_codes=_precision_codes(model),
            baseline_mape=model.metrics.get("baseline_mape"),
            interval_uncalibrated_coverage=model.interval_uncalibrated_coverage,
            metrics_temporal=model.metrics_temporal,
            total_rows=int(model.lake["rows"]),
            train_rows=None if model.catalog is None else model.catalog.n_rows,
            trained_on_rows=int(model.lake["rows"]),
        )
        for model in (models[key] for key in sorted(models))
    ]
    version = verticals[0].model_version if verticals else "unreleased"
    return ModelInfoResponse(
        version=version,
        target="log_price",
        verticals=verticals,
        label_gate=_label_gate(models),
    )


def _label_gate(models: Mapping[VehicleType, ServedModel]) -> LabelGate | None:
    """Return the gate the served bundles were judged against.

    Read from the bundles rather than from this module's constants, so the rule published
    describes the models actually loaded. Every vertical is judged against the same
    thresholds, so disagreement between two loaded bundles means they were exported by
    different code — reporting nothing is the honest answer to that, because picking one
    would describe one vertical's verdict as if it were the other's.
    """
    gates = {
        (gate.min_coverage, gate.max_coverage, gate.max_relative_width)
        for model in models.values()
        if (gate := model.label_gate) is not None
    }
    if len(gates) != 1:
        return None
    minimum, maximum, width = gates.pop()
    return LabelGate(min_coverage=minimum, max_coverage=maximum, max_relative_width=width)


@app.get(
    "/catalog",
    summary="What the valuation form may ask about",
    responses={503: {"model": ErrorResponse}},
)
def catalog(models: ModelsDep, vehicle_type: VehicleType | None = None) -> CatalogResponse:
    """List the makes, models, departments and ranges the served models were fitted on.

    The frontend's form is built from this, not from a hand-written list: a make the trees
    have no category for would be routed down their missing branch and still produce a
    confident-looking estimate, and a list typed by hand goes stale the first time the lake
    grows. See :mod:`autovalor.models.catalog`.

    Args:
        models: The loaded bundles.
        vehicle_type: One vertical; omit for both.

    Returns:
        One entry per vertical that carries a catalogue.

    Raises:
        HTTPException: 503 when no model is loaded, or when the loaded bundle predates
            catalogues — predictions still work, so this says what to re-run rather than
            returning empty lists a form would render as a dead dropdown.
    """
    if vehicle_type is None:
        wanted = sorted(models)
    else:
        # _require so an unloaded vertical answers 503 with "start it with artifacts"
        # rather than an empty list that looks like "this vertical has no makes".
        wanted = [_require(models, vehicle_type).vehicle_type]

    verticals = []
    for key in wanted:
        model = models[key]
        if model.catalog is None:
            continue
        verticals.append(
            VerticalCatalog(
                vehicle_type=model.vehicle_type,
                model_version=model.version,
                train_rows=model.catalog.n_rows,
                total_rows=int(model.lake["rows"]),
                trained_on_rows=model.catalog.n_rows,
                brands=[
                    CatalogBrand(
                        name=brand.name,
                        listings=brand.listings,
                        display_name=brand.display_name,
                        models=[_catalog_entry(entry) for entry in brand.models],
                    )
                    for brand in model.catalog.brands
                ],
                departments=[_catalog_entry(entry) for entry in model.catalog.departments],
                # The range `/predict` actually enforces, not the raw training span: the
                # two used to differ, which is how a form could offer a year the service
                # then rejected -- or worse, accept one it should not have.
                model_year=_year_range(model.catalog),
                mileage_km=CatalogRange(min=0, max=MAX_MILEAGE_KM),
                engine_cc=None
                if model.catalog.engine_cc is None
                else CatalogRange(min=model.catalog.engine_cc.min, max=model.catalog.engine_cc.max),
                asking_price_cop=None
                if model.catalog.asking_price_cop is None
                else CatalogRange(
                    min=model.catalog.asking_price_cop.min,
                    max=model.catalog.asking_price_cop.max,
                ),
            )
        )

    if not verticals:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "no catalogue is available: the loaded bundle was exported before "
                "catalogues existed. Re-run `make export-model`."
            ),
        )
    return CatalogResponse(verticals=verticals)


@app.post(
    "/predict",
    summary="Estimate a price with its P10-P90 range",
    responses={503: {"model": ErrorResponse}},
)
def predict(request: PredictRequest, models: ModelsDep) -> PredictResponse:
    """Value one vehicle.

    The range is always returned. The label is returned only when this vertical's band
    passed the quality gate *and* an asking price was supplied to compare against.
    """
    model = _require(models, request.vehicle_type)
    # Checked against the catalogue the bundle carries, which is the same list /catalog
    # publishes. See autovalor.api.rules for why this is not in the schema.
    checked = resolve(request, model.catalog)
    request = checked.request
    frame = to_frame(request, departments=_known_departments(model))
    # The published band: calibrated P10 and P90 around the *point* model's estimate, which
    # is the number /explain attributes and the one whose MAPE is published. See
    # ServedModel.predict_published_band.
    # With an uncovered department there is no level to score: the request would take
    # LightGBM's default branch, which is an arbitrary effect rather than an answer about
    # an unknown region. See autovalor.api.regions.
    pairs = _average_over(model, checked.warnings)
    row = average_band(model, frame, pairs) if pairs else model.predict_published_band(frame)[0]
    lower, estimate, upper = (float(np.exp(value)) for value in row)

    label = None
    if request.asking_price_cop is not None:
        # Classified against the band the caller is shown, not a different one.
        labels = model.classify([float(np.log(request.asking_price_cop))], [row[0]], [row[2]])
        label = None if labels is None else labels[0]

    return PredictResponse(
        vehicle_type=request.vehicle_type,
        band=PriceBand(
            lower_cop=lower,
            estimate_cop=estimate,
            upper_cop=upper,
            relative_width=(upper - lower) / estimate,
        ),
        label=label,
        precision_notice=model.label.precision_notice,
        precision_codes=_precision_codes(model),
        warnings=checked.warnings,
        model_version=model.version,
    )


@app.post(
    "/explain",
    summary="Why the estimate landed where it did",
    responses={503: {"model": ErrorResponse}},
)
def explain(request: PredictRequest, models: ModelsDep) -> ExplainResponse:
    """Attribute one estimate to its features, as exact multiplicative factors."""
    model = _require(models, request.vehicle_type)
    checked = resolve(request, model.catalog)
    request = checked.request
    frame = to_frame(request, departments=_known_departments(model))

    pairs = _average_over(model, checked.warnings)
    if pairs:
        # The averaged prediction, attributed exactly: phi is additive in log space and the
        # base does not depend on the row, so averaging the contributions explains the
        # averaged estimate and base x factors = estimate still holds.
        contributions, base, predicted = average_contributions(model, frame, pairs)
    else:
        phi, base = shap_contributions(model.point, frame)
        contributions = phi.iloc[0]
        predicted = float(model.predict_log_price(frame)[0])

    ordered = contributions.reindex(contributions.abs().sort_values(ascending=False).index)
    ranked = _with_supplied(ordered, request, averaged=bool(pairs))
    factors = [
        Factor(
            feature=str(feature),
            label=_localized(feature_label(str(feature))),
            value=_shown(frame.iloc[0].get(feature)),
            value_display=_localized(format_value(str(feature), frame.iloc[0].get(feature))),
            factor=float(np.exp(contribution)),
            direction="raises" if contribution >= 0 else "lowers",
            assumed=str(feature) in SERVING_ASSUMPTIONS,
        )
        for feature, contribution in ranked.items()
    ]
    if pairs:
        # Said plainly rather than echoing back the department the caller typed: the
        # estimate is not about that department, it is the average over the ones we have.
        factors = [
            factor.model_copy(update={"value": None, "value_display": _localized(AVERAGE_REGION)})
            if factor.feature == DEPARTMENT_FEATURE
            else factor
            for factor in factors
        ]
    return ExplainResponse(
        vehicle_type=request.vehicle_type,
        # The same number /predict publishes, from the same model. These were two different
        # models until this block: /predict centred its band on the P50 quantile model while
        # /explain reported the point model, so the product showed two prices for one
        # vehicle and the SHAP reconciliation only held for one of them.
        estimate_cop=float(np.exp(predicted)),
        base_price_cop=float(np.exp(base)),
        factors=factors,
        warnings=checked.warnings,
        model_version=model.version,
    )


DEPARTMENT_FEATURE = "department"

SUPPLIED_ALWAYS_SHOWN = ("engine_cc",)
"""Optional fields that appear in an explanation whenever the caller filled them in.

Measured on the deployed service: a Mazda 3 2018 valued 60,8 M at 1.600 cc and 67,8 M at
2.000 cc, an 11,5 % move, and "Cilindrada" was still absent from the five factors because
five other features moved it more. Someone who typed a number and then cannot find it in
the explanation has no way to tell whether it was used at all.
"""


def _with_supplied(ordered: Any, request: PredictRequest, *, averaged: bool) -> Any:
    """Return the strongest factors, keeping any field that has to stay visible.

    The ranking is untouched and nothing is dropped to make room: an appended factor is a
    weaker one by construction, so promoting it over a stronger one would misrepresent the
    order. The list is therefore the top five *plus* what has to be said.

    Two kinds of addition. A field the caller filled in and would otherwise not appear --
    see :data:`SUPPLIED_ALWAYS_SHOWN`. And the region, whenever the estimate is an average
    over departments: that is the one factor whose displayed value is not the input, so
    hiding it would leave the reader with an averaged price and no sign that it was one.
    """
    top = ordered.head(TOP_FACTORS)
    wanted = list(SUPPLIED_ALWAYS_SHOWN)
    if averaged:
        wanted.append(DEPARTMENT_FEATURE)

    def has_to_show(feature: str) -> bool:
        if averaged and feature == DEPARTMENT_FEATURE:
            return True
        return getattr(request, feature, None) is not None

    extra = [
        feature
        for feature in wanted
        if has_to_show(feature) and feature in ordered.index and feature not in top.index
    ]
    if not extra:
        return top
    return ordered.reindex([*top.index, *extra])


def _localized(text: Localized) -> LocalizedText:
    """Carry a two-language string from the label table into the response model."""
    return LocalizedText(es=text.es, en=text.en)


def _shown(value: Any) -> str | None:
    """Render a feature value for display, or ``None`` when it was not supplied."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


@app.get(
    "/market",
    summary="The published economic results",
    responses={404: {"model": ErrorResponse}},
)
def market(settings: SettingsDep, table: str | None = None) -> dict[str, Any]:
    """Serve the F3 result tables the dashboard reads.

    Args:
        settings: Injected settings, so the directory can be pointed elsewhere in tests.
        table: One table name; omit to list what is available.

    Returns:
        The manifest and the requested table, or the manifest and the index of tables.

    Raises:
        HTTPException: 404 when the table does not exist, naming the ones that do.
    """
    directory = settings.results_dir or RESULTS_DIR
    available = sorted(path.stem for path in directory.glob("*.json") if path.stem != "manifest")
    manifest = _read_json(directory / "manifest.json")

    if table is None:
        return {"manifest": manifest, "tables": available}

    if table not in available:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no table named {table!r}; available: {', '.join(available) or 'none'}",
        )
    return {"manifest": manifest, "table": table, "rows": _read_json(directory / f"{table}.json")}


def _read_json(path: Path) -> Any:
    """Read a published JSON file, or return ``None`` when it has not been generated."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
