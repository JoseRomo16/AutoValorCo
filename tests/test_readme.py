"""The README's figures have to match the files the site reads.

Deliberately **not** a test that greps figures out of the prose. The point of the generated
block is that there is exactly one place a number can be wrong, and a test that also
asserted "11,3 % appears somewhere in the README" would make the prose a second source of
truth — the situation the block exists to end.

So there are two kinds of test here: the renderer behaves (markers, both languages, the
locale's own separators), and the committed README equals what the renderer produces from
the committed artifacts. The second one is what fails when a retrain is not followed by
``make readme``.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from autovalor.models.bundle import ARTIFACTS_DIR, MANIFEST_NAME
from autovalor.models.dataset import VEHICLE_TYPES, VehicleType
from autovalor.readme import (
    LANGUAGES,
    README_PATH,
    ReadmeError,
    end_marker,
    load_models,
    load_results,
    render_block,
    render_readme,
    replace_block,
    start_marker,
    update,
)


@pytest.fixture(scope="module")
def models() -> dict[VehicleType, dict[str, Any]]:
    """The committed bundle manifests."""
    return load_models()


@pytest.fixture(scope="module")
def results() -> dict[str, Any]:
    """The committed result tables."""
    return load_results()


def test_the_committed_readme_matches_the_committed_artifacts() -> None:
    # The one that matters: a retrain that skips `make readme` fails here instead of
    # publishing figures the model no longer has.
    assert update(check=True), "README is out of date; run make readme"


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_language_has_its_block(lang: str) -> None:
    text = README_PATH.read_text(encoding="utf-8")

    assert text.count(start_marker(lang)) == 1
    assert text.count(end_marker(lang)) == 1
    assert text.index(start_marker(lang)) < text.index(end_marker(lang))


@pytest.mark.parametrize("lang", LANGUAGES)
def test_a_block_carries_its_own_markers(
    models: dict[VehicleType, dict[str, Any]], results: dict[str, Any], lang: str
) -> None:
    block = render_block(models, results, lang)

    assert block.startswith(start_marker(lang))
    assert block.endswith(end_marker(lang))


def test_each_language_writes_numbers_its_own_way(
    models: dict[VehicleType, dict[str, Any]], results: dict[str, Any]
) -> None:
    # A bilingual README that prints 10.3 in the Spanish half reads as machine-translated.
    spanish = render_block(models, results, "es")
    english = render_block(models, results, "en")
    mape = float(models["car"]["metrics"]["mape"]) * 100

    assert f"{mape:.1f}".replace(".", ",") in spanish
    assert f"{mape:.1f}" in english


def test_the_published_error_lands_in_the_block(
    models: dict[VehicleType, dict[str, Any]], results: dict[str, Any]
) -> None:
    # Reads the figure from the manifest rather than hard-coding it, so the assertion
    # survives a retrain while still proving the block is wired to the real file.
    block = render_block(models, results, "es")

    for vehicle_type in VEHICLE_TYPES:
        mape = float(models[vehicle_type]["metrics"]["mape"]) * 100
        assert f"{mape:.1f}".replace(".", ",") in block


def test_the_label_state_is_the_one_the_bundle_recorded(
    models: dict[VehicleType, dict[str, Any]], results: dict[str, Any]
) -> None:
    block = render_block(models, results, "en")

    for vehicle_type in VEHICLE_TYPES:
        published = models[vehicle_type]["label"]["publishes_label"]
        assert ("published" in block) if published else ("withheld" in block)


def test_regenerating_twice_changes_nothing(
    models: dict[VehicleType, dict[str, Any]], results: dict[str, Any]
) -> None:
    once = render_readme(README_PATH.read_text(encoding="utf-8"), models, results)
    twice = render_readme(once, models, results)

    assert once == twice


def test_a_missing_marker_is_an_error_rather_than_a_silent_skip() -> None:
    # Dropping a marker while editing the README would otherwise mean the figures quietly
    # stop being regenerated and start drifting again.
    with pytest.raises(ReadmeError, match="results:start:es"):
        replace_block("no markers here", "block", "es")


def test_markers_in_the_wrong_order_are_an_error() -> None:
    reversed_text = f"{end_marker('es')}\n{start_marker('es')}"

    with pytest.raises(ReadmeError, match="appears before"):
        replace_block(reversed_text, "block", "es")


def test_a_missing_bundle_names_the_command_that_writes_it(tmp_path: Path) -> None:
    with pytest.raises(ReadmeError, match="make export-model"):
        load_models(tmp_path)


def test_a_missing_results_manifest_names_its_command(tmp_path: Path) -> None:
    with pytest.raises(ReadmeError, match="make results"):
        load_results(tmp_path)


def test_check_mode_leaves_the_file_alone(tmp_path: Path) -> None:
    # `--check` runs in CI, where rewriting a tracked file would turn a failing assertion
    # into a dirty working tree.
    readme = tmp_path / "README.md"
    stale = "\n".join(f"{start_marker(lang)}\nold\n{end_marker(lang)}" for lang in LANGUAGES)
    readme.write_text(stale, encoding="utf-8")

    assert not update(readme, check=True)
    assert readme.read_text(encoding="utf-8") == stale


def test_a_bundle_without_the_new_metrics_is_reported_not_rendered(tmp_path: Path) -> None:
    # `baseline_mape` arrived with the October export. A manifest without it must fail
    # loudly here rather than render an empty cell into a published table.
    for vehicle_type in VEHICLE_TYPES:
        directory = tmp_path / vehicle_type
        directory.mkdir()
        manifest = json.loads(
            (ARTIFACTS_DIR / vehicle_type / MANIFEST_NAME).read_text(encoding="utf-8")
        )
        del manifest["metrics"]["baseline_mape"]
        (directory / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(KeyError, match="baseline_mape"):
        render_block(load_models(tmp_path), load_results(), "es")
