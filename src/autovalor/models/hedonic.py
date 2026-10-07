"""The hedonic OLS baseline.

A hedonic regression explains a price by the attributes of the good: in this market,
age, mileage, make, model, engine size and where it is being sold. It is the baseline
every later ensemble has to beat — if LightGBM cannot improve on a linear model with
dummies, the extra complexity is not earning its keep.

Two feature sets are fitted on purpose, because the F1 pilot's main finding was about
features rather than volume:

``basic``
    Age, mileage and department. The set that stalled at sigma ~ 0.58 for cars no matter how
    many rows were added.
``full``
    Plus make, model and engine size — the columns mined from the listing title.

Built on scikit-learn rather than statsmodels formulas for one reason that matters out of
sample: ``OneHotEncoder`` can be told to ignore categories it never saw while fitting, so
a make or model that only appears in the holdout degrades the prediction instead of
crashing it. Coefficient inference, if F3 wants it, is a separate concern.
"""

import warnings
from dataclasses import dataclass
from typing import Literal, get_args

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from autovalor.models.dataset import VehicleType
from autovalor.models.spec import FeatureSpec

__all__ = ["FeatureSpec"]
"""Re-exported: the type moved to :mod:`autovalor.models.spec` so the API image does not
have to install scikit-learn to read a model's column list, and every existing import
of it from here keeps working."""

FeatureSet = Literal["basic", "full"]

FEATURE_SETS: tuple[FeatureSet, ...] = get_args(FeatureSet)

TARGET = "log_price"
"""Prices are modeled on the log scale: errors are proportional, and the distribution of
asking prices is right-skewed."""

MIN_CATEGORY_FREQUENCY = 5
"""Categories rarer than this are pooled into a single "infrequent" level. A model dummy
estimated from two listings fits those two listings and predicts noise; motorcycles have
764 distinct model tokens over 3,765 rows, so pooling is not optional there."""

AGE_SQUARED = "vehicle_age_squared"
LOG_MILEAGE = "log_mileage_km"


def feature_spec(feature_set: FeatureSet, vehicle_type: VehicleType) -> FeatureSpec:
    """Return the columns for a feature set in a given vertical.

    Args:
        feature_set: ``basic`` or ``full``.
        vehicle_type: Vertical being modeled; motorcycles carry the ``is_quad`` flag
            because quads, buggies and side-by-sides share the vertical but not its
            price curve.

    Returns:
        The specification, before derived columns are added by :func:`add_derived`.

    Raises:
        ValueError: If ``feature_set`` is not recognised.
    """
    # Checked up front rather than as a trailing else: the literal type makes mypy treat
    # any code after the two branches as unreachable.
    if feature_set not in FEATURE_SETS:
        msg = f"unknown feature set {feature_set!r}"
        raise ValueError(msg)

    if feature_set == "basic":
        return FeatureSpec(
            numeric=("vehicle_age_years", AGE_SQUARED, LOG_MILEAGE),
            categorical=("department",),
            boolean=(),
        )

    boolean = (
        ("is_official_store", "is_quad") if vehicle_type == "motorcycle" else ("is_official_store",)
    )
    return FeatureSpec(
        numeric=("vehicle_age_years", AGE_SQUARED, LOG_MILEAGE, "engine_cc"),
        categorical=("department", "brand", "model"),
        boolean=boolean,
    )


