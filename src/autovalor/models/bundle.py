"""Saving and loading the served model, without MLflow.

F2 trained models and logged them to MLflow, which is the right tool for comparing runs and
the wrong one for serving: MLflow pulls in a tracking server, a database and a third of the
dependency tree, and the F4 constraint is an API image that fits in Render's free 512 MB.
So the served model travels as **a few files, versioned in the repository**.

What that buys, and why it is the shape chosen over a download at start-up:

* **The image is hermetic.** Everything the API needs is in the build context, so a cold
  start cannot fail because an artifact store was unreachable, and nothing has to be paid
  for or authenticated against.
* **It is reproducible by inspection.** The bundle records the lake it came from — rows per
  vertical, the partition seed, the held-out metrics — so "which model answered this" is a
  question the repository can answer at any commit.
* **It costs nothing.** No object storage, no release assets, no token.

The format is deliberately boring: LightGBM's own text dump for each booster, and one JSON
for everything else. No pickle. A pickle of a fitted estimator binds the artifact to the
exact library version that wrote it and executes arbitrary code on load; a booster dump is
a stable text format that LightGBM reads back across versions.

The band's three quantile models are part of the bundle, not an optional extra. The product
promise for motorcycles is "estimate and range", so the range is as much the served model as
the point estimate is.
"""

import gzip
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lightgbm as lgb
import pandas as pd

from autovalor.models.dataset import VehicleType
from autovalor.models.quantiles import (
    QUANTILES,
    FittedInterval,
    Label,
    LabelPolicy,
)
from autovalor.models.spec import FeatureSpec
from autovalor.models.trees import FittedTree

logger = logging.getLogger("autovalor.models")

ARTIFACTS_DIR = Path(__file__).resolve().parents[3] / "artifacts" / "models"
"""Where bundles live. Inside the repository on purpose; see the module docstring."""

MANIFEST_NAME = "model.json"
POINT_MODEL_NAME = "point.txt.gz"

GZIP_LEVEL = 9
"""Boosters are stored gzipped. A LightGBM text dump is extremely repetitive -- thousands
of near-identical split records -- and compresses about six to one, which took this
project's four boosters per vertical from 47 MB to under 8. That matters twice: the files
live in the repository, and they are copied into an image with a 512 MB budget."""

BUNDLE_FORMAT = 1
"""Bumped when the on-disk shape changes in a way an older loader cannot read."""


class BundleError(RuntimeError):
    """Raised when a bundle is missing, unreadable or of an unknown format."""


@dataclass(frozen=True)
class ServedModel:
    """Everything the API needs to answer for one vertical.

    Attributes:
        vehicle_type: Vertical this bundle serves.
        version: Bundle version string, which is what ``/model-info`` reports.
        point: The point model, predicting ``log(price)``.
        interval: The calibrated P10-P90 band.
        label: Whether this vertical may show the bargain/fair/expensive label, carrying
            the held-out numbers the decision was made on.
        metrics: Held-out error of the point model, for ``/model-info``.
        lake: Which lake the bundle was trained on.
    """

    vehicle_type: VehicleType
    version: str
    point: FittedTree
    interval: FittedInterval
    label: LabelPolicy
    metrics: dict[str, float]
    lake: dict[str, Any]

    def predict_log_price(self, frame: pd.DataFrame) -> Any:
        """Predict ``log(price)`` for a gold-shaped frame."""
        return self.point.predict_log_price(frame)

    def predict_bounds(self, frame: pd.DataFrame) -> Any:
        """Predict the calibrated ``(lower, median, upper)`` band on the log scale."""
        return self.interval.predict_log_bounds(frame)

    def classify(self, asking_log_price: Any, lower: Any, upper: Any) -> list[Label] | None:
        """Label asking prices, or return ``None`` when this vertical withholds the label."""
        return self.label.labels(asking_log_price, lower, upper)


def _spec_to_json(spec: FeatureSpec) -> dict[str, list[str]]:
    return {
        "numeric": list(spec.numeric),
        "categorical": list(spec.categorical),
        "boolean": list(spec.boolean),
    }


def _spec_from_json(payload: dict[str, list[str]]) -> FeatureSpec:
    return FeatureSpec(
        numeric=tuple(payload["numeric"]),
        categorical=tuple(payload["categorical"]),
        boolean=tuple(payload["boolean"]),
    )


def _booster(tree: FittedTree) -> lgb.Booster:
    """Return the underlying booster of a fitted LightGBM model.

    Raises:
        BundleError: If the model is not LightGBM. CatBoost is not served; see ADR 0003.
    """
    if tree.model_kind != "lightgbm":
        msg = f"only lightgbm models can be bundled, got {tree.model_kind!r}"
        raise BundleError(msg)
    booster: lgb.Booster = tree.estimator.booster_  # type: ignore[attr-defined]
    return booster


