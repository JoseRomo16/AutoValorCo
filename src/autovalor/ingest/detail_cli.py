"""Command line entrypoint for the motorcycle detail enrichment.

Examples:
    uv run python -m autovalor.ingest.detail_cli --budget 500
    uv run python -m autovalor.ingest.detail_cli --budget 20 --dry-run
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import duckdb

from autovalor.config import get_settings
from autovalor.ingest.bronze import read_details, write_details
from autovalor.ingest.detail import (
    DEFAULT_BUDGET,
    DEFAULT_SEED,
    coverage,
    enrich_listings,
    select_listings,
)
from autovalor.ingest.records import VehicleType

logger = logging.getLogger("autovalor.ingest.detail")

GOLD_TABLE = "main_gold.gold_listings"


def load_candidates(
    vehicle_type: VehicleType,
    *,
    duckdb_path: Path | None = None,
    data_dir: Path | None = None,
) -> list[tuple[str, str]]:
    """Return the listings of a vertical that have no detail row yet.

    Args:
        vehicle_type: Vertical to enrich.
        duckdb_path: Database written by dbt; defaults to the configured path.
        data_dir: Root of the data lake; defaults to the configured one.

    Returns:
        ``(listing_id, source_url)`` pairs, sorted.

    Raises:
        FileNotFoundError: If the database does not exist — gold is where the candidates
            come from, so there is nothing to enrich without it.
    """
    settings = get_settings()
    database = duckdb_path if duckdb_path is not None else settings.duckdb_path
    if not database.exists():
        msg = f"{database} does not exist; run the transform first"
        raise FileNotFoundError(msg)

    with duckdb.connect(str(database), read_only=True) as con:
        # GOLD_TABLE is a module constant, not input; the vertical is a bound parameter.
        rows = con.execute(
            f"select listing_id, source_url from {GOLD_TABLE} where vehicle_type = ?",
            [vehicle_type.value],
        ).fetchall()

    existing = read_details(data_dir, vehicle_type=vehicle_type)
    enriched = set(existing["listing_id"]) if not existing.empty else set()
    candidates = [
        (str(listing_id), str(url)) for listing_id, url in rows if listing_id not in enriched
    ]
    logger.info(
        "%s: %d listings in gold, %d already enriched, %d candidates",
        vehicle_type.value,
        len(rows),
        len(enriched),
        len(candidates),
    )
    return sorted(candidates)


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the enrichment command."""
    parser = argparse.ArgumentParser(
        prog="autovalor-enrich",
        description="Read the attribute table of listing pages that have no details yet.",
    )
    parser.add_argument(
        "--vehicle-type",
        choices=[vehicle.value for vehicle in VehicleType],
        default=VehicleType.MOTORCYCLE.value,
        help=(
            "Vertical to enrich (default: motorcycle). Cars reach the F2 target without "
            "any extra request, so enriching them is not justified by performance."
        ),
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=DEFAULT_BUDGET,
        help=(
            f"Listings to fetch in this run (default: {DEFAULT_BUDGET}). A polite pause "
            "between requests makes this a time budget: roughly 35 minutes for 500."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=(
            f"Seed for the random draw over candidates (default: {DEFAULT_SEED}). The "
            "sample is random because identifiers correlate with publication date."
        ),
    )
    parser.add_argument(
        "--duckdb-path",
        type=Path,
        default=None,
        help="Database written by dbt (default: the configured AUTOVALOR_DUCKDB_PATH).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Root of the data lake (default: the configured AUTOVALOR_DATA_DIR).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report which listings would be fetched without making a single request.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one enrichment pass and return a process exit code.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` on success, ``1`` when there is no lake to read or every page failed.
    """
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )
    vehicle_type = VehicleType(args.vehicle_type)

    try:
        candidates = load_candidates(
            vehicle_type, duckdb_path=args.duckdb_path, data_dir=args.data_dir
        )
    except FileNotFoundError as error:
        logger.error("%s", error)
        return 1

    if not candidates:
        logger.info("%s: every listing already has details", vehicle_type.value)
        return 0

    if args.dry_run:
        chosen = select_listings(candidates, budget=args.budget, seed=args.seed)
        sys.stdout.write(f"{len(chosen)} listings would be fetched, first five:\n")
        for listing_id, url in chosen[:5]:
            sys.stdout.write(f"  {listing_id}  {url}\n")
        return 0

    result = enrich_listings(
        candidates, vehicle_type=vehicle_type, budget=args.budget, seed=args.seed
    )
    if not result.details:
        logger.error("%s: no page could be read", vehicle_type.value)
        return 1

    target = write_details(result.details, vehicle_type=vehicle_type, data_dir=args.data_dir)
    logger.info("%s: %d rows -> %s", vehicle_type.value, len(result.details), target)

    sys.stdout.write("attribute coverage in this run:\n")
    for key, share in sorted(coverage(result.details).items(), key=lambda item: -item[1]):
        sys.stdout.write(f"  {key:16} {share * 100:5.1f}%\n")
    if result.unknown_labels:
        sys.stdout.write("labels seen but not stored (schema drift):\n")
        for label, count in sorted(result.unknown_labels.items(), key=lambda item: -item[1]):
            sys.stdout.write(f"  {label:32} {count}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
