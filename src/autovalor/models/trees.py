"""Gradient-boosted trees on the gold layer: LightGBM and CatBoost.

These are the models that have to beat the hedonic baseline to justify their complexity,
and the reason to expect they can is the one thing a linear model cannot do here: handle
high-cardinality categories directly. ``model`` carries 498 values for cars and 764 for
motorcycles, so :mod:`autovalor.models.hedonic` has to pool the rare ones into an
"infrequent" bucket before one-hot encoding them. Both libraries split on the raw category
instead, which is exactly the advantage being measured — so this module deliberately does
**not** reuse the hedonic pipeline.

Nothing here derives age squared or log mileage either. Trees are invariant to monotone
transformations of a feature, so those columns would only add correlated splits.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, get_args

import numpy as np
import numpy.typing as npt
import pandas as pd

from autovalor.models.dataset import DEFAULT_SEED, VehicleType
from autovalor.models.hedonic import FeatureSpec

TreeModel = Literal["lightgbm", "catboost"]

TREE_MODELS: tuple[TreeModel, ...] = get_args(TreeModel)

TREE_NUMERIC = ("vehicle_age_years", "mileage_km", "engine_cc", "km_per_year")
"""Numeric features. ``engine_cc`` keeps its nulls: both libraries route missing values
down their own branch, so "engine size unknown" stays a signal instead of becoming an
imputed average. ``model_year`` is left out as collinear with ``vehicle_age_years``."""

TREE_CATEGORICAL = ("brand", "model", "department", "city")
"""Categorical features, passed raw. ``city`` has ~110 values per vertical; it is included
because trees can use it, but note that sponsored cards leak between regions, so neither
it nor ``department`` is a clean sampling frame."""

TREE_BOOLEAN = ("is_official_store",)
"""Booleans every vertical carries."""

MOTORCYCLE_BOOLEAN = ("is_quad",)
"""Quads, buggies and side-by-sides sit in the motorcycle vertical but not on its price
curve, so the flag reaches the model there and nowhere else."""

DETAIL_CATEGORICAL = ("body_type", "transmission", "brakes", "color")
"""Categoricals that only exist on the listing page.

``body_type`` is the one the enrichment was worth running for: a Naked, a Scooter and an
Enduro at the same displacement are different price classes, and the title never says
which. The other three are free once the page has been fetched.
"""

DETAIL_NUMERIC = ("gear_count", "is_single_owner")
"""Gear count, and single ownership — one of the few condition signals the page offers.

``is_single_owner`` is numeric rather than boolean on purpose. Most adverts leave the
field blank, and the boolean group fills missing values with ``False``, which would turn
"not stated" into "not a single owner" — a claim the advert never made. As a numeric it
keeps its null and both libraries route it down their missing branch, the same treatment
``engine_cc`` gets.
"""

FORBIDDEN_COLUMNS = frozenset(
    {
        "price_cop",
        "log_price",
        "title",
        "listing_id",
        "source_url",
        "first_seen_at",
        "last_seen_at",
        "vehicle_type",
    }
)
"""Columns no model may consume.