def save_bundle(
    directory: Path,
    *,
    vehicle_type: VehicleType,
    version: str,
    point: FittedTree,
    interval: FittedInterval,
    label: LabelPolicy,
    metrics: dict[str, float],
    lake: dict[str, Any],
) -> Path:
    """Write one vertical's served model to ``directory``.

    Args:
        directory: Destination, created if missing. One directory per vertical.
        vehicle_type: Vertical being saved.
        version: Version string for ``/model-info``.
        point: The tuned point model.
        interval: The calibrated band.
        label: The label decision taken on the holdout.
        metrics: Held-out error of the point model.
        lake: Fingerprint of the lake it was trained on.

    Returns:
        The path of the manifest written.

    Raises:
        BundleError: If a model is not LightGBM.
    """
    directory.mkdir(parents=True, exist_ok=True)
    _write_booster(_booster(point), directory / POINT_MODEL_NAME)
    for quantile, model in interval.models.items():
        _write_booster(_booster(model), directory / _quantile_name(quantile))

    manifest = {
        "format": BUNDLE_FORMAT,
        "vehicle_type": vehicle_type,
        "version": version,
        "saved_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "spec": _spec_to_json(point.spec),
        # Frozen so a make seen only at predict time lands outside the categories and is
        # routed down the missing branch, exactly as it was at fit time.
        "levels": {column: [str(v) for v in index] for column, index in point.levels.items()},
        "interval": {
            "widening": interval.widening,
            "crossing_rate": interval.crossing_rate,
            "n_calibration": interval.n_calibration,
            "quantiles": list(QUANTILES),
        },
        "label": {
            "publishes_label": label.publishes_label,
            "coverage": label.coverage,
            "mean_relative_width": label.mean_relative_width,
            "n": label.n,
            "failures": list(label.failures),
            "precision_notice": label.precision_notice,
        },
        "metrics": metrics,
        "lake": lake,
    }
    path = directory / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("saved %s bundle %s to %s", vehicle_type, version, directory)
    return path


def _quantile_name(quantile: float) -> str:
    """File name for one quantile level. Rounded because 0.9 * 100 is 90.00000000000001."""
    return f"quantile_p{round(quantile * 100):02d}.txt.gz"


def _write_booster(booster: lgb.Booster, path: Path) -> None:
    """Write a booster as gzipped text."""
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=GZIP_LEVEL) as handle:
        handle.write(booster.model_to_string())


def load_bundle(directory: Path) -> ServedModel:
    """Read one vertical's served model back.

    Args:
        directory: Directory a previous :func:`save_bundle` wrote.

    Returns:
        The served model, ready to predict.

    Raises:
        BundleError: If the directory has no manifest, or the manifest is of a format this
            code does not know how to read.
    """
    path = directory / MANIFEST_NAME
    if not path.exists():
        msg = f"no model bundle at {directory}; run `make export-model` to build one"
        raise BundleError(msg)

    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("format") != BUNDLE_FORMAT:
        msg = (
            f"{path} is bundle format {manifest.get('format')!r}, this build reads {BUNDLE_FORMAT}"
        )
        raise BundleError(msg)

    spec = _spec_from_json(manifest["spec"])
    levels = {column: pd.Index(values) for column, values in manifest["levels"].items()}

    point = _load_tree(directory / POINT_MODEL_NAME, spec, levels)
    interval = FittedInterval(
        vehicle_type=manifest["vehicle_type"],
        models={
            quantile: _load_tree(directory / _quantile_name(quantile), spec, levels)
            for quantile in manifest["interval"]["quantiles"]
        },
        widening=float(manifest["interval"]["widening"]),
        crossing_rate=float(manifest["interval"]["crossing_rate"]),
        n_calibration=int(manifest["interval"]["n_calibration"]),
    )
    label = LabelPolicy(
        vehicle_type=manifest["vehicle_type"],
        coverage=float(manifest["label"]["coverage"]),
        mean_relative_width=float(manifest["label"]["mean_relative_width"]),
        n=int(manifest["label"]["n"]),
        failures=tuple(manifest["label"]["failures"]),
    )
    return ServedModel(
        vehicle_type=manifest["vehicle_type"],
        version=manifest["version"],
        point=point,
        interval=interval,
        label=label,
        metrics=manifest["metrics"],
        lake=manifest["lake"],
    )


def _load_tree(path: Path, spec: FeatureSpec, levels: dict[str, pd.Index]) -> FittedTree:
    """Rebuild a :class:`FittedTree` around a saved booster.

    The booster goes in as the estimator directly, rather than being stuffed back into an
    ``LGBMRegressor``. :meth:`FittedTree.predict_log_price` calls ``estimator.predict``
    and nothing else, and ``Booster`` has exactly that method; rebuilding the scikit-learn
    wrapper would mean assigning half a dozen private attributes that are not part of
    LightGBM's API and would break on an upgrade.

    Prediction therefore goes through the same path at serve time as at fit time, including
    :meth:`FittedTree.design_matrix`, which is what freezes the category codes.
    """
    if not path.exists():
        msg = f"bundle is missing {path.name}"
        raise BundleError(msg)
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        booster = lgb.Booster(model_str=handle.read())
    return FittedTree(model_kind="lightgbm", spec=spec, estimator=booster, levels=levels)


def load_served_models(directory: Path = ARTIFACTS_DIR) -> dict[VehicleType, ServedModel]:
    """Load every bundle under ``directory``, keyed by vertical.

    Args:
        directory: Root holding one subdirectory per vertical.

    Returns:
        The served models found. An empty mapping when the root does not exist, so a
        development checkout without artifacts starts and reports itself unready rather
        than failing to import.
    """
    if not directory.exists():
        logger.warning("no model artifacts at %s; the API will report itself unready", directory)
        return {}

    models: dict[VehicleType, ServedModel] = {}
    for child in sorted(directory.iterdir()):
        if (child / MANIFEST_NAME).exists():
            model = load_bundle(child)
            models[model.vehicle_type] = model
    logger.info("loaded %d served model(s) from %s", len(models), directory)
    return models
