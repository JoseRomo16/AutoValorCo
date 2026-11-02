"""Everything Block 4 measures about the served band, on any bundle, the same way.

The point is comparability: the baseline (the published bundle, before ``city`` is dropped)
and the retrained bundle are measured by this one function on the same holdout, so the
before and after in ADR 0006 differ only in the model.

Each vertical is scored under two conditions:

- ``real``: the holdout as gold has it. This is how the published figures were measured
  until Block 4.
- ``served``: the holdout passed through :func:`autovalor.models.serving.as_served`, i.e.
  with every column ``/predict`` fixes set to the value it sends. **This is the one a user
  meets.** Under the published bundle it forces ``city`` to ``"Desconocida"``, a level that
  does not occur once in the holdout.

Per condition: error and bias of the point model, coverage and width of the band (both the
gate's calibrated band and the published one, which is widened to contain the estimate),
width by price quartile, where the estimate sits inside the published band, how far the
point model is from the band's own P50, the P50's error — measured here for the first
time — and how many rows the published band had to widen.

Per vertical, on the served condition: the mean SHAP pull of ``city`` (when the model still
has it), the effect of each department on the same vehicles set beside the regional effect
``/market`` publishes, and the band's coverage under "Otro departamento" — each row averaged
over the *other* known departments, its own excluded and the weights renormalised, as
specified in ``docs/STATUS.md``.

Run with ``python -m autovalor.models.band_diagnostics --output docs/reports/<name>.json``.
Not ``docs/results/``: ``/market`` serves every JSON there as a table.
"""

import argparse
import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from autovalor.models.bundle import ServedModel, load_served_models
from autovalor.models.dataset import DEFAULT_SEED, VEHICLE_TYPES, VehicleType, load_split
from autovalor.models.quantiles import LABEL_GATE
from autovalor.models.serving import as_served

logger = logging.getLogger(__name__)

TARGET = "log_price"
DEPARTMENT_COLUMN = "department"
CITY_COLUMN = "city"
REFERENCE_DEPARTMENT = "Bogotá D.C."
"""The reference ``/market`` publishes regional effects against."""

EDGE_LOW = 0.2
EDGE_HIGH = 0.8
"""Positions inside the band below/above which the estimate counts as near an edge."""

_EPS = 1e-9
RESULTS_DIR = Path("docs/results")


# --- the band -------------------------------------------------------------------------


