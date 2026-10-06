"""Keep the bronze capture history on an orphan ``data`` branch of this repository.

Weekly captures only become useful by accumulating: the monthly price index and the
depreciation curves of F3 are time series, and temporal validation needs a lake that
spans weeks. Workflow artifacts cannot carry that — they expire after 90 days and have to
be unpacked by hand. [ADR 0004](../../../docs/adr/0004-capture-history-storage.md) chose a
``data`` branch, with Cloudflare R2 as the documented upgrade path once the dataset
outgrows git.

The branch holds no code: its roots are ``bronze/`` and ``detail/``, mirroring
``data/bronze/`` and ``data/detail/`` with the same Hive partitions, so a pulled history
can be read by dbt exactly as a local capture would be.

Two rules hold on both sides of the transfer:

* **Captures are immutable.** A file already present is never overwritten, in either
  direction. Captures are named after their UTC instant, so a collision means the same
  capture, not a newer version of it.
* **Only the raw layers travel.** Silver and gold are rebuilt from them with dbt, so
  publishing those would store a derivation that the transformation already defines. The
  detail layer does travel, because an enrichment pass costs one polite request per
  listing and nobody should have to spend that hour twice.

One mechanism serves all three callers — the weekly workflow, ``make pull-history`` and
the local seeding — so there is a single place where this can be wrong.
"""

import argparse
import logging
import shutil
import subprocess
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from autovalor.config import get_settings

logger = logging.getLogger("autovalor.history")

DATA_BRANCH: Final = "data"
"""Branch that carries the captures. Orphan: it shares no history with ``main``."""

BRONZE_PREFIX: Final = "bronze"
"""Directory at the root of the branch that mirrors ``data/bronze``."""

DETAIL_PREFIX: Final = "detail"
"""Directory that mirrors ``data/detail`` — the listing-page attributes.

Published for the same reason bronze is: an enrichment pass costs one polite request per
listing, so ~1.300 of them is an hour of scraping that nobody should have to repeat. It
is a separate root because dbt reads each layer through its own glob.
"""

PUBLISHED_PREFIXES: Final = (BRONZE_PREFIX, DETAIL_PREFIX)
"""Every layer that travels. Silver and gold never do; dbt rebuilds them."""

DEFAULT_REMOTE: Final = "origin"

CAPTURE_GLOB: Final = "**/*.parquet"
"""Only Parquet travels. ``.gitkeep`` and stray files stay where they are."""


@dataclass(frozen=True)
class HistoryResult:
    """What one transfer moved.

    Attributes:
        copied: Capture files written at the destination.
        skipped: Capture files already present, left untouched.
        branch: Branch the history lives on.
        committed: Whether a commit was created (``push`` only).
    """

    copied: tuple[str, ...]
    skipped: tuple[str, ...]
    branch: str = DATA_BRANCH
    committed: bool = False

    def summary(self) -> str:
        """Return a one-line description, for a log or a CLI."""
        return (
            f"{len(self.copied)} capture files copied, "
            f"{len(self.skipped)} already present, branch {self.branch}"
        )


class HistoryError(RuntimeError):
    """A git operation the caller has to resolve, reported with what to do about it."""


def pull_history(
    *,
    data_dir: Path | None = None,
    remote: str = DEFAULT_REMOTE,
    branch: str = DATA_BRANCH,
) -> HistoryResult:
    """Copy the published captures into the local bronze layer.

    Args:
        data_dir: Root of the data lake; defaults to the configured ``AUTOVALOR_DATA_DIR``.
        remote: Remote holding the branch.
        branch: Branch carrying the history.

    Returns:
        What was copied and what was already there.

    Raises:
        HistoryError: If the branch does not exist on the remote.
    """
    root = _lake_root(data_dir)
    _fetch(remote, branch)
    with _branch_worktree() as worktree:
        result = _copy_layers(worktree, root, branch=branch)
    logger.info("pulled history: %s", result.summary())
    return result


def push_history(
    *,
    data_dir: Path | None = None,
    remote: str = DEFAULT_REMOTE,
    branch: str = DATA_BRANCH,
    message: str | None = None,
    dry_run: bool = False,
) -> HistoryResult:
    """Publish the local bronze captures to the history branch.

    Creates the branch, as an orphan with an empty root commit, the first time it is
    called. Pushes nothing when every local capture is already published.

    Args:
        data_dir: Root of the data lake; defaults to the configured ``AUTOVALOR_DATA_DIR``.
        remote: Remote to push to.
        branch: Branch carrying the history.
        message: Commit subject; defaults to one naming the UTC instant.
        dry_run: Prepare and report, then throw the commit away.

    Returns:
        What was copied, and whether a commit was made.

    Raises:
        HistoryError: If there is nothing to publish, or git refuses the push.
    """
    root = _lake_root(data_dir)
    if not (root / BRONZE_PREFIX).exists():
        msg = f"no bronze layer at {root / BRONZE_PREFIX}; run a capture first"
        raise HistoryError(msg)

    _ensure_branch(remote, branch)
    with _branch_worktree() as worktree:
        result = _copy_layers(root, worktree, branch=branch)
        if not result.copied:
            logger.info("nothing to publish: %s", result.summary())
            return result
        if dry_run:
            logger.info("dry run, not committing: %s", result.summary())
            return result

        subject = f"data: {message}" if message else f"data: captures as of {_timestamp()}"
        # Only the layers that exist: git add refuses a pathspec matching nothing, and a
        # lake with no enrichment pass yet has no detail/ at all.
        present = [prefix for prefix in PUBLISHED_PREFIXES if (worktree / prefix).is_dir()]
        _git("add", "--", *present, cwd=worktree)
        _git("commit", "--message", subject, cwd=worktree)
        _git("push", remote, f"HEAD:refs/heads/{branch}", cwd=worktree)

    logger.info("published history: %s", result.summary())
    return HistoryResult(result.copied, result.skipped, branch=branch, committed=True)


