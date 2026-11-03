"""What the service fixes on every request, in one place both sides read.

``/predict`` builds its row from what the form asks. Some model columns the form never asks
for, and the API fills them with a constant: no request can say "this is an official store"
or "this is a quad". Those constants are the **serving assumptions**, and they live here so
two things read the same mapping:

- :func:`autovalor.api.features.to_frame`, which writes them into every request's row;
- the evaluation of the published figures, which applies them to the holdout through
  :func:`as_served` before the band is calibrated and scored.

The second is the point. A band measured with values the API cannot send describes a
model nobody is served: that is how the published 80,0 % coverage on cars turned out to be
75,0 % for the rows the API actually scores, once ``city`` was forced to the constant the
API sent (``docs/STATUS.md``, Block 4). ``city`` has since left the model, so it is no
longer an assumption; a column the API cannot send is better dropped than assumed.

``tests/models/test_serving_parity.py`` fails if a model column is filled with a constant
that is not declared here, or if the gate is scored on a frame that did not go through
:func:`as_served`.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

import pandas as pd

SERVING_ASSUMPTIONS: Final[Mapping[str, str | bool]] = MappingProxyType(
    {
        "is_official_store": False,
        # Only read for motorcycles. A request cannot say "this is a quad" or "this is a
        # cargo trike", and guessing from the brand would be worse than the default: the
        # flags exist to let the model separate populations it saw while fitting, not to
        # be asked about.
        "is_quad": False,
        "is_cargo": False,
    }
)
"""Model columns ``/predict`` never takes from the request, with the value it sends."""


def as_served(frame: pd.DataFrame) -> pd.DataFrame:
    """Return ``frame`` with every serving assumption applied, as ``/predict`` would see it.

    Columns the frame does not carry are left out rather than added: a frame without
    ``is_quad`` is a car frame, and the car model never reads it.

    Args:
        frame: Gold-shaped rows.

    Returns:
        A copy whose assumed columns hold the value the API sends.
    """
    served = frame.copy()
    for column, value in SERVING_ASSUMPTIONS.items():
        if column in served.columns:
            served[column] = value
    return served
