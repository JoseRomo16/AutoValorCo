"""``make readme`` — regenerate the figures the README publishes.

The README quoted its numbers as prose, and prose does not get recomputed. After the
October retrain nine of its figures were wrong at once: the error rates, the lake sizes and
the sentence about which of the two label criteria motorcycles fail. None of them was a
typo; each was true when written.

So the figures live in a generated block between markers, and the prose around it keeps the
interpretation without restating a number. The block is rendered from the same two sources
the site reads at build time — each vertical's ``model.json`` and ``docs/results/`` — which
is what makes "the README, the docs and the site agree" checkable instead of a habit.

A test regenerates the block and compares, so a retrain that is not followed by
``make readme`` fails the suite rather than shipping a stale README.

Examples:
    uv run python -m autovalor.readme
    uv run python -m autovalor.readme --check
"""

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from autovalor.models.bundle import ARTIFACTS_DIR, MANIFEST_NAME
from autovalor.models.dataset import VEHICLE_TYPES, VehicleType

logger = logging.getLogger("autovalor.readme")

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "docs" / "results"
README_PATH = REPO_ROOT / "README.md"

LANGUAGES = ("es", "en")
"""The README is bilingual, so there is one block per language rather than one shared
table. A single block would force one language's wording on the other section."""


def start_marker(lang: str) -> str:
    """Return the opening marker for a language's block."""
    return f"<!-- results:start:{lang} -->"


def end_marker(lang: str) -> str:
    """Return the closing marker for a language's block."""
    return f"<!-- results:end:{lang} -->"


class ReadmeError(RuntimeError):
    """Raised when the README cannot be regenerated from the files on disk."""


def _read_json(path: Path) -> Any:
    """Read a published JSON file, naming the command that writes it when it is missing."""
    if not path.exists():
        hint = "make export-model" if path.name == MANIFEST_NAME else "make results"
        msg = f"{path} does not exist; run {hint} first"
        raise ReadmeError(msg)
    return json.loads(path.read_text(encoding="utf-8"))


_ES_SEPARATORS = str.maketrans({",": ".", ".": ","})
"""Swaps the thousands and decimal separators in one pass. A sequence of `str.replace`
calls cannot do this: the first replacement's output is the second's input."""


def _decimal(value: float, lang: str, digits: int = 1) -> str:
    """Format a number in the language's own convention.

    Spanish writes 10,3 and English 10.3. Getting this wrong is the kind of detail that
    makes a bilingual README read as machine-translated.
    """
    text = f"{value:,.{digits}f}"
    if lang == "es":
        text = text.translate(_ES_SEPARATORS)
    # A real minus sign, not a hyphen: the rest of the prose in this README uses one, and
    # at small sizes a hyphen in front of a figure reads as a dash.
    return text.replace("-", "\N{MINUS SIGN}", 1) if text.startswith("-") else text


def _percent(fraction: float, lang: str, digits: int = 1) -> str:
    """Format a fraction as a percentage."""
    return f"{_decimal(fraction * 100, lang, digits)} %"


def _points(value: float, lang: str, digits: int = 1) -> str:
    """Format a difference between two percentages, which is measured in points."""
    unit = "puntos" if lang == "es" else "points"
    return f"{_decimal(value, lang, digits)} {unit}"


def _integer(value: float, lang: str) -> str:
    """Format a count with the language's thousands separator."""
    return _decimal(value, lang, 0)


def _cop(value: float, lang: str) -> str:
    """Format a peso amount, rounded to the nearest thousand."""
    rounded = round(value / 1_000) * 1_000
    return f"$ {_integer(rounded, lang)}" if lang == "es" else f"COP {_integer(rounded, lang)}"


def _millions(value: float, lang: str) -> str:
    """Format a peso amount in millions, which is how prices are spoken here."""
    millions = value / 1_000_000
    digits = 0 if abs(millions) >= 10 else 1
    amount = _decimal(millions, lang, digits)
    return f"$ {amount} millones" if lang == "es" else f"COP {amount}M"