def position_in_band(
    estimate: npt.NDArray[np.float64],
    lower: npt.NDArray[np.float64],
    upper: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Where the estimate sits inside ``[lower, upper]``, all in log: 0 at P10, 1 at P90.

    A zero-width band has no inside; its rows come out as 0.5 rather than dividing by zero.
    """
    width = upper - lower
    safe = np.where(width > _EPS, width, 1.0)
    position: npt.NDArray[np.float64] = np.where(width > _EPS, (estimate - lower) / safe, 0.5)
    return position


def _coverage(actual: npt.NDArray[np.float64], lower: Any, upper: Any) -> float:
    return float(np.mean((actual >= lower) & (actual <= upper)))


def _relative_width(lower: Any, estimate: Any, upper: Any) -> npt.NDArray[np.float64]:
    width: npt.NDArray[np.float64] = (np.exp(upper) - np.exp(lower)) / np.exp(estimate)
    return width


def _ape(predicted: Any, actual: Any) -> npt.NDArray[np.float64]:
    ape: npt.NDArray[np.float64] = np.abs(np.exp(predicted - actual) - 1.0)
    return ape


def width_by_quartile(
    lower: npt.NDArray[np.float64],
    estimate: npt.NDArray[np.float64],
    upper: npt.NDArray[np.float64],
) -> list[dict[str, float]]:
    """Band width by quartile of the **estimate**, never of the asking price.

    Cutting on the asking price would condition on the dependent variable — the bug the
    price segments of F3 had. The estimate is what the user is shown, so it is also the
    natural axis for "how wide is the band for a cheap vehicle".
    """
    edges = np.quantile(estimate, [0.0, 0.25, 0.5, 0.75, 1.0])
    bucket = np.clip(np.searchsorted(edges, estimate, side="right") - 1, 0, 3)
    rows = []
    for quartile in range(4):
        mask = bucket == quartile
        if not mask.any():
            continue
        rows.append(
            {
                "quartile": float(quartile + 1),
                "estimate_cop_min": float(np.exp(estimate[mask].min())),
                "estimate_cop_max": float(np.exp(estimate[mask].max())),
                "mean_relative_width": float(
                    _relative_width(lower[mask], estimate[mask], upper[mask]).mean()
                ),
                "median_p90_over_p10": float(np.median(np.exp(upper[mask] - lower[mask]))),
                "n": float(mask.sum()),
            }
        )
    return rows


def condition_metrics(model: ServedModel, frame: pd.DataFrame) -> dict[str, Any]:
    """Every band and error figure for one scored frame.

    Args:
        model: The served bundle.
        frame: Holdout rows, gold-shaped, carrying ``log_price``.

    Returns:
        A JSON-ready mapping; see the module docstring for what each figure means.
    """
    actual = frame[TARGET].to_numpy(dtype=np.float64)
    calibrated = np.asarray(model.predict_bounds(frame), dtype=np.float64)
    published = np.asarray(model.predict_published_band(frame), dtype=np.float64)
    lower, estimate, upper = published[:, 0], published[:, 1], published[:, 2]
    p50 = calibrated[:, 1]

    position = position_in_band(estimate, lower, upper)
    below = estimate < calibrated[:, 0]
    above = estimate > calibrated[:, 2]
    gap = estimate - p50

    return {
        "mape": float(_ape(estimate, actual).mean()),
        "median_ape": float(np.median(_ape(estimate, actual))),
        "bias_log": float(np.mean(estimate - actual)),
        "p50_mape": float(_ape(p50, actual).mean()),
        "point_minus_p50_log": {
            "mean": float(gap.mean()),
            "median_abs": float(np.median(np.abs(gap))),
        },
        "coverage_calibrated": _coverage(actual, calibrated[:, 0], calibrated[:, 2]),
        "mean_relative_width_calibrated": float(
            _relative_width(calibrated[:, 0], estimate, calibrated[:, 2]).mean()
        ),
        "coverage_published": _coverage(actual, lower, upper),
        "mean_relative_width_published": float(_relative_width(lower, estimate, upper).mean()),
        "position": {
            "median": float(np.median(position)),
            "share_below_0_2": float(np.mean(position < EDGE_LOW)),
            "share_above_0_8": float(np.mean(position > EDGE_HIGH)),
            "share_at_edge": float(np.mean(below | above)),
            "deciles": [float(v) for v in np.quantile(position, np.linspace(0, 1, 11))],
        },
        "widened": {
            "below_p10": float(below.sum()),
            "above_p90": float(above.sum()),
            "share": float(np.mean(below | above)),
        },
        "width_by_estimate_quartile": width_by_quartile(lower, estimate, upper),
    }


# --- geography ------------------------------------------------------------------------


def department_pairs(model: ServedModel) -> list[tuple[str, float]]:
    """``(department, training listings)`` from the bundle's catalogue."""
    if model.catalog is None or not model.catalog.departments:
        msg = f"the {model.vehicle_type} bundle has no department catalogue"
        raise ValueError(msg)
    return [(entry.name, float(entry.listings)) for entry in model.catalog.departments]


def spread_departments(frame: pd.DataFrame, names: Sequence[str]) -> pd.DataFrame:
    """Repeat every row once per department: row-major, ``len(frame) x len(names)`` rows."""
    spread = frame.loc[frame.index.repeat(len(names))].reset_index(drop=True)
    spread[DEPARTMENT_COLUMN] = list(names) * len(frame)
    return spread


def exclusion_weights(
    own: Sequence[str], pairs: Sequence[tuple[str, float]]
) -> npt.NDArray[np.float64]:
    """Per-row weights over the known departments, with the row's own one excluded.

    Args:
        own: Each row's real department.
        pairs: ``(department, training listings)`` for every department the model knows.

    Returns:
        An ``(n_rows, n_departments)`` array whose rows sum to one. A row whose department
        is not among ``pairs`` keeps every department: there is nothing to exclude.

    Raises:
        ValueError: If excluding a row's department leaves no weight.
    """
    names = np.array([name for name, _ in pairs], dtype=object)
    counts = np.array([count for _, count in pairs], dtype=np.float64)
    matrix = np.tile(counts, (len(own), 1))
    matrix[np.asarray(own, dtype=object)[:, None] == names[None, :]] = 0.0
    totals = matrix.sum(axis=1, keepdims=True)
    if np.any(totals <= 0):
        msg = "excluding the row's own department left no department to average over"
        raise ValueError(msg)
    weights: npt.NDArray[np.float64] = matrix / totals
    return weights


def uncovered_bands(
    model: ServedModel, frame: pd.DataFrame, pairs: Sequence[tuple[str, float]]
) -> npt.NDArray[np.float64]:
    """Each row's published band averaged, in log, over the *other* known departments."""
    names = [name for name, _ in pairs]
    bands = np.asarray(
        model.predict_published_band(spread_departments(frame, names)), dtype=np.float64
    ).reshape(len(frame), len(names), 3)
    weights = exclusion_weights(frame[DEPARTMENT_COLUMN].astype(str).tolist(), pairs)
    averaged: npt.NDArray[np.float64] = np.einsum("rd,rdk->rk", weights, bands)
    return averaged


def uncovered_coverage(
    model: ServedModel, frame: pd.DataFrame, pairs: Sequence[tuple[str, float]]
) -> dict[str, Any]:
    """Coverage of the "Otro departamento" band on the holdout, against the gate window."""
    bands = uncovered_bands(model, frame, pairs)
    coverage = _coverage(frame[TARGET].to_numpy(dtype=np.float64), bands[:, 0], bands[:, 2])
    return {
        "coverage": coverage,
        "mean_relative_width": float(_relative_width(bands[:, 0], bands[:, 1], bands[:, 2]).mean()),
        "within_gate": LABEL_GATE.min_coverage <= coverage <= LABEL_GATE.max_coverage,
    }


def department_effects(
    model: ServedModel,
    frame: pd.DataFrame,
    pairs: Sequence[tuple[str, float]],
    market: Sequence[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    """What each department does to the estimate of the same vehicles, beside ``/market``.

    For every holdout row the point model is scored once per department; the effect of a
    department is the mean of ``exp(pred_d - pred_ref) - 1`` over rows, against
    :data:`REFERENCE_DEPARTMENT` — the same reference the hedonic regional effect uses.
    """
    names = [name for name, _ in pairs]
    if REFERENCE_DEPARTMENT not in names:
        return []
    predicted = np.asarray(
        model.predict_log_price(spread_departments(frame, names)), dtype=np.float64
    ).reshape(len(frame), len(names))
    reference = predicted[:, names.index(REFERENCE_DEPARTMENT)][:, None]
    effect = np.mean(np.expm1(predicted - reference), axis=0) * 100.0
    published = {row["department"]: row for row in market}
    rows = []
    for (name, listings), model_pct in zip(pairs, effect, strict=True):
        hedonic = published.get(name)
        rows.append(
            {
                "department": name,
                "listings": listings,
                "model_pct": float(model_pct),
                "market_pct": None if hedonic is None else hedonic["pct_change"],
                "market_significant": None if hedonic is None else hedonic["significant"],
            }
        )
    return rows


def city_shap(model: ServedModel, frame: pd.DataFrame) -> dict[str, float] | None:
    """Mean SHAP pull of ``city`` on a frame, or ``None`` when the model has no city."""
    if CITY_COLUMN not in model.point.spec.categorical:
        return None
    # Imported here so the module loads without the explain path when city is gone.
    from autovalor.models.explain import shap_contributions

    phi, _ = shap_contributions(model.point, frame)
    city = phi[CITY_COLUMN].to_numpy(dtype=np.float64)
    total = np.abs(phi.to_numpy(dtype=np.float64)).sum(axis=1)
    return {
        "mean_log": float(city.mean()),
        "mean_abs_log": float(np.abs(city).mean()),
        "share_of_abs_pull": float(np.abs(city).sum() / total.sum()),
    }


# --- one vertical ---------------------------------------------------------------------


def diagnose(
    model: ServedModel, test: pd.DataFrame, market: Sequence[dict[str, Any]] = ()
) -> dict[str, Any]:
    """Measure one vertical; see the module docstring.

    Args:
        model: The served bundle.
        test: The holdout, gold-shaped, carrying ``log_price``.
        market: The ``/market`` regional effect rows for this vertical.

    Returns:
        A JSON-ready mapping.
    """
    real = test.reset_index(drop=True)
    served = as_served(real)
    pairs = department_pairs(model)
    return {
        "vehicle_type": model.vehicle_type,
        "version": model.version,
        "n": len(real),
        "uses_city": CITY_COLUMN in model.point.spec.categorical,
        "published": {
            "mape": model.metrics.get("mape"),
            "interval_coverage": model.metrics.get("interval_coverage"),
            "interval_mean_relative_width": model.metrics.get("interval_mean_relative_width"),
        },
        "conditions": {
            "real": condition_metrics(model, real),
            "served": condition_metrics(model, served),
        },
        "city_shap": {
            "real": city_shap(model, real),
            "served": city_shap(model, served),
        },
        "department_effect_served": department_effects(model, served, pairs, market),
        "uncovered_department": {
            "real": uncovered_coverage(model, real, pairs),
            "served": uncovered_coverage(model, served, pairs),
        },
        "gate": {
            "min_coverage": LABEL_GATE.min_coverage,
            "max_coverage": LABEL_GATE.max_coverage,
            "max_relative_width": LABEL_GATE.max_relative_width,
        },
    }


def _market_rows(vehicle_type: VehicleType, results_dir: Path) -> list[dict[str, Any]]:
    path = results_dir / "regional_effect.json"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in rows if row.get("vehicle_type") == vehicle_type]


def build_parser() -> argparse.ArgumentParser:
    """Command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vehicle-type", choices=VEHICLE_TYPES, action="append")
    parser.add_argument("--duckdb", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=None, help="Write the JSON here.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Diagnose every requested vertical against the served bundles."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    models = load_served_models()
    results = []
    for vehicle_type in args.vehicle_type or VEHICLE_TYPES:
        model = models[vehicle_type]
        dataset = load_split(vehicle_type, seed=args.seed, duckdb_path=args.duckdb)
        recorded = model.lake.get("n_test")
        if recorded is not None and int(recorded) != dataset.n_test:
            logger.warning(
                "%s holdout has %d rows, the bundle recorded %s: the lake has moved",
                vehicle_type,
                dataset.n_test,
                recorded,
            )
        results.append(diagnose(model, dataset.test, _market_rows(vehicle_type, RESULTS_DIR)))
    payload = json.dumps(results, indent=2, ensure_ascii=False)
    if args.output is not None:
        args.output.write_text(payload + "\n", encoding="utf-8")
        logger.info("wrote %s", args.output)
    else:
        print(payload)  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
