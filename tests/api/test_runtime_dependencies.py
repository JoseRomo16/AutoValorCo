"""The API must import with only the dependencies the image installs.

This is the test the Docker build needed and did not have. ``Dockerfile.api`` installs
``[project.dependencies]`` and skips the ingest / transform / train / analysis groups, so
anything the serving path imports at module scope from outside that list makes the
container die on start-up — while every other test here still passes, because the
development environment has everything.

That is exactly what happened: the image built, the container exited on ``import duckdb``,
and CI only noticed because it had started curling ``/health``. The fix was to make
``load_gold`` import DuckDB lazily and to move ``FeatureSpec`` out of the
scikit-learn-importing module. This test is what keeps it fixed.

**Each check runs in a subprocess.** Blocking imports inside this interpreter would mean
clearing ``autovalor`` out of ``sys.modules`` so the import actually re-runs, and that
leaves the rest of the session holding stale module objects — which it did, breaking an
unrelated test fifteen minutes later. A fresh interpreter is both the honest simulation of
a container start-up and the only version with no side effects.
"""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

NOT_IN_THE_IMAGE = (
    # transform
    "duckdb",
    "dbt",
    "pandera",
    "pyarrow",
    # train
    "sklearn",
    "catboost",
    "optuna",
    "shap",
    "mlflow",
    # analysis
    "statsmodels",
    "matplotlib",
    # ingest
    "httpx",
    "bs4",
    "lxml",
    "playwright",
    "tenacity",
    "truststore",
)
"""Every top-level package that lives in a dependency group rather than in
``[project.dependencies]``. Checked against ``pyproject.toml`` below."""

SERVING_MODULES = (
    "autovalor.api.main",
    "autovalor.api.schemas",
    "autovalor.api.features",
    "autovalor.models.bundle",
)
"""What uvicorn ends up importing to answer a request."""

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROBE = """
import builtins, sys

blocked = set({blocked!r})
real = builtins.__import__


def guarded(name, *args, **kwargs):
    if name.split(".")[0] in blocked:
        raise ModuleNotFoundError(f"No module named {{name!r}} (not in the API image)")
    return real(name, *args, **kwargs)


builtins.__import__ = guarded
import {module}
print("ok")
"""


@pytest.mark.parametrize("module", SERVING_MODULES)
def test_the_serving_path_imports_without_the_training_stack(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", PROBE.format(blocked=NOT_IN_THE_IMAGE, module=module)],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )

    assert result.returncode == 0, (
        f"{module} cannot be imported inside the API image:\n{result.stderr}"
    )


def test_the_blocked_list_matches_the_groups_in_pyproject() -> None:
    # If a package moves from a group into [project.dependencies], or the other way, this
    # list has to move with it or the test above quietly stops checking anything.
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    grouped = {
        requirement.split(">")[0].split("[")[0].split("=")[0].strip()
        for group, requirements in pyproject["dependency-groups"].items()
        if group != "dev"
        for requirement in requirements
    }
    # Distribution names differ from import names in a few cases; map only those.
    import_names = {"beautifulsoup4": "bs4", "scikit-learn": "sklearn", "dbt-duckdb": "dbt"}
    expected = {import_names.get(name, name) for name in grouped}

    missing = sorted(expected - set(NOT_IN_THE_IMAGE))
    assert missing == [], f"grouped but not blocked by the import test: {missing}"