def add_derived(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``frame`` with the derived regression columns added.

    Depreciation is not linear in age and the price effect of mileage is proportional,
    so the linear model is given an age-squared term and log mileage rather than being
    asked to approximate both with a straight line.

    Args:
        frame: Gold rows.

    Returns:
        A copy carrying :data:`AGE_SQUARED` and :data:`LOG_MILEAGE`.
    """
    enriched = frame.copy()
    age = enriched["vehicle_age_years"].astype("float64")
    enriched[AGE_SQUARED] = age**2
    # log1p keeps a genuinely new vehicle at zero instead of minus infinity.
    enriched[LOG_MILEAGE] = np.log1p(enriched["mileage_km"].astype("float64"))
    return enriched


def build_pipeline(spec: FeatureSpec) -> Pipeline:
    """Assemble the preprocessing and OLS pipeline for a feature specification.

    Args:
        spec: Columns to consume.

    Returns:
        An unfitted pipeline mapping a gold-shaped frame to ``log(price)``.
    """
    steps: list[tuple[str, object, list[str]]] = [
        (
            "numeric",
            # engine_cc is missing for ~14 % of cars and ~19 % of motorcycles; the
            # indicator lets the model treat "unknown engine" as its own signal rather
            # than silently pretending every such listing is average.
            SimpleImputer(strategy="median", add_indicator=True),
            list(spec.numeric),
        ),
    ]
    if spec.categorical:
        steps.append(
            (
                "categorical",
                OneHotEncoder(
                    handle_unknown="infrequent_if_exist",
                    min_frequency=MIN_CATEGORY_FREQUENCY,
                    sparse_output=False,
                    drop="first",
                ),
                list(spec.categorical),
            )
        )
    if spec.boolean:
        # Already numeric by the time they get here (see prepare), and passed through as
        # a plain string rather than a FunctionTransformer: a custom callable inside the
        # pipeline is a type MLflow's serializer refuses to load without an exemption.
        steps.append(("boolean", "passthrough", list(spec.boolean)))

    return Pipeline(
        [
            (
                "features",
                ColumnTransformer(steps, remainder="drop", verbose_feature_names_out=False),
            ),
            # Rank-deficient dummy matrices are expected here; the lstsq solver returns
            # the minimum-norm solution instead of failing.
            ("ols", LinearRegression()),
        ]
    )


def prepare(frame: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    """Return just the columns a spec needs, with categories as strings.

    Args:
        frame: Gold rows, already passed through :func:`add_derived`.
        spec: Columns to keep.

    Returns:
        A frame of exactly ``spec.columns``.
    """
    prepared = frame.loc[:, list(spec.columns)].copy()
    for column in spec.categorical:
        # A missing model token is a level in its own right ("make known, model not"),
        # not a row to drop.
        prepared[column] = prepared[column].fillna("Desconocido").astype(str)
    for column in spec.boolean:
        prepared[column] = prepared[column].fillna(False).astype("float64")
    return prepared


def fit_hedonic(
    train: pd.DataFrame,
    *,
    feature_set: FeatureSet,
    vehicle_type: VehicleType,
) -> tuple[Pipeline, FeatureSpec]:
    """Fit the hedonic baseline on a training frame.

    Args:
        train: Training rows from gold.
        feature_set: ``basic`` or ``full``.
        vehicle_type: Vertical being modeled.

    Returns:
        The fitted pipeline and the spec it was fitted with.
    """
    spec = feature_spec(feature_set, vehicle_type)
    enriched = add_derived(train)
    pipeline = build_pipeline(spec)
    pipeline.fit(prepare(enriched, spec), enriched[TARGET].astype("float64"))
    return pipeline, spec


def predict_log_price(pipeline: Pipeline, frame: pd.DataFrame, spec: FeatureSpec) -> np.ndarray:
    """Predict ``log(price)`` for a gold-shaped frame.

    Args:
        pipeline: Pipeline returned by :func:`fit_hedonic`.
        frame: Rows to score, straight from gold.
        spec: Spec the pipeline was fitted with.

    Returns:
        Predicted ``log(price)``, one value per row.
    """
    # Unseen makes and models are the expected case on a holdout, and the encoder is
    # configured to absorb them; its per-call warning would otherwise bury the metrics.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Found unknown categories", category=UserWarning)
        prediction: np.ndarray = pipeline.predict(prepare(add_derived(frame), spec))
    return prediction


@dataclass(frozen=True)
class HedonicModel:
    """The fitted baseline behind the same interface the tree models expose.

    Lets :mod:`autovalor.models.train` score every model the same way instead of
    branching on which one it is holding.

    Attributes:
        pipeline: The fitted pipeline.
        spec: Columns it was fitted on.
    """

    pipeline: Pipeline
    spec: FeatureSpec

    def predict_log_price(self, frame: pd.DataFrame) -> np.ndarray:
        """Predict ``log(price)`` for a gold-shaped frame."""
        return predict_log_price(self.pipeline, frame, self.spec)


def fit_hedonic_model(
    train: pd.DataFrame,
    *,
    feature_set: FeatureSet,
    vehicle_type: VehicleType,
) -> HedonicModel:
    """Fit the baseline and wrap it in :class:`HedonicModel`.

    Args:
        train: Training rows from gold.
        feature_set: ``basic`` or ``full``.
        vehicle_type: Vertical being modeled.

    Returns:
        The fitted model.
    """
    pipeline, spec = fit_hedonic(train, feature_set=feature_set, vehicle_type=vehicle_type)
    return HedonicModel(pipeline=pipeline, spec=spec)
