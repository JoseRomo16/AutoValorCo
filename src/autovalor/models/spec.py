"""The feature specification — which columns a model consumes, grouped by how.

Its own module because of where it is *used*, not because of what it is. ``FeatureSpec``
is a frozen dataclass of strings, and it was born in :mod:`autovalor.models.hedonic`, which
imports scikit-learn. The served model needs the spec to rebuild its design matrix, and the
API image does not install scikit-learn: importing the spec from there would drag a hundred
megabytes of estimator library into a container that only ever calls ``Booster.predict``.

So the type lives here, where nothing heavier than the standard library is imported, and
``hedonic`` re-exports it so existing call sites keep working.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureSpec:
    """Columns a feature set feeds to a model.

    Attributes:
        numeric: Columns used as-is, after median imputation.
        categorical: Columns one-hot encoded by the baseline, passed raw to the trees.
        boolean: Columns cast to 0/1.
    """

    numeric: tuple[str, ...]
    categorical: tuple[str, ...]
    boolean: tuple[str, ...]

    @property
    def columns(self) -> tuple[str, ...]:
        """All input columns, in a stable order."""
        return self.numeric + self.categorical + self.boolean
