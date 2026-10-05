import subprocess
from pathlib import Path

import pytest

from autovalor.ingest.history import (
    BRONZE_PREFIX,
    DATA_BRANCH,
    HistoryError,
    main,
    pull_history,
    push_history,
)

PARTITION = "source=tucarro/vehicle_type=car/capture_date=2026-09-30"
"""The Hive layout the bronze writer produces, mirrored on the branch."""


def _git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return completed.stdout


def _capture(lake: Path, name: str, *, payload: bytes = b"PAR1-fake") -> Path:
    path = lake / BRONZE_PREFIX / PARTITION / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


@pytest.fixture
def clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working clone of a bare 'origin', with the process CWD inside it."""
    origin = tmp_path / "origin.git"
    _git("init", "--bare", "--initial-branch", "main", str(origin), cwd=tmp_path)

    work = tmp_path / "work"
    _git("clone", str(origin), str(work), cwd=tmp_path)
    _git("config", "user.email", "test@example.com", cwd=work)
    _git("config", "user.name", "Test", cwd=work)
    (work / "README.md").write_text("code lives here\n", encoding="utf-8")
    _git("add", "README.md", cwd=work)
    _git("commit", "--message", "initial", cwd=work)
    _git("push", "origin", "main", cwd=work)

    monkeypatch.chdir(work)
    return work


def test_pushing_creates_the_branch_and_publishes_the_captures(clone: Path) -> None:
    lake = clone / "data"
    _capture(lake, "listings_20260930T024809Z.parquet")
    _capture(lake, "listings_20260930T060127Z.parquet")

    result = push_history(data_dir=lake)

    assert result.committed
    assert len(result.copied) == 2
    published = _git("ls-tree", "-r", "--name-only", f"origin/{DATA_BRANCH}", cwd=clone)
    assert f"{BRONZE_PREFIX}/{PARTITION}/listings_20260930T024809Z.parquet" in published


def test_the_history_branch_carries_no_code(clone: Path) -> None:
    # It is an orphan branch whose root is bronze/: publishing code there would make the
    # captures a second copy of the repository.
    lake = clone / "data"
    _capture(lake, "listings_20260930T024809Z.parquet")

    push_history(data_dir=lake)

    published = _git("ls-tree", "-r", "--name-only", f"origin/{DATA_BRANCH}", cwd=clone)
    assert "README.md" not in published
    assert all(line.startswith(BRONZE_PREFIX) for line in published.splitlines())


def test_only_bronze_is_published(clone: Path) -> None:
    # Silver and gold are rebuilt from bronze with dbt, so publishing them would store a
    # derivation the transformation already defines.
    lake = clone / "data"
    _capture(lake, "listings_20260930T024809Z.parquet")
    (lake / "silver").mkdir(parents=True)
    (lake / "silver" / "listings.parquet").write_bytes(b"derived")
    (lake / "autovalor.duckdb").write_bytes(b"database")

    push_history(data_dir=lake)

    published = _git("ls-tree", "-r", "--name-only", f"origin/{DATA_BRANCH}", cwd=clone)
    assert "silver" not in published
    assert "autovalor.duckdb" not in published


def test_only_parquet_travels(clone: Path) -> None:
    lake = clone / "data"
    _capture(lake, "listings_20260930T024809Z.parquet")
    (lake / BRONZE_PREFIX / ".gitkeep").write_text("", encoding="utf-8")

    result = push_history(data_dir=lake)

    assert result.copied == (f"{PARTITION}/listings_20260930T024809Z.parquet",)


def test_pushing_twice_publishes_nothing_the_second_time(clone: Path) -> None:
    # Bronze is immutable and captures are named after their UTC instant, so a second push
    # of the same lake has nothing to add.
    lake = clone / "data"
    _capture(lake, "listings_20260930T024809Z.parquet")
    push_history(data_dir=lake)

    result = push_history(data_dir=lake)

    assert not result.committed
    assert result.copied == ()
    assert len(result.skipped) == 1


def test_a_new_capture_is_appended_to_the_existing_history(clone: Path) -> None:
    lake = clone / "data"
    _capture(lake, "listings_20260930T024809Z.parquet")
    push_history(data_dir=lake)
    _capture(lake, "listings_20261005T074500Z.parquet")

    result = push_history(data_dir=lake)

    assert result.committed
    assert result.copied == (f"{PARTITION}/listings_20261005T074500Z.parquet",)
    published = _git("ls-tree", "-r", "--name-only", f"origin/{DATA_BRANCH}", cwd=clone)
    assert len(published.splitlines()) == 2


def test_pulling_brings_the_history_into_an_empty_lake(clone: Path) -> None:
    source = clone / "data"
    _capture(source, "listings_20260930T024809Z.parquet", payload=b"original")
    push_history(data_dir=source)
    other = clone / "elsewhere"

    result = pull_history(data_dir=other)

    assert len(result.copied) == 1
    landed = other / BRONZE_PREFIX / PARTITION / "listings_20260930T024809Z.parquet"
    assert landed.read_bytes() == b"original"


def test_pulling_never_overwrites_a_local_capture(clone: Path) -> None:
    # The local file wins: bronze is written once per capture, and a pull is not a chance
    # to rewrite history.
    source = clone / "data"
    _capture(source, "listings_20260930T024809Z.parquet", payload=b"published")
    push_history(data_dir=source)
    other = clone / "elsewhere"
    _capture(other, "listings_20260930T024809Z.parquet", payload=b"local")

    result = pull_history(data_dir=other)

    assert result.copied == ()
    assert len(result.skipped) == 1
    landed = other / BRONZE_PREFIX / PARTITION / "listings_20260930T024809Z.parquet"
    assert landed.read_bytes() == b"local"


def test_pulling_without_a_published_history_says_how_to_seed_it(clone: Path) -> None:
    with pytest.raises(HistoryError, match="does not exist yet"):
        pull_history(data_dir=clone / "data")


def test_pushing_without_a_lake_fails_before_touching_git(clone: Path) -> None:
    with pytest.raises(HistoryError, match="no bronze layer"):
        push_history(data_dir=clone / "missing")


def test_a_dry_run_publishes_nothing(clone: Path) -> None:
    lake = clone / "data"
    _capture(lake, "listings_20260930T024809Z.parquet")

    result = push_history(data_dir=lake, dry_run=True)

    assert not result.committed
    assert len(result.copied) == 1
    # The branch exists, because it had to be created to compare against, but it is empty.
    published = _git("ls-tree", "-r", "--name-only", f"origin/{DATA_BRANCH}", cwd=clone)
    assert published.strip() == ""


def test_the_commit_subject_can_be_set(clone: Path) -> None:
    lake = clone / "data"
    _capture(lake, "listings_20260930T024809Z.parquet")

    push_history(data_dir=lake, message="bronze from run 42")

    subject = _git("log", "-1", "--format=%s", f"origin/{DATA_BRANCH}", cwd=clone)
    assert subject.strip() == "data: bronze from run 42"


def test_the_cli_round_trips_a_capture(clone: Path) -> None:
    lake = clone / "data"
    _capture(lake, "listings_20260930T024809Z.parquet")

    assert main(["push", "--data-dir", str(lake)]) == 0
    assert main(["pull", "--data-dir", str(clone / "elsewhere")]) == 0
    assert (clone / "elsewhere" / BRONZE_PREFIX / PARTITION).is_dir()


def test_the_cli_reports_a_git_failure_as_an_exit_code(clone: Path) -> None:
    assert main(["pull", "--data-dir", str(clone / "data")]) == 1
