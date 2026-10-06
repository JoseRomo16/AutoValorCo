"""Writing the economic results to ``docs/results/`` as versioned files.

F4's app has to show depreciation curves and regional differences without refitting
anything — a Next.js static site cannot run statsmodels, and a free Render service should
not be fitting regressions on request. So every result here is written once, committed, and
read as data.

Two formats per table, on purpose: **JSON** for the app, which wants records it can map
over, and **CSV** for a notebook or a spreadsheet, which is how these numbers get checked.
They are generated from the same frame in the same call, so they cannot drift.

Floats are rounded before writing. These files live in git, and an unrounded float changes
in its fifteenth decimal every time the lake grows by one row, which would make every diff
unreadable and every commit look like a result changed.

The manifest is the part that makes the export auditable: it records which lake the numbers
came from — rows per vertical, the capture span, the thresholds in force. Without it a
figure in the README is a number with no provenance, and the first question anyone asks of
a result is "measured on what".
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger("autovalor.analysis")

RESULTS_DIR = Path("docs/results")
"""Where the exports live. Inside docs/ because they are published artefacts, not data."""

FIGURES_DIR = Path("docs/figures")
"""Where the PNGs live, for the same reason."""

FLOAT_DECIMALS = 4
"""Decimals kept on export. Four is past the precision any of these estimates has —
a depreciation rate is reported to one decimal — and keeps the diffs stable."""

MANIFEST_NAME = "manifest.json"


@dataclass
class Manifest:
    """What the exported results were measured on.

    Attributes:
        generated_at: UTC timestamp of the run.
        gold_rows: Rows per vertical in the gold table the run read.
        capture_span_days: Spread of ``last_seen_at`` across the lake, which is what
            decides whether a temporal split or a price index is possible yet.
        detail_coverage: Share of each vertical carrying listing-page attributes.
        thresholds: The filters and cut-offs in force, so a reader does not have to go
            find them in the source.
        files: Relative paths written, filled in by :func:`write_table`.
    """

    generated_at: str
    gold_rows: dict[str, int]
    capture_span_days: float
    detail_coverage: dict[str, float]
    thresholds: dict[str, float]
    files: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        """Return the manifest as a JSON-ready mapping."""
        return {
            "generated_at": self.generated_at,
            "gold_rows": self.gold_rows,
            "capture_span_days": round(self.capture_span_days, 3),
            "detail_coverage": {
                key: round(value, 4) for key, value in self.detail_coverage.items()
            },
            "thresholds": self.thresholds,
            "files": sorted(self.files),
        }


def now_utc() -> str:
    """Return the current UTC instant as an ISO-8601 string, to the second.

    Seconds rather than microseconds: the extra digits are noise in a committed file.
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def write_table(frame: pd.DataFrame, name: str, *, output_dir: Path, manifest: Manifest) -> None:
    """Write one result table as both JSON and CSV, and record it in the manifest.

    Args:
        frame: The table to write.
        name: Base file name, without extension.
        output_dir: Directory to write into; created if missing.
        manifest: Manifest to append the written paths to.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    rounded = frame.round(FLOAT_DECIMALS)

    csv_path = output_dir / f"{name}.csv"
    json_path = output_dir / f"{name}.json"
    rounded.to_csv(csv_path, index=False, encoding="utf-8", lineterminator="\n")
    json_path.write_text(
        json.dumps(_records(rounded), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    manifest.files.extend([csv_path.name, json_path.name])
    logger.info("exported %s — %d rows", name, len(frame))


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    """Return the frame as JSON-ready records, with every missing value as ``null``.

    ``NaN`` is not valid JSON, and writing it produces a file that a strict parser — which
    includes every browser — refuses to read. Replacing it inside a float column has to
    happen record by record: assigning ``None`` back into a float Series just turns it into
    ``NaN`` again.

    Args:
        frame: The table to convert.

    Returns:
        One mapping per row, with ``None`` wherever the value was missing and plain Python
        scalars elsewhere.
    """
    records: list[dict[str, object]] = []
    for row in frame.to_dict(orient="records"):
        record: dict[str, object] = {}
        for key, value in row.items():
            missing = value is None or (not isinstance(value, list | tuple) and pd.isna(value))
            record[str(key)] = None if missing else _scalar(value)
        records.append(record)
    return records


def _scalar(value: object) -> object:
    """Return a numpy or pandas scalar as the plain Python value json can serialise."""
    item = getattr(value, "item", None)
    return item() if callable(item) else value


def write_manifest(manifest: Manifest, *, output_dir: Path) -> Path:
    """Write the manifest beside the tables.

    Args:
        manifest: Manifest to write.
        output_dir: Directory to write into.

    Returns:
        The path written.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / MANIFEST_NAME
    path.write_text(
        json.dumps(manifest.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    logger.info("wrote %s with %d files", path, len(manifest.files))
    return path
