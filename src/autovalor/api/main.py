"""FastAPI application — the F4 product surface.

Five routes, and the shape of each one follows from a decision taken earlier in the project
rather than from REST habit:

``/predict``
    An estimate **and** a P10-P90 range, always. The label only when the vertical's band
    passed the quality gate; otherwise the same payload carries the precision notice.
``/explain``
    Multiplicative factors, because SHAP is additive in log space and ``exp(phi)`` is an
    exact factor on the price. Peso deltas would be an approximation dressed as arithmetic.
``/market``
    The F3 result tables, served from the files ``make results`` wrote. The dashboard reads
    them; it does not recompute them, and neither does this service.
``/health`` and ``/model-info``
    Real, not stubs. ``/health`` separates "the process is up" from "a model is loaded",
    because a checkout without artifacts is the second and a platform probe needs to tell.

Models load once at start-up and live in application state. A per-request load would read
and parse four boosters per call; a module-level global would make the tests fight over one
instance.
"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from autovalor import __version__
from autovalor.api.features import to_frame
from autovalor.api.schemas import (
    ErrorResponse,
    ExplainResponse,
    Factor,
    HealthResponse,
    ModelInfoResponse,
    PredictRequest,
    PredictResponse,
    PriceBand,
    VerticalInfo,
)
from autovalor.config import Settings, get_settings
from autovalor.models.bundle import ARTIFACTS_DIR, ServedModel, load_served_models
from autovalor.models.dataset import VehicleType
from autovalor.models.explain import shap_contributions

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
            trained_on_rows=int(model.lake["rows"]),
        )
        for model in (models[key] for key in sorted(models))
    ]
    version = verticals[0].model_version if verticals else "unreleased"
    return ModelInfoResponse(version=version, target="log_price", verticals=verticals)


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
    frame = to_frame(request)
    bounds = model.predict_bounds(frame)
    lower, estimate, upper = (float(np.exp(value)) for value in bounds[0])

    label = None
    if request.asking_price_cop is not None:
        labels = model.classify(
            [float(np.log(request.asking_price_cop))], [bounds[0, 0]], [bounds[0, 2]]
        )
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
    frame = to_frame(request)
    phi, base = shap_contributions(model.point, frame)

    row = phi.iloc[0]
    ranked = row.reindex(row.abs().sort_values(ascending=False).index).head(TOP_FACTORS)
    factors = [
        Factor(
            feature=str(feature),
            value=_shown(frame.iloc[0].get(feature)),
            factor=float(np.exp(contribution)),
            direction="raises" if contribution >= 0 else "lowers",
        )
        for feature, contribution in ranked.items()
    ]
    return ExplainResponse(
        vehicle_type=request.vehicle_type,
        estimate_cop=float(np.exp(model.predict_log_price(frame)[0])),
        base_price_cop=float(np.exp(base)),
        factors=factors,
        model_version=model.version,
    )


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
