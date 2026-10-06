"""Static figures for the README and the F3 write-up.

Five figures, each one answering a question the tables answer less readably. The chart type
follows the job of the data, which is the only rule here that is not taste:

===============================  ===============================================
Question                         Form
===============================  ===============================================
Which brands hold their value?   Horizontal bars, one series, 95 % interval drawn
What is a brand worth at age N?  Lines over age, one per brand, direct-labelled
What do 10.000 km cost?          Bars over the ordered price segments
Where is the same vehicle        Diverging bars around zero, signed against the
cheaper?                         reference department
Where does the model err?        Horizontal bars against the F2 target line
===============================  ===============================================

Colour is assigned by job, not by taste either: a single-series magnitude chart gets one
hue, the per-brand curves get the categorical slots in fixed order, and the regional chart
— the only one whose data has a sign — gets the diverging pair with a neutral zero. Three
of the categorical slots sit below 3:1 against the chart surface, so every line carries a
direct label at its end: identity never rests on colour alone.

Rendered through the Agg backend so this runs in CI with no display, and written at a size
that is legible inline on GitHub without being opened.
"""

import logging
from pathlib import Path

import matplotlib

# Selected before pyplot is imported: on a headless runner the default interactive backend
# fails at import time, not at draw time.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from autovalor.analysis.mileage import MILEAGE_STEP_KM

logger = logging.getLogger("autovalor.analysis")

SURFACE = "#fcfcfb"
PRIMARY_INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
MUTED_INK = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

SERIES = "#2a78d6"
"""Single-series hue, for the magnitude charts."""

CATEGORICAL = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300")
"""Categorical slots in fixed order. Validated for adjacent-pair separation under both
normal vision and simulated colour-vision deficiency; the order is the safety mechanism,
so it is never cycled or reshuffled. A seventh brand folds out of the chart instead."""

NEGATIVE = "#e34948"
POSITIVE = "#2a78d6"
"""The diverging pair, for the one chart whose values have a sign."""

FIGURE_DPI = 150
TARGET_MAPE_PCT = 15.0
"""The F2 acceptance threshold, drawn as a reference line on the error chart."""


def _style_axes(axes: Axes, *, xlabel: str = "", ylabel: str = "", title: str = "") -> None:
    """Apply the recessive chrome every figure here shares."""
    axes.set_facecolor(SURFACE)
    axes.set_title(title, color=PRIMARY_INK, fontsize=11, loc="left", pad=12)
    axes.set_xlabel(xlabel, color=SECONDARY_INK, fontsize=9)
    axes.set_ylabel(ylabel, color=SECONDARY_INK, fontsize=9)
    axes.tick_params(colors=MUTED_INK, labelsize=8.5)
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_color(BASELINE)
    axes.grid(True, color=GRIDLINE, linewidth=0.8, axis="x")
    axes.set_axisbelow(True)


def _save(figure: Figure, path: Path) -> Path:
    """Write a figure and close it, so a long run does not accumulate open figures."""
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=FIGURE_DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(figure)
    logger.info("wrote %s", path)
    return path


def depreciation_figure(curves: pd.DataFrame, path: Path) -> Path:
    """Annual depreciation by brand, with its confidence interval.

    Args:
        curves: Output of :func:`autovalor.analysis.depreciation.depreciation_curves`.
        path: PNG to write.

    Returns:
        The path written.
    """
    ordered = curves.sort_values("annual_depreciation_pct")
    height = max(2.4, 0.42 * len(ordered) + 1.4)
    figure, axes = plt.subplots(figsize=(7.2, height), facecolor=SURFACE)

    positions = range(len(ordered))
    errors = [
        ordered["annual_depreciation_pct"] - ordered["ci_low_pct"],
        ordered["ci_high_pct"] - ordered["annual_depreciation_pct"],
    ]
    axes.barh(
        list(positions),
        ordered["annual_depreciation_pct"],
        color=SERIES,
        height=0.62,
        xerr=errors,
        error_kw={"ecolor": SECONDARY_INK, "elinewidth": 1.0, "capsize": 3},
    )
    axes.set_yticks(list(positions))
    axes.set_yticklabels(ordered["brand"])

    vertical = str(ordered["vehicle_type"].iloc[0])
    _style_axes(
        axes,
        xlabel="Annual depreciation (% of price per year)",
        title=f"{vertical.capitalize()}s — what a year of age costs, by brand",
    )
    # The value next to each bar: a reader comparing two brands should not have to measure
    # against the axis. Anchored past the whisker rather than at the bar's end, where it
    # would sit on top of the interval it is supposed to be read with.
    for position, value, edge in zip(
        positions, ordered["annual_depreciation_pct"], ordered["ci_high_pct"], strict=True
    ):
        axes.annotate(
            f"{value:.1f}%",
            (edge, position),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=8.5,
            color=SECONDARY_INK,
        )
    axes.margins(x=0.14)
    return _save(figure, path)