The first two are the target. ``title`` is the text the brand, model and engine size were
mined from, so feeding it back is both leakage-adjacent and a free-text column no tree can
use. The identifiers and timestamps would let a model memorise rows instead of learning a
price. A test asserts the specification never includes any of these.
"""

UNKNOWN_CATEGORY = "Desconocido"
"""Level used for a missing category, matching what the hedonic pipeline does."""

DEFAULT_PARAMS: dict[TreeModel, dict[str, Any]] = {
    "lightgbm": {"n_estimators": 400, "learning_rate": 0.05, "num_leaves": 31},
    "catboost": {"iterations": 400, "learning_rate": 0.05, "depth": 6},
}
"""Sane starting points, used when no tuned parameters are supplied."""


def tree_spec(vehicle_type: VehicleType, *, detail_features: bool = False) -> FeatureSpec:
    """Return the columns the tree models consume for a vertical.

    Args:
        vehicle_type: Vertical being modeled.
        detail_features: Also consume the columns that only exist on the listing page.
            Off by default: they are null for every listing that has not been enriched,
            and the pass is incremental, so a run over the whole vertical would feed the
            model mostly-missing columns. Turning it on is only meaningful together with
            ``only_enriched`` on the split, which is what makes a with-and-without
            comparison measure the features rather than the population.

    Returns:
        The specification. Reuses :class:`~autovalor.models.hedonic.FeatureSpec` because
        the grouping — numeric, categorical, boolean — is the same question.
    """
    numeric: tuple[str, ...] = TREE_NUMERIC
    categorical: tuple[str, ...] = TREE_CATEGORICAL
    boolean: tuple[str, ...] = (
        TREE_BOOLEAN + MOTORCYCLE_BOOLEAN if vehicle_type == "motorcycle" else TREE_BOOLEAN
    )
    if detail_features:
        numeric += DETAIL_NUMERIC
        categorical += DETAIL_CATEGORICAL
    return FeatureSpec(numeric=numeric, categorical=categorical, boolean=boolean)


def _model_matrix(frame: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    """Return the feature columns with numeric and boolean types settled.

    Categoricals are left untouched here; each library wants them in a different shape.
    """
    matrix = pd.DataFrame(index=frame.index)
    for column in spec.numeric:
        matrix[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
    for column in spec.categorical:
        matrix[column] = frame[column]
    for column in spec.boolean:
        matrix[column] = frame[column].fillna(False).astype("float64")
    return matrix.loc[:, list(spec.columns)]


def _category_levels(frame: pd.DataFrame, spec: FeatureSpec) -> dict[str, pd.Index]:
    """Return the category levels seen while fitting, one entry per categorical column."""
    return {
        column: pd.Index(sorted(frame[column].dropna().astype(str).unique()))
        for column in spec.categorical
    }


def _as_lightgbm(
    matrix: pd.DataFrame,
    spec: FeatureSpec,
    levels: dict[str, pd.Index],
) -> pd.DataFrame:
    """Cast categoricals to the exact levels seen while fitting.

    Freezing the levels is what makes prediction safe: a make that only appears in the
    holdout lands outside the categories and becomes missing, which LightGBM routes down
    its missing branch. Without this the same value could be encoded as a different
    integer at fit and at predict time.

    Unknown values are mapped to missing explicitly, before the cast. Letting pandas do it
    implicitly — by handing it values outside the categories — works today but is
    deprecated and raises in a future version.
    """
    prepared = matrix.copy()
    for column in spec.categorical:
        values = prepared[column].astype("string")
        known = values.where(values.isin(levels[column]))
        prepared[column] = pd.Categorical(known, categories=levels[column])
    return prepared


def _as_catboost(matrix: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    """Cast categoricals to strings; CatBoost rejects nulls in a categorical column."""
    prepared = matrix.copy()
    for column in spec.categorical:
        prepared[column] = prepared[column].astype("string").fillna(UNKNOWN_CATEGORY).astype(str)
    return prepared


@dataclass(frozen=True)
class FittedTree:
    """A fitted tree model together with everything prediction needs.

    Attributes:
        model_kind: Which library produced it.
        spec: Columns it was fitted on.
        estimator: The fitted regressor.
        levels: Category levels seen while fitting (LightGBM only).
    """

    model_kind: TreeModel
    spec: FeatureSpec
    estimator: object
    levels: dict[str, pd.Index] = field(default_factory=dict)

    def predict_log_price(self, frame: pd.DataFrame) -> npt.NDArray[np.float64]:
        """Predict ``log(price)`` for a gold-shaped frame.

        Args:
            frame: Rows to score, straight from gold.

        Returns:
            Predicted ``log(price)``, one value per row.
        """
        matrix = _model_matrix(frame, self.spec)
        if self.model_kind == "lightgbm":
            prepared = _as_lightgbm(matrix, self.spec, self.levels)
        else:
            prepared = _as_catboost(matrix, self.spec)
        prediction = self.estimator.predict(prepared)  # type: ignore[attr-defined]
        return np.asarray(prediction, dtype=np.float64)


def fit_tree(
    train: pd.DataFrame,
    *,
    model_kind: TreeModel,
    vehicle_type: VehicleType,
    params: dict[str, Any] | None = None,
    seed: int = DEFAULT_SEED,
    detail_features: bool = False,
) -> FittedTree:
    """Fit one tree model on a training frame.

    Args:
        train: Training rows from gold.
        model_kind: ``lightgbm`` or ``catboost``.
        vehicle_type: Vertical being modeled.
        params: Hyperparameters; defaults to :data:`DEFAULT_PARAMS`.
        seed: Seed for the library's own randomness.
        detail_features: Also consume the listing-page columns; see :func:`tree_spec`.

    Returns:
        The fitted model, ready to score a gold-shaped frame.

    Raises:
        ValueError: If ``model_kind`` is not recognised.
    """
    if model_kind not in TREE_MODELS:
        msg = f"unknown tree model {model_kind!r}"
        raise ValueError(msg)

    spec = tree_spec(vehicle_type, detail_features=detail_features)
    matrix = _model_matrix(train, spec)
    target = train["log_price"].astype("float64")
    settings = dict(DEFAULT_PARAMS[model_kind] if params is None else params)

    if model_kind == "lightgbm":
        from lightgbm import LGBMRegressor

        levels = _category_levels(matrix, spec)
        estimator = LGBMRegressor(random_state=seed, verbose=-1, **settings)
        estimator.fit(_as_lightgbm(matrix, spec, levels), target)
        return FittedTree(model_kind, spec, estimator, levels)

    from catboost import CatBoostRegressor

    estimator = CatBoostRegressor(
        random_seed=seed,
        verbose=False,
        # CatBoost writes a catboost_info/ directory into the working directory unless
        # told not to, which would litter the repository on every fit.
        allow_writing_files=False,
        cat_features=list(spec.categorical),
        **settings,
    )
    estimator.fit(_as_catboost(matrix, spec), target)
    return FittedTree(model_kind, spec, estimator)
