"""Reading ``render.yaml`` so CI, the tests and the platform agree on one environment.

The deployment bug this module exists to stop was not in the code: the service started
locally, started in CI and died on Render, because the environment Render passes in is
written in ``render.yaml`` and nothing ever loaded that file. A blueprint is configuration
as code only if something reads it.

Two callers, deliberately the same function:

* ``tests/test_config.py`` loads :class:`~autovalor.config.Settings` with exactly these
  variables, so a value the platform will pass is proven to parse before it is pushed.
* ``.github/workflows/ci.yml`` turns them into a ``docker run --env-file``, so the image
  is started the way Render starts it.

PyYAML is a development and CI dependency, not a runtime one. That is fine: nothing in the
serving path imports this module, and the API image never reads its own blueprint.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RENDER_BLUEPRINT = PROJECT_ROOT / "render.yaml"
"""The blueprint Render reads when the repository is connected. The source of truth."""

API_SERVICE = "autovalor-api"
WEB_SERVICE = "autovalor-web"


class BlueprintError(RuntimeError):
    """Raised when the blueprint does not describe the service that was asked for."""


def load_blueprint(path: Path = RENDER_BLUEPRINT) -> dict[str, Any]:
    """Parse the blueprint.

    Args:
        path: Blueprint to read.

    Returns:
        The parsed document.

    Raises:
        BlueprintError: If the file does not exist or holds no ``services`` list.
    """
    if not path.exists():
        msg = f"{path} does not exist; the deployment blueprint is the source of truth"
        raise BlueprintError(msg)

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("services"), list):
        msg = f"{path} has no 'services' list"
        raise BlueprintError(msg)
    return document


def service(name: str, *, path: Path = RENDER_BLUEPRINT) -> dict[str, Any]:
    """Return one service's definition.

    Args:
        name: Service name as written in the blueprint.
        path: Blueprint to read.

    Returns:
        The service mapping.

    Raises:
        BlueprintError: If no service carries that name.
    """
    for candidate in load_blueprint(path)["services"]:
        if isinstance(candidate, dict) and candidate.get("name") == name:
            return candidate
    msg = f"{path} describes no service named {name!r}"
    raise BlueprintError(msg)


def service_env_vars(name: str = API_SERVICE, *, path: Path = RENDER_BLUEPRINT) -> dict[str, str]:
    """Return the literal environment a service is deployed with.

    Args:
        name: Service name as written in the blueprint.
        path: Blueprint to read.

    Returns:
        Variable name to value, in blueprint order. Entries without a literal ``value`` —
        ``sync: false`` secrets typed into the dashboard, or values taken from another
        service — are skipped rather than guessed at: there is no honest local stand-in
        for a value only the platform holds.

    Raises:
        BlueprintError: If no service carries that name.
    """
    env_vars: dict[str, str] = {}
    for entry in service(name, path=path).get("envVars") or []:
        if isinstance(entry, dict) and "key" in entry and "value" in entry:
            env_vars[str(entry["key"])] = str(entry["value"])
    return env_vars


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the blueprint reader."""
    parser = argparse.ArgumentParser(
        prog="autovalor-deploy",
        description="Print a service's environment from render.yaml as KEY=VALUE lines.",
    )
    parser.add_argument(
        "--service",
        default=API_SERVICE,
        help=f"Service name in render.yaml (default: {API_SERVICE}).",
    )
    parser.add_argument(
        "--blueprint",
        type=Path,
        default=RENDER_BLUEPRINT,
        help="Blueprint to read (default: the repository's render.yaml).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Print the service environment in ``docker run --env-file`` format.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` on success, ``1`` when the blueprint does not describe the service.
    """
    args = build_parser().parse_args(argv)
    try:
        env_vars = service_env_vars(args.service, path=args.blueprint)
    except BlueprintError as error:
        sys.stderr.write(f"{error}\n")
        return 1

    for key, value in env_vars.items():
        sys.stdout.write(f"{key}={value}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
