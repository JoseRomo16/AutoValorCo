"""Request and response contracts for the API.

Kept apart from the routes because these are the published surface of the product: the
Next.js app of F4 is written against them, and anything here that changes shape is a
breaking change whether or not the routing code moves.

Two decisions run through the whole file.

**The band is not optional and the label is.** Every estimate ships with a P10-P90 range,
because a used-vehicle price without one is a false precision. The bargain/fair/expensive
label only appears when the vertical's band passed the quality gate — see
:mod:`autovalor.models.quantiles` — and when it does not, ``precision_notice`` says so in
the same payload rather than leaving the client to infer it from a missing field.

**Explanations are multiplicative factors, not peso deltas.** The model predicts
``log(price)``, so SHAP contributions are additive in logs and ``exp(phi)`` is an *exact*
factor on the price: 0.78 means "this vehicle is worth 22 % less because of this". Pesos
are not additive and a peso breakdown would be an approximation presented as arithmetic.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from autovalor.models.dataset import VehicleType

Label = Literal["bargain", "fair", "expensive"]

MIN_MODEL_YEAR = 1950
MAX_MODEL_YEAR = 2100
"""Deliberately wider than the plausibility bounds the lake enforces. This is input
validation, not a quality contract: a 2035 model year is a typo to reject at the edge, and
the narrower year checks belong to the data layer that already owns them."""

MAX_MILEAGE_KM = 2_000_000
MAX_ENGINE_CC = 10_000


class PredictRequest(BaseModel):
    """One vehicle to value.

    Only the fields the served model actually uses are accepted. A request carrying a
    colour or a trim would be quietly ignored, which is worse than a clear rejection, so
    unknown fields are refused.
    """

    model_config = {"extra": "forbid"}

    vehicle_type: VehicleType = Field(description="Which vertical to value against.")
    brand: str = Field(min_length=1, max_length=60, description="Make, e.g. 'Toyota'.")
    model: str | None = Field(
        default=None, max_length=60, description="Model token, e.g. 'corolla'. Optional."
    )
    model_year: Annotated[int, Field(ge=MIN_MODEL_YEAR, le=MAX_MODEL_YEAR)] = Field(
        description="Model year as advertised."
    )
    mileage_km: Annotated[int, Field(ge=0, le=MAX_MILEAGE_KM)] = Field(
        description="Odometer reading in kilometres."
    )
    department: str = Field(
        min_length=1, max_length=60, description="Colombian department where it is sold."
    )
    engine_cc: Annotated[int, Field(ge=1, le=MAX_ENGINE_CC)] | None = Field(
        default=None,
        description=(
            "Displacement in cc. Optional: the model treats an unknown engine as its own "
            "signal rather than guessing an average."
        ),
    )
    asking_price_cop: Annotated[int, Field(ge=1)] | None = Field(
        default=None,
        description=(
            "Asking price, in COP. Supply it to get the bargain/fair/expensive label; "
            "without it there is nothing to compare the band against."
        ),
    )


class PriceBand(BaseModel):
    """The P10-P90 range around an estimate, in pesos."""

    lower_cop: float = Field(description="P10: one listing in ten is expected below this.")
    estimate_cop: float = Field(description="P50, the point estimate.")
    upper_cop: float = Field(description="P90: one listing in ten is expected above this.")
    relative_width: float = Field(
        description="(upper - lower) / estimate. The narrower, the more informative."
    )


class PredictResponse(BaseModel):
    """An estimate, its range, and the label when the vertical has earned one."""

    vehicle_type: VehicleType
    band: PriceBand
    label: Label | None = Field(
        default=None,
        description=(
            "Where the asking price falls inside the band. Null when no asking price was "
            "supplied, or when this vertical's band is not precise enough to label."
        ),
    )
    precision_notice: str | None = Field(
        default=None,
        description=(
            "Why no label is shown, when the reason is the band's quality rather than a "
            "missing asking price. Render it next to the estimate."
        ),
    )
    model_version: str = Field(description="Served model version; matches /model-info.")


class Factor(BaseModel):
    """One feature's contribution, as a multiplicative factor on the price."""

    feature: str
    value: str | None = Field(description="The vehicle's value for this feature, as shown.")
    factor: float = Field(
        description=(
            "exp(phi): the exact multiplier this feature applies to the price. 1.15 means "
            "it makes the vehicle 15 % dearer than the baseline."
        )
    )
    direction: Literal["raises", "lowers"] = Field(
        description="Whether the factor pushes the price up or down."
    )


class ExplainResponse(BaseModel):
    """Why the model landed where it did.

    ``base_price_cop`` times the product of every factor is the estimate — exactly, not
    approximately — which is the property that makes this explanation checkable.
    """

    vehicle_type: VehicleType
    estimate_cop: float
    base_price_cop: float = Field(
        description="Where every explanation starts, before any feature moves it."
    )
    factors: list[Factor] = Field(description="The strongest contributions, largest first.")
    model_version: str


class VerticalInfo(BaseModel):
    """What the service can say about one vertical."""

    vehicle_type: VehicleType
    model_version: str
    mape: float = Field(description="Held-out mean absolute percentage error, as a fraction.")
    interval_coverage: float = Field(description="Share of held-out prices inside the band.")
    interval_mean_relative_width: float
    publishes_label: bool = Field(description="Whether this vertical shows bargain/fair/expensive.")
    label_withheld_because: list[str] = Field(
        default_factory=list, description="Empty when the label is published."
    )
    trained_on_rows: int


class ModelInfoResponse(BaseModel):
    """Description of the models currently served."""

    version: str = Field(description="Bundle version, shared by every vertical.")
    target: str = Field(description="Modeled target variable.")
    verticals: list[VerticalInfo]


class HealthResponse(BaseModel):
    """Liveness and readiness.

    Separate booleans on purpose: the process can be up while no model is loaded, which is
    what a development checkout without artifacts looks like, and a platform health check
    should be able to tell those apart.
    """

    status: Literal["ok", "degraded"]
    version: str = Field(description="Version of the autovalor package.")
    models_loaded: list[VehicleType]


class ErrorResponse(BaseModel):
    """What every 4xx and 5xx looks like."""

    detail: str = Field(description="What went wrong, in terms the caller can act on.")