def _lake_root(data_dir: Path | None) -> Path:
    return data_dir if data_dir is not None else get_settings().data_dir


def _copy_layers(source_root: Path, destination_root: Path, *, branch: str) -> HistoryResult:
    """Copy every published layer from one lake root to another."""
    copied: list[str] = []
    skipped: list[str] = []
    for prefix in PUBLISHED_PREFIXES:
        layer = _copy_captures(source_root / prefix, destination_root / prefix, prefix=prefix)
        copied.extend(layer[0])
        skipped.extend(layer[1])
    return HistoryResult(tuple(copied), tuple(skipped), branch=branch)


def _copy_captures(source: Path, destination: Path, *, prefix: str) -> tuple[list[str], list[str]]:
    """Copy every Parquet under ``source`` into ``destination``, never overwriting."""
    if not source.exists():
        return [], []

    copied: list[str] = []
    skipped: list[str] = []
    for path in sorted(source.glob(CAPTURE_GLOB)):
        relative = f"{prefix}/{path.relative_to(source).as_posix()}"
        target = destination / path.relative_to(source)
        if target.exists():
            # Bronze is immutable and captures are named after their UTC instant, so a
            # collision is the same capture rather than a newer version of it.
            skipped.append(relative)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(relative)
    return copied, skipped


def _fetch(remote: str, branch: str) -> None:
    if not _branch_exists(remote, branch):
        msg = (
            f"{remote}/{branch} does not exist yet; seed it with "
            "'python -m autovalor.ingest.history push' (see docs/adr/"
            "0004-capture-history-storage.md)"
        )
        raise HistoryError(msg)
    _git("fetch", "--depth", "1", remote, branch)


def _branch_exists(remote: str, branch: str) -> bool:
    listing = _git("ls-remote", "--heads", remote, f"refs/heads/{branch}")
    return bool(listing.strip())


def _ensure_branch(remote: str, branch: str) -> None:
    """Create the orphan branch on the remote the first time, then fetch it."""
    if _branch_exists(remote, branch):
        _git("fetch", "--depth", "1", remote, branch)
        return

    # Built with plumbing rather than 'checkout --orphan': an empty tree committed with
    # no parent is an orphan branch, and this never touches the current working tree.
    empty_tree = _git("hash-object", "-t", "tree", "--stdin", stdin="")
    # commit-tree is plumbing and takes only the short option.
    root = _git("commit-tree", empty_tree, "-m", "data: start the capture history")
    _git("push", remote, f"{root}:refs/heads/{branch}")
    logger.info("created the %s branch on %s", branch, remote)
    _git("fetch", "--depth", "1", remote, branch)


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def _branch_worktree() -> Iterator[Path]:
    """Check ``FETCH_HEAD`` out into a throwaway worktree.

    Callers fetch the branch first; this deliberately reads ``FETCH_HEAD`` rather than a
    local ref so a stale local ``data`` branch can never be published by accident.

    A linked worktree is used rather than a second clone so the transfer costs one shallow
    fetch instead of a full copy of the repository, and so the credentials already
    configured for this checkout keep working.
    """
    with TemporaryDirectory(prefix="autovalor-history-") as directory:
        path = Path(directory) / "worktree"
        _git("worktree", "add", "--detach", str(path), "FETCH_HEAD")
        try:
            yield path
        finally:
            _git("worktree", "remove", "--force", str(path))


def _git(*args: str, cwd: Path | None = None, stdin: str | None = None) -> str:
    """Run one git command and return its stripped stdout.

    Raises:
        HistoryError: If git exits non-zero, carrying its stderr.
    """
    try:
        # A fixed argv and no shell: nothing here is interpolated into a command line.
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            input=stdin,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as error:  # pragma: no cover - git is a hard requirement
        msg = "git is not on PATH"
        raise HistoryError(msg) from error
    except subprocess.CalledProcessError as error:
        msg = f"git {' '.join(args)} failed: {error.stderr.strip()}"
        raise HistoryError(msg) from error
    return completed.stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the history command."""
    parser = argparse.ArgumentParser(
        prog="autovalor-history",
        description="Move bronze captures between the local lake and the data branch.",
    )
    parser.add_argument(
        "action",
        choices=("pull", "push"),
        help="pull brings the published captures into data/bronze; push publishes them.",
    )
    parser.add_argument(
        "--remote",
        default=DEFAULT_REMOTE,
        help=f"Remote carrying the branch (default: {DEFAULT_REMOTE}).",
    )
    parser.add_argument(
        "--branch",
        default=DATA_BRANCH,
        help=f"Branch carrying the history (default: {DATA_BRANCH}).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Root of the data lake (default: the configured AUTOVALOR_DATA_DIR).",
    )
    parser.add_argument(
        "--message",
        default=None,
        help="Commit subject for a push; defaults to one naming the UTC instant.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="For push: report what would be published without committing.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``make pull-history`` and the weekly workflow.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` on success, ``1`` when git refuses the operation.
    """
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    try:
        if args.action == "pull":
            pull_history(data_dir=args.data_dir, remote=args.remote, branch=args.branch)
        else:
            push_history(
                data_dir=args.data_dir,
                remote=args.remote,
                branch=args.branch,
                message=args.message,
                dry_run=args.dry_run,
            )
    except HistoryError as error:
        logger.error("%s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