def load_models(directory: Path = ARTIFACTS_DIR) -> dict[VehicleType, dict[str, Any]]:
    """Read each vertical's bundle manifest.

    Args:
        directory: Root holding one subdirectory per vertical.

    Returns:
        The manifests, keyed by vehicle type.

    Raises:
        ReadmeError: If a manifest is missing.
    """
    return {
        vehicle_type: _read_json(directory / vehicle_type / MANIFEST_NAME)
        for vehicle_type in VEHICLE_TYPES
    }


def load_results(directory: Path = RESULTS_DIR) -> dict[str, Any]:
    """Read the published result tables and their manifest.

    Args:
        directory: Directory ``make results`` writes.

    Returns:
        Every table by stem, plus ``manifest``.

    Raises:
        ReadmeError: If the manifest is missing.
    """
    manifest = _read_json(directory / "manifest.json")
    tables = {
        path.stem: _read_json(path)
        for path in sorted(directory.glob("*.json"))
        if path.stem != "manifest"
    }
    return {"manifest": manifest, **tables}


def _extreme(
    rows: Sequence[dict[str, Any]],
    *,
    vehicle_type: str,
    key: str,
    largest: bool,
    where: str | None = None,
) -> dict[str, Any]:
    """Return the row of one vertical with the largest or smallest value of ``key``.

    Pulled out because every economic figure in the block is "the brand that depreciates
    most", "the department that pays least" or similar, and each one hand-rolled is one
    more place a filter can quietly disagree with the sentence next to it.

    Args:
        rows: A published result table.
        vehicle_type: Vertical to filter to.
        key: Numeric column to rank by.
        largest: Whether to take the maximum rather than the minimum.
        where: Optional column that must be truthy, e.g. ``significant``.

    Returns:
        The winning row.

    Raises:
        ReadmeError: If no row survives the filter, which means the table changed shape.
    """
    candidates = [
        row
        for row in rows
        if row.get("vehicle_type") == vehicle_type and (where is None or row.get(where))
    ]
    if not candidates:
        msg = f"no {vehicle_type} rows with a {key!r}" + (f" and {where!r}" if where else "")
        raise ReadmeError(msg)
    return (
        max(candidates, key=lambda row: float(row[key]))
        if largest
        else min(candidates, key=lambda row: float(row[key]))
    )


def _label_state(model: dict[str, Any], lang: str) -> str:
    """Say whether a vertical publishes the bargain/fair/expensive label, and why not."""
    if model["label"]["publishes_label"]:
        return "publicada" if lang == "es" else "published"
    codes = {entry["code"] for entry in model["label"].get("failure_codes", ())}
    if codes == {"width_above_max"}:
        return "retenida, solo por el ancho" if lang == "es" else "withheld, on width alone"
    return "retenida" if lang == "es" else "withheld"


