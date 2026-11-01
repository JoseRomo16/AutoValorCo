"""Tests for the contract between the capture workflows and the capture code.

The workflows branch on an exit code that Python defines, and they are the one part of
the pipeline no test exercises end to end: a blocked capture on GitHub Actions cannot be
reproduced here. So what is checked is the seam. If ``BLOCKED_EXIT_CODE`` moves and the
YAML keeps testing for 3, nothing fails anywhere — the capture quietly goes back to
reporting a blocked week as an ordinary failure, which is the bug of 2026-10-26.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from autovalor.ingest.cli import BLOCKED_EXIT_CODE

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
SCRAPERS = ("capture.yml", "enrich.yml")


def load(name: str) -> dict[str, Any]:
    """Return a parsed workflow."""
    parsed = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def steps_of(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every step of the workflow's single job."""
    jobs: dict[str, Any] = workflow["jobs"]
    (job,) = jobs.values()
    steps: list[dict[str, Any]] = job["steps"]
    return steps


def scripts_of(workflow: dict[str, Any]) -> str:
    """Return every shell script in the workflow, concatenated."""
    return "\n".join(step["run"] for step in steps_of(workflow) if "run" in step)


@pytest.mark.parametrize("name", SCRAPERS)
def test_the_workflow_branches_on_the_exit_code_python_defines(name: str) -> None:
    """The seam itself: the YAML tests for the number the CLI actually returns."""
    assert f"-eq {BLOCKED_EXIT_CODE} ]" in scripts_of(load(name))


@pytest.mark.parametrize("name", SCRAPERS)
def test_a_blocked_run_does_not_go_red(name: str) -> None:
    """`exit 0` on the blocked branch is the whole point: nothing is broken."""
    after = scripts_of(load(name)).split(f"-eq {BLOCKED_EXIT_CODE} ]")[1]
    # Up to the line that closes the branch. Split on whole lines, because "fi" also
    # lives inside "verificación".
    body: list[str] = []
    for line in after.splitlines():
        if line.strip() == "fi":
            break
        body.append(line.strip())
    assert "exit 0" in body


@pytest.mark.parametrize("name", SCRAPERS)
def test_every_other_exit_code_keeps_its_meaning(name: str) -> None:
    """A capture that lost one location must still fail the job, as it did before."""
    assert 'exit "$code"' in scripts_of(load(name))


def test_the_capture_can_write_an_issue() -> None:
    """Without this permission the notice a green run cannot give is never written."""
    jobs: dict[str, Any] = load("capture.yml")["jobs"]
    (job,) = jobs.values()
    assert job["permissions"]["issues"] == "write"


def test_the_issue_is_opened_updated_and_closed_under_one_label() -> None:
    """One issue per episode. Searching by label is what stops it being one per week."""
    workflow = load("capture.yml")
    label = workflow["env"]["BLOCKED_LABEL"]
    script = scripts_of(workflow)
    assert script.count('--label "$BLOCKED_LABEL" --state open') == 2, (
        "both the blocked and the recovered path must look for the same open issue"
    )
    for command in ("gh issue create", "gh issue comment", "gh issue close"):
        assert command in script, f"{command} is missing: the issue would never {command}"
    assert label


@pytest.mark.parametrize("name", SCRAPERS)
def test_the_runner_is_pinned(name: str) -> None:
    """`ubuntu-latest` is migrating to Ubuntu 26; a scraper should not meet that by luck."""
    jobs: dict[str, Any] = load(name)["jobs"]
    (job,) = jobs.values()
    assert job["runs-on"] == "ubuntu-24.04"


def test_nothing_is_validated_or_published_without_bronze() -> None:
    """A dry run and a capture blocked on its first request both write no bronze.

    `history push` raises outright with no bronze layer, and Pandera has nothing to
    read, so these steps have to be gated on files existing rather than on the exit
    code.
    """
    guarded = {
        "Validate bronze",
        "Build silver and gold",
        "Validate silver and gold",
        "Report capture size",
        "Publish bronze to the data branch",
    }
    seen = {
        step["name"]
        for step in steps_of(load("capture.yml"))
        if step.get("name") in guarded
        and "steps.capture.outputs.captured == 'true'" in step.get("if", "")
    }
    assert seen == guarded, f"ungated: {sorted(guarded - seen)}"
