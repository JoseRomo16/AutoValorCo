"""How a request from a department the model never saw gets answered.

The capture sweeps six locations and gold holds ten departments for cars, so somebody in
Nariño is a real caller the model has no level for. What happened until now, verified in the
catalogue the bundle carries: **there is no "unknown" department level at all** — ten levels
for cars, nine for motorcycles, none of them a catch-all. So the request went down
LightGBM's default branch, which is wherever the tree's missing-value path happens to lead.
Measured on the deployed service, "Nariño", "xyz", "Otro" and a lower-cased "antioquia" all
returned exactly the same estimate as Antioquia: not a considered answer about an unknown
region, just an arbitrary one.

It used to *look* harmless only because the model also read `city`, which absorbed the
regional effect: the department moved the estimate by at most ~0,2 %, while `/market`
publishes regional differences up to +27 % for motorcycles in Antioquia. Block 4 dropped
`city`, so the department now carries that effect, and the default branch would distort
the answer by as much.

**The answer is the weighted average over the departments the model does know**, in log
space, weighted by how many training listings each one contributed. Not an unweighted mean:
Cauca has one listing and Bogotá has 1.251, and treating them as equal would let a region
the model barely saw drag the national average around.

Averaging in log space rather than in pesos is not a detail. The model predicts
``log(price)``, so a log-space mean is the geometric mean of the prices — which is the
average that makes sense for a quantity that varies multiplicatively, and the only one under
which the explanation still reconciles exactly (see :func:`average_contributions`).

Everything here scores **one frame per model**, not a loop: the departments become rows, so
a ten-department average costs the same four LightGBM calls as a single prediction.
"""

from collections.abc import Sequence
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from autovalor.api.labels import Localized
from autovalor.models.bundle import ServedModel
from autovalor.models.catalog import VehicleCatalog

DEPARTMENT_COLUMN = "department"

AVERAGE_REGION = Localized(
    es="promedio de departamentos",
    en="average of departments",
)
"""What ``/explain`` shows for the region when the department is not covered.

The factor is still reported rather than hidden: it carries a real contribution — the
weighted average of the contribution across every known department — and dropping it would
leave the five factors not summing to the estimate.
"""


def weights(catalog: VehicleCatalog) -> tuple[tuple[str, float], ...]:
    """Return each known department with its share of the training listings.

    The counts are the ones ``/catalog`` publishes, so the average a caller gets and the
    list a caller is shown are derived from the same numbers.

    Returns:
        ``(name, weight)`` pairs whose weights sum to 1, or empty when the catalogue has
        no departments at all.
    """
    listings = [(entry.name, float(entry.listings)) for entry in catalog.departments]
    total = sum(count for _, count in listings)
    if not listings or total <= 0:
        return ()
    return tuple((name, count / total) for name, count in listings)


def spread(frame: pd.DataFrame, names: Sequence[str]) -> pd.DataFrame:
    """Repeat a one-row frame once per department, varying only the department.

    Args:
        frame: The single scored row.
        names: Department levels to spread over.

    Returns:
        A frame of ``len(names)`` rows, identical but for the department column.
    """
    spread_frame = pd.concat([frame] * len(names), ignore_index=True)
    spread_frame[DEPARTMENT_COLUMN] = list(names)
    return spread_frame


def _average(values: npt.NDArray[np.float64], shares: npt.NDArray[np.float64]) -> Any:
    """Weighted mean along the rows."""
    return np.average(values, axis=0, weights=shares)


def average_band(
    model: ServedModel, frame: pd.DataFrame, pairs: Sequence[tuple[str, float]]
) -> npt.NDArray[np.float64]:
    """Return the published band averaged over the known departments, in log space.

    The band's bounds are averaged alongside the estimate, so the range describes the same
    hypothetical vehicle the estimate does. Ordering survives: every row comes out of
    :meth:`ServedModel.predict_published_band` already ordered, and a weighted mean of
    ordered triples is ordered.

    Args:
        model: The served bundle.
        frame: The single scored row.
        pairs: ``(department, weight)`` from :func:`weights`.

    Returns:
        A ``(3,)`` array: lower, estimate, upper, as ``log(price)``.
    """
    names = [name for name, _ in pairs]
    shares = np.array([share for _, share in pairs], dtype=np.float64)
    bounds = np.asarray(model.predict_published_band(spread(frame, names)), dtype=np.float64)
    averaged: npt.NDArray[np.float64] = _average(bounds, shares)
    return averaged


def average_contributions(
    model: ServedModel, frame: pd.DataFrame, pairs: Sequence[tuple[str, float]]
) -> tuple[pd.Series, float, float]:
    """Return the SHAP contributions of the averaged prediction, and that prediction.

    Exact rather than approximate, and the reason is worth keeping: for every row the model
    satisfies ``prediction = base + sum(phi)``, and ``base`` does not depend on the row. So
    the weighted mean of the predictions equals ``base`` plus the weighted mean of the
    contributions, feature by feature. Averaging ``phi`` therefore explains the averaged
    estimate exactly, and ``base x factors = estimate`` still holds — which is the property
    that makes an explanation checkable rather than decorative.

    Args:
        model: The served bundle.
        frame: The single scored row.
        pairs: ``(department, weight)`` from :func:`weights`.

    Returns:
        The averaged contributions as one row, the base ``log(price)``, and the averaged
        predicted ``log(price)``.
    """
    # Imported here: shap_contributions pulls in the explain module, and /predict must not
    # pay for it on a path that never explains anything.
    from autovalor.models.explain import shap_contributions

    names = [name for name, _ in pairs]
    shares = np.array([share for _, share in pairs], dtype=np.float64)
    spread_frame = spread(frame, names)

    phi, base = shap_contributions(model.point, spread_frame)
    averaged = pd.Series(
        _average(np.asarray(phi.to_numpy(), dtype=np.float64), shares), index=phi.columns
    )
    predicted = float(
        _average(
            np.asarray(model.predict_log_price(spread_frame), dtype=np.float64).reshape(-1, 1),
            shares,
        )[0]
    )
    return averaged, base, predicted