def _model_table(models: dict[VehicleType, dict[str, Any]], lang: str) -> list[str]:
    """Render the per-vertical table of published figures."""
    car, moto = models["car"], models["motorcycle"]
    headers = ("", "Carros", "Motos") if lang == "es" else ("", "Cars", "Motorcycles")
    labels = {
        "es": {
            "total": "Anuncios en total",
            "train": "Para entrenar",
            "test": "Para evaluar",
            "mape": "Error medio (MAPE)",
            "temporal": "Error medio, partición temporal",
            "baseline": "Referencia OLS",
            "gain": "Lo que gana el modelo sobre la referencia",
            "coverage": "Cobertura del rango (objetivo 80 %)",
            "width": "Ancho medio del rango",
            "label": "Etiqueta ganga/justo/caro",
        },
        "en": {
            "total": "Listings in total",
            "train": "Used for training",
            "test": "Used for evaluation",
            "mape": "Mean error (MAPE)",
            "temporal": "Mean error, time-ordered split",
            "baseline": "OLS reference",
            "gain": "What the model gains over the reference",
            "coverage": "Range coverage (80 % target)",
            "width": "Mean range width",
            "label": "Bargain/fair/expensive label",
        },
    }[lang]

    def row(name: str, left: str, right: str) -> str:
        return f"| {name} | {left} | {right} |"

    def temporal(model: dict[str, Any]) -> str:
        measured = model.get("metrics_temporal")
        if not measured:
            return "—"
        return _percent(float(measured["mape"]), lang)

    lines = [
        row(*headers),
        "| --- | ---: | ---: |",
        row(
            labels["total"],
            _integer(car["lake"]["rows"], lang),
            _integer(moto["lake"]["rows"], lang),
        ),
        row(
            labels["train"],
            _integer(car["lake"]["n_train"], lang),
            _integer(moto["lake"]["n_train"], lang),
        ),
        row(
            labels["test"],
            _integer(car["metrics"]["n_test"], lang),
            _integer(moto["metrics"]["n_test"], lang),
        ),
        row(
            labels["mape"],
            f"**{_percent(car['metrics']['mape'], lang)}**",
            f"**{_percent(moto['metrics']['mape'], lang)}**",
        ),
        row(labels["temporal"], temporal(car), temporal(moto)),
        row(
            labels["baseline"],
            _percent(car["metrics"]["baseline_mape"], lang),
            _percent(moto["metrics"]["baseline_mape"], lang),
        ),
        row(
            labels["gain"],
            _points((car["metrics"]["baseline_mape"] - car["metrics"]["mape"]) * 100, lang),
            _points((moto["metrics"]["baseline_mape"] - moto["metrics"]["mape"]) * 100, lang),
        ),
        row(
            labels["coverage"],
            _percent(car["metrics"]["interval_coverage"], lang),
            _percent(moto["metrics"]["interval_coverage"], lang),
        ),
        row(
            labels["width"],
            _percent(car["metrics"]["interval_mean_relative_width"], lang, 0),
            _percent(moto["metrics"]["interval_mean_relative_width"], lang, 0),
        ),
        row(labels["label"], _label_state(car, lang), _label_state(moto, lang)),
    ]
    return lines


_ECONOMICS_TEMPLATES: dict[str, dict[str, str]] = {
    "es": {
        "depreciation": (
            "- **Depreciación anual.** En motos va de {moto_low} ({moto_low_brand}) a "
            "{moto_high} ({moto_high_brand}); en carros, de {car_low} ({car_low_brand}) a "
            "{car_high} ({car_high_brand})."
        ),
        "mileage": (
            "- **Costo del kilometraje.** Cada {step} km restan {car_cost} en el carro "
            "mediano ({car_price}, {car_km} km) y {moto_cost} en la moto mediana "
            "({moto_price}, {moto_km} km)."
        ),
        "regional": (
            "- **Diferencias regionales.** El mismo carro se pide {car_gap} más caro en "
            "{car_where} que en {reference}; en motos la brecha va de {moto_high} "
            "({moto_high_where}) a {moto_low} ({moto_low_where})."
        ),
        "segment": (
            "- **Dónde falla más el modelo de carros.** {brand}, con {error} de error medio "
            "sobre {n} anuncios."
        ),
    },
    "en": {
        "depreciation": (
            "- **Annual depreciation.** Motorcycles run from {moto_low} ({moto_low_brand}) "
            "to {moto_high} ({moto_high_brand}); cars from {car_low} ({car_low_brand}) to "
            "{car_high} ({car_high_brand})."
        ),
        "mileage": (
            "- **What mileage costs.** Every {step} km take {car_cost} off the median car "
            "({car_price}, {car_km} km) and {moto_cost} off the median motorcycle "
            "({moto_price}, {moto_km} km)."
        ),
        "regional": (
            "- **Regional spread.** The same car is asked {car_gap} dearer in {car_where} "
            "than in {reference}; for motorcycles the gap runs from {moto_high} "
            "({moto_high_where}) to {moto_low} ({moto_low_where})."
        ),
        "segment": (
            "- **Where the car model is weakest.** {brand}, at {error} mean error over "
            "{n} listings."
        ),
    },
}
"""One template per finding per language, so a wording change touches one string and the
two languages stay structurally parallel. Filling them separately is what let the Spanish
and English halves of this README drift apart in the first place."""


