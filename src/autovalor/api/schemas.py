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


class PrecisionCode(BaseModel):
    """One reason the bargain/fair/expensive label is withheld, as data.

    The product has to explain a withheld label in the reader's language, and a translated
    sentence cannot be derived from an English one. `code` is one of `coverage_below_min`,
    `coverage_above_max` or `width_above_max`; `value` and `limit` are fractions, so a
    client formats "81 % against a maximum of 60 %" itself.
    """

    code: str
    value: float = Field(description="What was measured on the holdout, as a fraction.")
    limit: float = Field(description="The threshold it failed against, as a fraction.")
    message: str = Field(description="The English sentence, unchanged.")


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
            "missing asking price. Render it next to the estimate. English, because it is "
            "the wording this field shipped with; `precision_codes` is what a client "
            "translates."
        ),
    )
    precision_codes: list[PrecisionCode] = Field(
        default_factory=list,
        description=(
            "The same reasons as codes with the numbers behind them, for a client that "
            "renders them in its own language. Empty when a label is published, and also "
            "on a bundle exported before the codes existed."
        ),
    )
    model_version: str = Field(description="Served model version; matches /model-info.")


class LocalizedText(BaseModel):
    """One string in the two languages the product publishes."""

    es: str = Field(description="Spanish, the product's default language.")
    en: str = Field(description="English.")


class Factor(BaseModel):
    """One feature's contribution, as a multiplicative factor on the price.

    ``feature`` and ``value`` are the technical pair: a stable key and the raw value, which
    is what a client should log, plot or compare against. ``label`` and ``value_display``
    are the same thing for a reader — "Edad del vehículo", "8 años" — because a product card
    showing ``vehicle_age_years = 8.0`` is showing the inside of the model.
    """

    feature: str = Field(description="Technical column name; stable across languages.")
    label: LocalizedText = Field(description="The feature's name for a reader.")
    value: str | None = Field(description="The vehicle's raw value, or null when not supplied.")
    value_display: LocalizedText = Field(
        description="The value with its unit, e.g. '60.000 km'. Says so when not supplied."
    )
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
        default_factory=list, description="Empty when the label is published. English."
    )
    label_withheld_codes: list[PrecisionCode] = Field(
        default_factory=list,
        description="The same reasons as codes with their values. Empty when published.",
    )
    baseline_mape: float | None = Field(
        default=None,
        description=(
            "Held-out MAPE of the OLS reference on the same partition, so the gain from "
            "the served model is a figure rather than a claim. Null on a bundle exported "
            "before it was recorded."
        ),
    )
    interval_uncalibrated_coverage: float | None = Field(
        default=None,
        description=(
            "Coverage the three quantile models reach on their own, before the conformal "
            "widening. The gap against interval_coverage is what calibrating bought."
        ),
    )
    metrics_temporal: dict[str, float] | None = Field(
        default=None,
        description=(
            "The same model family measured on a time-ordered partition instead of the "
            "grouped random one. A second measurement, never the published figure. Null "
            "when the lake does not span enough days for that partition."
        ),
    )
    trained_on_rows: int


class LabelGate(BaseModel):
    """The rule a vertical's band has to pass before its label may be published.

    The same three thresholds for every vertical, which is why they sit beside the list
    rather than inside each entry. Published because ``label_withheld_codes`` carries a
    limit only for the rule that failed: a vertical that passes carries none, and the
    coverage window never appears in full because a failure is one-sided by construction.
    A client that explains the rule needs all three, in its own language.
    """

    min_coverage: float = Field(description="Lowest held-out coverage that earns a label.")
    max_coverage: float = Field(
        description="Highest. Over-covering stops the label discriminating."
    )
    max_relative_width: float = Field(description="Widest mean band, as a share of the estimate.")


class ModelInfoResponse(BaseModel):
    """Description of the models currently served."""

    version: str = Field(description="Bundle version, shared by every vertical.")
    target: str = Field(description="Modeled target variable.")
    verticals: list[VerticalInfo]
    label_gate: LabelGate | None = Field(
        default=None,
        description=(
            "The thresholds every vertical above was judged against. Null on a bundle "
            "exported before the gate was published."
        ),
    )


class HealthResponse(BaseModel):
    """Liveness and readiness.

    Separate booleans on purpose: the process can be up while no model is loaded, which is
    what a development checkout without artifacts looks like, and a platform health check
    should be able to tell those apart.
    """

    status: Literal["ok", "degraded"]
    version: str = Field(description="Version of the autovalor package.")
    models_loaded: list[VehicleType]


class CatalogEntry(BaseModel):
    """One categorical level the served model has a category for."""

    name: str
    listings: int = Field(description="Training listings that carried this level.")
    display_name: str = Field(
        description=(
            "The same level spelled for a reader. Model tokens are mined from titles in "
            "lower case, so 'cx-30' displays as 'CX-30'; makes and departments display as "
            "themselves. Send `name`, show `display_name`."
        )
    )


class CatalogBrand(BaseModel):
    """One make, with the model tokens seen under it in training."""

    name: str
    listings: int
    display_name: str = Field(description="The make as a reader sees it; equals `name`.")
    models: list[CatalogEntry] = Field(description="Model tokens for this make, alphabetically.")


class CatalogRange(BaseModel):
    """The closed range of a numeric input, as training observed it."""

    min: float
    max: float


class VerticalCatalog(BaseModel):
    """The valid inputs for one vertical.

    Everything here is derived from the rows the served model was fitted on, which is the
    point: a make outside this list has no category in the trees, so the model would route
    it down its missing branch and still answer with a confident-looking number. A form
    built from these lists cannot ask that question.
    """

    vehicle_type: VehicleType
    model_version: str = Field(description="Served model these lists came from; matches /predict.")
    trained_on_rows: int = Field(description="Training rows the lists were derived from.")
    brands: list[CatalogBrand] = Field(description="Makes, alphabetically, each with its models.")
    departments: list[CatalogEntry] = Field(description="Departments, alphabetically.")
    model_year: CatalogRange
    engine_cc: CatalogRange | None = Field(
        default=None, description="Null when the vertical records no displacement."
    )


class CatalogResponse(BaseModel):
    """What the valuation form may offer, per vertical."""

    verticals: list[VerticalCatalog]


class ErrorResponse(BaseModel):
    """What every 4xx and 5xx looks like."""

    detail: str = Field(description="What went wrong, in terms the caller can act on.")
