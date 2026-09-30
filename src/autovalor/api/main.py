"""FastAPI application.

F0 only wires up the service skeleton: ``/health`` is fully functional and
``/model-info`` reports configuration. ``/predict`` and ``/explain`` arrive in F4,
once a model is registered in MLflow (F2).
"""

from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from autovalor import __version__
from autovalor.config import Settings, get_settings


class HealthResponse(BaseModel):
    """Liveness payload used by Docker and the deployment platform."""

    status: Literal["ok"] = "ok"
    version: str = Field(description="Version of the autovalor package.")


class ModelInfoResponse(BaseModel):
    """Description of the model currently served."""

    version: str = Field(description="Served model version, 'unreleased' until F2 closes.")
    experiment: str = Field(description="MLflow experiment the model is tracked in.")
    vehicle_types: list[str] = Field(description="Vehicle types with a separate model.")
    target: str = Field(description="Modeled target variable.")


app = FastAPI(
    title="AutoValor CO",
    description="Used car and motorcycle valuation for the Colombian market.",
    version=__version__,
)

SettingsDep = Annotated[Settings, Depends(get_settings)]


@app.get("/health", summary="Liveness probe")
def health() -> HealthResponse:
    """Report that the service is up."""
    return HealthResponse(version=__version__)


@app.get("/model-info", summary="Served model metadata")
def model_info(settings: SettingsDep) -> ModelInfoResponse:
    """Describe the model backing ``/predict``."""
    return ModelInfoResponse(
        version=settings.served_model_version,
        experiment=settings.mlflow_experiment,
        vehicle_types=["car", "motorcycle"],
        target="log_price",
    )
