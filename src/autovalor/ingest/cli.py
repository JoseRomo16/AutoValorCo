"""Command line entrypoint for TuCarro captures — what ``make scrape`` runs.

Examples:
    uv run python -m autovalor.ingest.cli --vehicle-type all --pages 10
    uv run python -m autovalor.ingest.cli --vehicle-type car --location bogota-dc --dry-run
"""

import argparse
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from autovalor.config import get_settings
from autovalor.ingest.bronze import write_capture
from autovalor.ingest.polite import PoliteClient
from autovalor.ingest.records import RawListing, VehicleType
from autovalor.ingest.tucarro import scrape_search

logger = logging.getLogger("autovalor.ingest")

VEHICLE_CHOICES = [*(vehicle.value for vehicle in VehicleType), "all"]


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the capture command."""
    settings = get_settings()
    parser = argparse.ArgumentParser(
        prog="autovalor-scrape",
        description="Capture TuCarro listings into the bronze layer.",
    )
    parser.add_argument(
        "--vehicle-type",
        choices=VEHICLE_CHOICES,
        default="all",
        help="Vertical to capture (default: all).",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=settings.scraper_max_pages,
        help=f"Search pages per location (default: {settings.scraper_max_pages}).",
    )
    parser.add_argument(
        "--location",
        action="append",
        default=None,
        metavar="SLUG",
        help=(
            "Location slug such as bogota-dc; repeatable. Without it the capture is "
            "national, which the site may still skew towards the runner's region."
        ),
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
        help="Scrape and report counts without writing to bronze.",
    )
    return parser


def capture(
    vehicle_type: VehicleType,
    *,
    pages: int,
    locations: Sequence[str | None],
    client: PoliteClient,
    captured_at: datetime,
) -> list[RawListing]:
    """Scrape every requested location for one vertical, deduplicated by listing id."""
    found: dict[str, RawListing] = {}
    for location in locations:
        listings = scrape_search(
            vehicle_type,
            pages=pages,
            location=location,
            client=client,
            captured_at=captured_at,
        )
        logger.info(
            "%s / %s: %d listings",
            vehicle_type.value,
            location or "nacional",
            len(listings),
        )
        for listing in listings:
            found.setdefault(listing.listing_id, listing)
    return list(found.values())


def main(argv: Sequence[str] | None = None) -> int:
    """Run a capture and return a process exit code."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    vehicles = list(VehicleType) if args.vehicle_type == "all" else [VehicleType(args.vehicle_type)]
    locations: list[str | None] = list(args.location) if args.location else [None]
    captured_at = datetime.now(UTC)

    exit_code = 0
    with PoliteClient() as client:
        for vehicle in vehicles:
            listings = capture(
                vehicle,
                pages=args.pages,
                locations=locations,
                client=client,
                captured_at=captured_at,
            )
            if not listings:
                logger.error("%s: no listings captured", vehicle.value)
                exit_code = 1
                continue
            if args.dry_run:
                logger.info(
                    "%s: %d listings (dry run, nothing written)", vehicle.value, len(listings)
                )
                continue
            target = write_capture(
                listings,
                vehicle_type=vehicle,
                captured_at=captured_at,
                data_dir=args.data_dir,
            )
            logger.info("%s: %d listings -> %s", vehicle.value, len(listings), target)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
