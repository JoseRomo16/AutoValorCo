"""Human names and formatted values for the features ``/explain`` returns.

``vehicle_age_years`` and ``km_per_year`` are column names, and an explanation card that
shows them is showing the reader the inside of the model. The technical name still travels
in every factor — a client plotting or logging attributions needs a stable key, and a
translated string is not one — but next to it goes the name a person reads and the value in
the unit it is measured in.

Both languages are built here rather than in the frontend, for one reason: the formatting
depends on what the feature *means*. ``1600`` is "1.600 cc", ``8`` is "8 años" and ``False``
is "No", and a client that only sees a number and a column name has to re-derive that
mapping — which is how a frontend ends up printing "8 km". Spanish is the product's default
language, so Spanish is the one the API is sure to get right.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np

from autovalor.features.naming import display_model

SPANISH = "es"
ENGLISH = "en"

UNKNOWN_LEVEL = "Desconocida"
"""The level the lake uses for a make, city or department it could not parse. It reaches
this module as data, so it is translated rather than shown verbatim in English."""


@dataclass(frozen=True)
class Localized:
    """One string in both published languages."""

    es: str
    en: str

    def to_json(self) -> dict[str, str]:
        """Return the JSON form."""
        return {SPANISH: self.es, ENGLISH: self.en}


FEATURE_LABELS: dict[str, Localized] = {
    "brand": Localized(es="Marca", en="Make"),
    "model": Localized(es="Modelo", en="Model"),
    "department": Localized(es="Departamento", en="Department"),
    "city": Localized(es="Ciudad", en="City"),
    "vehicle_age_years": Localized(es="Edad del vehículo", en="Vehicle age"),
    "mileage_km": Localized(es="Kilometraje", en="Mileage"),
    "engine_cc": Localized(es="Cilindrada", en="Engine displacement"),
    "km_per_year": Localized(es="Kilómetros por año", en="Kilometres per year"),
    "is_official_store": Localized(es="Tienda oficial", en="Official store"),
    "is_quad": Localized(es="Cuatrimoto", en="Quad bike"),
    "is_cargo": Localized(es="Motocarro", en="Cargo three-wheeler"),
}
"""Every feature the served specification carries. Pinned by a test against the bundle's
own spec, so adding a feature to the model without naming it here fails the suite instead
of shipping a column name into the product."""

MISSING = Localized(es="sin dato", en="not provided")
"""What an unsupplied optional feature reads as. The model treats a missing engine as its
own signal, so "sin dato" is the honest rendering and "0 cc" would be a fabricated value."""


def feature_label(feature: str) -> Localized:
    """Return the human name of a feature.

    Args:
        feature: Technical column name.

    Returns:
        The name in both languages, falling back to the column name itself for a feature
        nobody has named yet — an unlabelled factor is still a true factor, and dropping it
        would silently shorten the explanation.
    """
    return FEATURE_LABELS.get(feature, Localized(es=feature, en=feature))


def _group(value: float, separator: str) -> str:
    """Format an integer-valued number with thousands separators."""
    return f"{round(value):,}".replace(",", separator)


def _localized_level(text: str) -> Localized:
    """Render a categorical level, translating only the lake's unknown bucket."""
    if text == UNKNOWN_LEVEL:
        return Localized(es=UNKNOWN_LEVEL, en="Unknown")
    return Localized(es=text, en=text)


def format_value(feature: str, value: Any) -> Localized:
    """Render a feature's value for display, in both languages.

    Args:
        feature: Technical column name, which decides the unit.
        value: The vehicle's value, straight from the scored frame.

    Returns:
        The formatted value, with its unit. An unsupplied feature renders as
        :data:`MISSING` rather than as nothing: it still carries a SHAP contribution, so
        the card has to say *why* — the model priced the absence.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return MISSING

    # np.bool_ as well as bool: the scored frame comes back from pandas, where a boolean
    # column is np.bool_, and treated as a number it would print "1".
    if isinstance(value, bool | np.bool_):
        yes = bool(value)
        return Localized(es="Sí" if yes else "No", en="Yes" if yes else "No")

    if feature == "vehicle_age_years":
        years = round(float(value))
        return Localized(
            es=f"{years} año" if years == 1 else f"{years} años",
            en=f"{years} year" if years == 1 else f"{years} years",
        )
    if feature == "mileage_km":
        return Localized(es=f"{_group(float(value), '.')} km", en=f"{_group(float(value), ',')} km")
    if feature == "engine_cc":
        return Localized(es=f"{_group(float(value), '.')} cc", en=f"{_group(float(value), ',')} cc")
    if feature == "km_per_year":
        return Localized(
            es=f"{_group(float(value), '.')} km/año", en=f"{_group(float(value), ',')} km/yr"
        )

    if isinstance(value, float) and value.is_integer():
        return Localized(es=str(int(value)), en=str(int(value)))
    if isinstance(value, float | int):
        return Localized(es=str(value), en=str(value))

    text = str(value)
    # Model tokens are mined from titles in lower case ("corolla"); makes and departments
    # already carry their own capitalisation and must not be touched — "BMW" is not "Bmw".
    # The same spelling rule the catalogue uses, so the explanation card and the dropdown
    # never disagree about a model's name. `str.title` gave "Cx-30" and "Mt-09".
    shown = display_model(text) if feature == "model" else text
    return _localized_level(shown)