def _economics(results: dict[str, Any], lang: str) -> list[str]:
    """Render the economic findings, each as one sentence carrying its own figures.

    Args:
        results: Published tables plus their manifest.
        lang: Which language's templates to fill.

    Returns:
        One markdown bullet per finding.
    """
    templates = _ECONOMICS_TEMPLATES[lang]
    depreciation = results["depreciation_by_brand"]
    mileage = results["mileage_effect"]
    regional = results["regional_effect"]
    segments = results["segment_error"]

    def slowest_and_fastest(vehicle_type: str) -> tuple[dict[str, Any], dict[str, Any]]:
        key = "annual_depreciation_pct"
        return (
            _extreme(depreciation, vehicle_type=vehicle_type, key=key, largest=False),
            _extreme(depreciation, vehicle_type=vehicle_type, key=key, largest=True),
        )

    def whole_vertical(vehicle_type: str) -> dict[str, Any]:
        return next(
            row
            for row in mileage
            if row["vehicle_type"] == vehicle_type and row["segment"] == "all"
        )

    def region(vehicle_type: str, *, largest: bool) -> dict[str, Any]:
        return _extreme(
            regional,
            vehicle_type=vehicle_type,
            key="pct_change",
            largest=largest,
            where="significant",
        )

    moto_low, moto_high = slowest_and_fastest("motorcycle")
    car_low, car_high = slowest_and_fastest("car")
    car_km, moto_km = whole_vertical("car"), whole_vertical("motorcycle")
    car_region = region("car", largest=True)
    moto_dear, moto_cheap = region("motorcycle", largest=True), region("motorcycle", largest=False)
    worst_brand = _extreme(
        [row for row in segments if row.get("segment_kind") == "brand"],
        vehicle_type="car",
        key="mape_pct",
        largest=True,
    )
    # Every regional figure is a contrast against one department, so the sentence has to
    # name it. Without that, "7,6 % dearer" reads as "dearer than average", which it is not.
    reference = next(
        row["department"]
        for row in regional
        if row["vehicle_type"] == "car" and row["is_reference"]
    )

    def pct(row: dict[str, Any], key: str) -> str:
        """The tables store percentages as points; the formatter takes fractions."""
        return _percent(float(row[key]) / 100, lang)

    return [
        templates["depreciation"].format(
            moto_low=pct(moto_low, "annual_depreciation_pct"),
            moto_low_brand=moto_low["brand"],
            moto_high=pct(moto_high, "annual_depreciation_pct"),
            moto_high_brand=moto_high["brand"],
            car_low=pct(car_low, "annual_depreciation_pct"),
            car_low_brand=car_low["brand"],
            car_high=pct(car_high, "annual_depreciation_pct"),
            car_high_brand=car_high["brand"],
        ),
        templates["mileage"].format(
            step=_integer(results["manifest"]["thresholds"]["mileage_step_km"], lang),
            car_cost=_cop(abs(float(car_km["cop_per_step"])), lang),
            car_price=_millions(float(car_km["median_price_cop"]), lang),
            car_km=_integer(float(car_km["median_mileage_km"]), lang),
            moto_cost=_cop(abs(float(moto_km["cop_per_step"])), lang),
            moto_price=_millions(float(moto_km["median_price_cop"]), lang),
            moto_km=_integer(float(moto_km["median_mileage_km"]), lang),
        ),
        templates["regional"].format(
            car_gap=pct(car_region, "pct_change"),
            car_where=car_region["department"],
            reference=reference,
            moto_high=pct(moto_dear, "pct_change"),
            moto_high_where=moto_dear["department"],
            moto_low=pct(moto_cheap, "pct_change"),
            moto_low_where=moto_cheap["department"],
        ),
        templates["segment"].format(
            brand=worst_brand["segment"],
            error=pct(worst_brand, "mape_pct"),
            n=_integer(float(worst_brand["n"]), lang),
        ),
    ]