def retained_value_figure(retained: pd.DataFrame, path: Path, *, max_brands: int = 6) -> Path:
    """Share of value retained as a vehicle ages, one line per brand.

    Args:
        retained: Output of :func:`autovalor.analysis.depreciation.depreciation_at_ages`.
        path: PNG to write.
        max_brands: Brands to draw. Past this the categorical palette would need hues it
            does not have, so the slowest and fastest depreciating brands are kept and the
            middle is left to the table.

    Returns:
        The path written.
    """
    by_brand = retained.sort_values(["brand", "age_years"])
    brands = list(by_brand["brand"].unique())
    if len(brands) > max_brands:
        # Keeping the extremes rather than the first N: the chart's job is the spread.
        at_ten = (
            by_brand[by_brand["age_years"] == by_brand["age_years"].max()]
            .sort_values("retained_value_pct")
            .reset_index(drop=True)
        )
        half = max_brands // 2
        brands = list(at_ten["brand"].head(half)) + list(at_ten["brand"].tail(max_brands - half))

    figure, axes = plt.subplots(figsize=(7.2, 4.4), facecolor=SURFACE)
    ends: list[tuple[float, str]] = []
    for slot, brand in enumerate(brands):
        series = by_brand[by_brand["brand"] == brand]
        colour = CATEGORICAL[slot % len(CATEGORICAL)]
        axes.plot(
            series["age_years"],
            series["retained_value_pct"],
            color=colour,
            linewidth=2.0,
            marker="o",
            markersize=4.5,
        )
        last = series.iloc[-1]
        ends.append((float(last["retained_value_pct"]), str(brand)))

    # Direct label at the end of every line: three of these hues are below 3:1 against the
    # surface, so colour alone may not carry identity. Two brands that end within a point
    # of each other would overprint, so the labels are pushed apart before they are drawn —
    # the line still points at the true value, the text just steps aside.
    last_age = float(by_brand["age_years"].max())
    span = float(by_brand["retained_value_pct"].max() - by_brand["retained_value_pct"].min())
    min_gap = max(span * 0.045, 0.5)
    placed = 0.0
    for value, brand in sorted(ends):
        position = value if value - placed >= min_gap or placed == 0.0 else placed + min_gap
        placed = position
        axes.annotate(
            f" {brand}",
            (last_age, position),
            fontsize=8.5,
            color=SECONDARY_INK,
            va="center",
        )

    vertical = str(retained["vehicle_type"].iloc[0])
    _style_axes(
        axes,
        xlabel="Age (years)",
        ylabel="Value retained (% of a new one)",
        title=f"{vertical.capitalize()}s — value retained as they age",
    )
    axes.grid(True, color=GRIDLINE, linewidth=0.8, axis="y")
    axes.margins(x=0.18)
    return _save(figure, path)


def mileage_figure(effects: pd.DataFrame, path: Path) -> Path:
    """What the next 10.000 km cost, by price segment.

    Args:
        effects: Output of :func:`autovalor.analysis.mileage.mileage_effects`.
        path: PNG to write.

    Returns:
        The path written.
    """
    segments = effects[effects["segment"] != "all"].sort_values("segment")
    figure, axes = plt.subplots(figsize=(7.2, 3.8), facecolor=SURFACE)

    # Plotted as a positive cost rather than a negative effect: the question is "what does
    # it cost me", and a chart of negative bars answers it less directly. Flipping the sign
    # reverses the interval, so the ends swap here -- and only here, because the exported
    # table keeps the signed convention.
    cost_millions = -segments["cop_per_step"] / 1e6
    low = -segments["cop_ci_high"] / 1e6
    high = -segments["cop_ci_low"] / 1e6
    axes.bar(
        segments["segment"],
        cost_millions,
        color=SERIES,
        width=0.58,
        yerr=[cost_millions - low, high - cost_millions],
        error_kw={"ecolor": SECONDARY_INK, "elinewidth": 1.0, "capsize": 3},
    )
    for segment, value, price in zip(
        segments["segment"], cost_millions, segments["median_price_cop"], strict=True
    ):
        axes.annotate(
            f"{value:.2f} M\n(median {price / 1e6:.0f} M)",
            (segment, value),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            fontsize=8,
            color=SECONDARY_INK,
        )

    vertical = str(effects["vehicle_type"].iloc[0])
    _style_axes(
        axes,
        xlabel="Price segment (quartile, cheapest to dearest)",
        ylabel="Cost in COP millions",
        title=(
            f"{vertical.capitalize()}s — what the next {MILEAGE_STEP_KM:,} km cost, "
            "at each segment's median listing"
        ),
    )
    axes.grid(True, color=GRIDLINE, linewidth=0.8, axis="y")
    axes.margins(y=0.22)
    return _save(figure, path)


