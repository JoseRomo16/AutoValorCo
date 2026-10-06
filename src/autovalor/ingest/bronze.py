"""Writing captures to the bronze layer.

Bronze is immutable: a capture is written exactly once, partitioned by source, vehicle
type and capture date, and never updated in place. Re-running a scraper on the same day
produces a new file (the timestamp is part of the name); overwriting an existing file is
an error, not a convenience.
"""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

import pandas as pd

from autovalor.config import get_settings
from autovalor.ingest.records import ListingDetail, RawListing, VehicleType

PARQUET_COMPRESSION: Final[Literal["zstd"]] = "zstd"


def capture_dir(
    data_dir: Path,
    *,
    vehicle_type: VehicleType,
    captured_at: datetime,
    source: str = "tucarro",
) -> Path:
    """Return the Hive-style partition directory for a capture."""
    return (
        data_dir
        / "bronze"
        / f"source={source}"
        / f"vehicle_type={vehicle_type.value}"
        / f"capture_date={captured_at.astimezone(UTC):%Y-%m-%d}"
    )


def capture_filename(captured_at: datetime) -> str:
    """Return the file name for a capture, unique per run down to the second."""
    return f"listings_{captured_at.astimezone(UTC):%Y%m%dT%H%M%SZ}.parquet"


def write_capture(
    listings: Iterable[RawListing],
    *,
    vehicle_type: VehicleType,
    captured_at: datetime | None = None,
    data_dir: Path | None = None,
    source: str = "tucarro",
) -> Path:
    """Write one capture to the bronze layer and return the file written.

    Args:
        listings: Listings collected in this run; must not be empty.
        vehicle_type: Partition the capture belongs to.
        captured_at: Capture instant. Defaults to now in UTC.
        data_dir: Root of the data lake. Defaults to the configured one.
        source: Site the listings came from.

    Returns:
        Path of the Parquet file written.

    Raises:
        ValueError: If ``listings`` is empty — an empty capture means the scraper
            failed and writing it would poison the layer with a silent gap.
        FileExistsError: If the target file already exists; bronze is immutable.
    """
    rows: Sequence[RawListing] = list(listings)
    if not rows:
        msg = f"refusing to write an empty {vehicle_type.value} capture to bronze"
        raise ValueError(msg)

    moment = captured_at if captured_at is not None else datetime.now(UTC)
    root = data_dir if data_dir is not None else get_settings().data_dir

    directory = capture_dir(root, vehicle_type=vehicle_type, captured_at=moment, source=source)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / capture_filename(moment)
    if target.exists():
        msg = f"{target} already exists and the bronze layer is immutable"
        raise FileExistsError(msg)

    frame = pd.DataFrame([listing.to_row() for listing in rows])
    frame.to_parquet(target, engine="pyarrow", compression=PARQUET_COMPRESSION, index=False)
    return target


def detail_dir(data_dir: Path, *, vehicle_type: VehicleType, source: str = "tucarro") -> Path:
    """Return the partition directory for enriched listing details.

    Deliberately a sibling of ``bronze/`` rather than a directory inside it. The layer is
    bronze-grade — raw strings as published, written once, never updated — but dbt reads
    bronze as a single ``read_parquet`` union over ``bronze/**/*.parquet``, and a second
    schema under that glob would be unioned into the capture source and silently fill
    silver with null columns.

    Not partitioned by date either, unlike captures. A detail row describes the vehicle
    rather than a moment, so it is written once per listing; partitioning by fetch date
    would make "has this listing been enriched?" a scan of every date instead of one read.
    """
    return data_dir / "detail" / f"source={source}" / f"vehicle_type={vehicle_type.value}"


def write_details(
    details: Iterable[ListingDetail],
    *,
    vehicle_type: VehicleType,
    fetched_at: datetime | None = None,
    data_dir: Path | None = None,
    source: str = "tucarro",
) -> Path:
    """Write one enrichment run to the detail layer and return the file written.

    Args:
        details: Rows parsed in this run; must not be empty.
        vehicle_type: Partition the rows belong to.
        fetched_at: Run instant, used to name the file. Defaults to now in UTC.
        data_dir: Root of the data lake. Defaults to the configured one.
        source: Site the listings came from.

    Returns:
        Path of the Parquet file written.

    Raises:
        ValueError: If ``details`` is empty.
        FileExistsError: If the target file already exists; bronze is immutable.
    """
    rows: Sequence[ListingDetail] = list(details)
    if not rows:
        msg = f"refusing to write an empty {vehicle_type.value} enrichment to bronze"
        raise ValueError(msg)

    moment = fetched_at if fetched_at is not None else datetime.now(UTC)
    root = data_dir if data_dir is not None else get_settings().data_dir

    directory = detail_dir(root, vehicle_type=vehicle_type, source=source)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"details_{moment.astimezone(UTC):%Y%m%dT%H%M%SZ}.parquet"
    if target.exists():
        msg = f"{target} already exists and the bronze layer is immutable"
        raise FileExistsError(msg)

    frame = pd.DataFrame([detail.to_row() for detail in rows])
    frame.to_parquet(target, engine="pyarrow", compression=PARQUET_COMPRESSION, index=False)
    return target


def read_details(
    data_dir: Path | None = None,
    *,
    vehicle_type: VehicleType | None = None,
    source: str = "tucarro",
) -> pd.DataFrame:
    """Read every enrichment run, optionally filtered by vehicle type.

    Returns an empty frame when nothing has been enriched yet, so a first run can ask
    "which listings already have details?" without a special case.
    """
    root = data_dir if data_dir is not None else get_settings().data_dir
    base = root / "detail" / f"source={source}"
    pattern = (
        f"vehicle_type={vehicle_type.value}/*.parquet"
        if vehicle_type is not None
        else "*/*.parquet"
    )
    files = sorted(base.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.concat((pd.read_parquet(path) for path in files), ignore_index=True)


def read_captures(
    data_dir: Path | None = None,
    *,
    vehicle_type: VehicleType | None = None,
    source: str = "tucarro",
) -> pd.DataFrame:
    """Read every bronze capture, optionally filtered by vehicle type.

    Returns an empty frame when nothing has been captured yet, so callers can treat a
    cold start like any other run.
    """
    root = data_dir if data_dir is not None else get_settings().data_dir
    base = root / "bronze" / f"source={source}"
    pattern = (
        f"vehicle_type={vehicle_type.value}/*/*.parquet"
        if vehicle_type is not None
        else "*/*/*.parquet"
    )
    files = sorted(base.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.concat((pd.read_parquet(path) for path in files), ignore_index=True)