def render_block(
    models: dict[VehicleType, dict[str, Any]],
    results: dict[str, Any],
    lang: str,
) -> str:
    """Render one language's block, markers included.

    Args:
        models: Bundle manifests by vehicle type.
        results: Published tables plus their manifest.
        lang: ``"es"`` or ``"en"``.

    Returns:
        The block as markdown, starting and ending with its markers.
    """
    manifest = results["manifest"]
    version = models["car"]["version"]
    dates = manifest["capture_dates"]
    span = float(manifest["capture_span_days"])

    if lang == "es":
        heading = "#### Las cifras del modelo servido"
        provenance = (
            f"Generado por `make readme` desde `artifacts/models/*/model.json` y "
            f"`docs/results/`. Modelo `{version}`, con {len(dates)} capturas entre "
            f"{dates[0]} y {dates[-1]} ({_decimal(span, lang)} días)."
        )
        economics_heading = "#### Lo que dicen los datos del mercado"
    else:
        heading = "#### Figures for the served model"
        provenance = (
            f"Generated by `make readme` from `artifacts/models/*/model.json` and "
            f"`docs/results/`. Model `{version}`, from {len(dates)} captures between "
            f"{dates[0]} and {dates[-1]} ({_decimal(span, lang)} days)."
        )
        economics_heading = "#### What the market data says"

    lines = [
        start_marker(lang),
        "",
        heading,
        "",
        *_model_table(models, lang),
        "",
        economics_heading,
        "",
        *_economics(results, lang),
        "",
        provenance,
        "",
        end_marker(lang),
    ]
    return "\n".join(lines)


def replace_block(text: str, block: str, lang: str) -> str:
    """Swap one language's block into the README text.

    Args:
        text: Current README contents.
        block: Rendered replacement, markers included.
        lang: Which block to replace.

    Returns:
        The README with that block replaced.

    Raises:
        ReadmeError: If either marker is missing or they are out of order, which means the
            README was edited in a way that would silently drop the generated figures.
    """
    start, end = start_marker(lang), end_marker(lang)
    first, last = text.find(start), text.find(end)
    if first == -1 or last == -1:
        msg = f"README is missing {start if first == -1 else end}"
        raise ReadmeError(msg)
    if last < first:
        msg = f"{end} appears before {start} in the README"
        raise ReadmeError(msg)
    return text[:first] + block + text[last + len(end) :]


def render_readme(
    text: str,
    models: dict[VehicleType, dict[str, Any]],
    results: dict[str, Any],
) -> str:
    """Return the README with every language's block regenerated."""
    for lang in LANGUAGES:
        text = replace_block(text, render_block(models, results, lang), lang)
    return text


def update(
    path: Path = README_PATH,
    *,
    artifacts: Path = ARTIFACTS_DIR,
    results_dir: Path = RESULTS_DIR,
    check: bool = False,
) -> bool:
    """Regenerate the README's figure blocks.

    Args:
        path: README to rewrite.
        artifacts: Root holding the bundle manifests.
        results_dir: Directory ``make results`` wrote.
        check: Report whether the file is current without writing it.

    Returns:
        ``True`` when the README on disk already matches what the files say.

    Raises:
        ReadmeError: If a source file or a marker is missing.
    """
    models = load_models(artifacts)
    results = load_results(results_dir)
    current = path.read_text(encoding="utf-8")
    rendered = render_readme(current, models, results)

    if rendered == current:
        return True
    if not check:
        path.write_text(rendered, encoding="utf-8")
    return False


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the readme command."""
    parser = argparse.ArgumentParser(
        prog="autovalor-readme",
        description="Regenerate the figures the README publishes.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the README is out of date, without writing it.",
    )
    parser.add_argument(
        "--readme",
        type=Path,
        default=README_PATH,
        help=f"README to rewrite (default: {README_PATH}).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``make readme``.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` on success, ``1`` when ``--check`` finds the README stale or a source file is
        missing.
    """
    args = build_parser().parse_args(argv)
    logging.basicConfig(level="INFO", format="%(levelname)s %(message)s")

    try:
        current = update(args.readme, check=args.check)
    except ReadmeError as error:
        logger.error("%s", error)
        return 1

    if current:
        sys.stdout.write(f"{args.readme} is up to date\n")
        return 0
    if args.check:
        sys.stdout.write(f"{args.readme} is out of date; run make readme\n")
        return 1
    sys.stdout.write(f"rewrote {args.readme}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