def regional_figure(effects: pd.DataFrame, path: Path) -> Path:
    """Price difference by department for a comparable vehicle.

    Args:
        effects: Output of :func:`autovalor.analysis.regional.regional_effects`.
        path: PNG to write.

    Returns:
        The path written.
    """
    ordered = effects.sort_values("pct_change")
    height = max(2.4, 0.42 * len(ordered) + 1.4)
    figure, axes = plt.subplots(figsize=(7.2, height), facecolor=SURFACE)

    positions = list(range(len(ordered)))
    # The only signed chart here, so the only one that gets the diverging pair.
    colours = [NEGATIVE if value < 0 else POSITIVE for value in ordered["pct_change"]]
    axes.barh(
        positions,
        ordered["pct_change"],
        color=colours,
        height=0.62,
        xerr=[
            ordered["pct_change"] - ordered["pct_ci_low"],
            ordered["pct_ci_high"] - ordered["pct_change"],
        ],
        error_kw={"ecolor": SECONDARY_INK, "elinewidth": 1.0, "capsize": 3},
    )
    axes.axvline(0.0, color=BASELINE, linewidth=1.2)
    axes.set_yticks(positions)
    reference = ordered[ordered["is_reference"]]
    reference_name = str(reference["department"].iloc[0]) if not reference.empty else "reference"
    axes.set_yticklabels(
        [
            f"{row['department']}{' (ref.)' if row['is_reference'] else ''}"
            for _, row in ordered.iterrows()
        ]
    )

    vertical = str(ordered["vehicle_type"].iloc[0])
    _style_axes(
        axes,
        xlabel=f"Price difference vs {reference_name} (%), same vehicle",
        title=f"{vertical.capitalize()}s — where the same vehicle is cheaper",
    )
    # Labelled past the far end of each whisker, on the side the bar points to, so the
    # number never lands on the interval or across the zero line.
    for position, row in zip(positions, ordered.to_dict(orient="records"), strict=True):
        if row["is_reference"]:
            continue
        negative = row["pct_change"] < 0
        edge = row["pct_ci_low"] if negative else row["pct_ci_high"]
        axes.annotate(
            f"{row['pct_change']:+.1f}%",
            (edge, position),
            xytext=(-8 if negative else 8, 0),
            textcoords="offset points",
            va="center",
            ha="right" if negative else "left",
            fontsize=8.5,
            color=SECONDARY_INK,
        )
    axes.margins(x=0.20)
    return _save(figure, path)


def segment_error_figure(errors: pd.DataFrame, path: Path, *, kind: str = "brand") -> Path:
    """Held-out MAPE by segment, against the F2 target.

    Args:
        errors: Output of :func:`autovalor.analysis.segments.segment_errors`.
        path: PNG to write.
        kind: Which cut to draw — ``brand``, ``price_segment`` or ``department``.

    Returns:
        The path written.
    """
    cut = errors[errors["segment_kind"] == kind].sort_values("mape_pct")
    height = max(2.4, 0.42 * len(cut) + 1.4)
    figure, axes = plt.subplots(figsize=(7.2, height), facecolor=SURFACE)

    positions = list(range(len(cut)))
    axes.barh(positions, cut["mape_pct"], color=SERIES, height=0.62)
    axes.axvline(
        TARGET_MAPE_PCT,
        color=SECONDARY_INK,
        linewidth=1.2,
        linestyle="--",
    )
    axes.annotate(
        f"F2 target {TARGET_MAPE_PCT:.0f}%",
        (TARGET_MAPE_PCT, len(cut) - 0.4),
        xytext=(4, 0),
        textcoords="offset points",
        fontsize=8,
        color=SECONDARY_INK,
    )
    axes.set_yticks(positions)
    axes.set_yticklabels([f"{row['segment']} (n={row['n']})" for _, row in cut.iterrows()])
    for position, value in zip(positions, cut["mape_pct"], strict=True):
        axes.annotate(
            f"{value:.1f}%",
            (value, position),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=8.5,
            color=SECONDARY_INK,
        )

    vertical = str(cut["vehicle_type"].iloc[0])
    _style_axes(
        axes,
        xlabel="Held-out MAPE (%)",
        title=f"{vertical.capitalize()}s — where the model's error lands, by {kind}",
    )
    axes.margins(x=0.16)
    return _save(figure, path)
