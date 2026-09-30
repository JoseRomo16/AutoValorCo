"""Validate each layer of the lake against its Pandera schema — part of ``make transform``.

Bronze is read straight from Parquet; silver and gold are read from the DuckDB database
that dbt writes. Stages whose data does not exist yet are skipped with a warning, so the
command is usable from the very first capture onwards.

Examples:
    uv run python -m autovalor.quality.cli --stage bronze
    uv run python -m autovalor.quality.cli
"""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

import duckdb
import pandas as pd

from autovalor.config import get_settings
from autovalor.ingest.bronze import read_captures
from autovalor.quality.schemas import (
    LayerValidationError,
    validate_bronze,
    validate_gold,
    validate_silver,
)

logger = logging.getLogger("autovalor.quality")

STAGES = ("bronze", "silver", "gold")

DBT_TABLES = {
    "silver": "main_silver.silver_listings",
    "gold": "main_gold.gold_listings",
}


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the validation command."""
    parser = argparse.ArgumentParser(
        prog="autovalor-validate",
        description="Validate the lake layers against their Pandera schemas.",
    )
    parser.add_argument(
        "--stage",
        action="append",
        choices=STAGES,
        default=None,
        help="Layer to validate; repeatable. Defaults to all three.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Root of the data lake (default: the configured AUTOVALOR_DATA_DIR).",
    )
    parser.add_argument(
        "--duckdb-path",
        type=Path,
        default=None,
        help="DuckDB database written by dbt (default: the configured one).",
    )
    return parser


def read_dbt_table(duckdb_path: Path, table: str) -> pd.DataFrame | None:
    """Read a dbt-built table, returning ``None`` when it does not exist yet."""
    if not duckdb_path.exists():
        return None
    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        try:
            # Table names come from DBT_TABLES, never from user input.
            return connection.sql(f"select * from {table}").df()
        except duckdb.CatalogException:
            return None


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the requested stages and return a process exit code."""
    args = build_parser().parse_args(argv)
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)-8s %(message)s")

    data_dir = args.data_dir if args.data_dir is not None else settings.data_dir
    duckdb_path = args.duckdb_path if args.duckdb_path is not None else settings.duckdb_path
    stages: tuple[str, ...] = tuple(args.stage) if args.stage else STAGES

    exit_code = 0
    for stage in stages:
        frame = (
            read_captures(data_dir)
            if stage == "bronze"
            else read_dbt_table(duckdb_path, DBT_TABLES[stage])
        )
        if frame is None or frame.empty:
            logger.warning("%s: no data yet, skipped", stage)
            continue

        validator = {
            "bronze": validate_bronze,
            "silver": validate_silver,
            "gold": validate_gold,
        }[stage]
        try:
            validator(frame)
        except LayerValidationError as exc:
            logger.error("%s: %d rows FAILED validation\n%s", stage, len(frame), exc)
            exit_code = 1
        else:
            logger.info("%s: %d rows valid", stage, len(frame))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
