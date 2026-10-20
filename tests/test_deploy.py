"""Tests for the render.yaml reader.

The blueprint is the deployment's source of truth, and this module is what lets CI and the
test suite share it. If it reads the file loosely, both of them agree on the wrong
environment, so the failure modes are checked as carefully as the happy path.
"""

from pathlib import Path

import pytest

from autovalor.deploy import (
    API_SERVICE,
    WEB_SERVICE,
    BlueprintError,
    main,
    service,
    service_env_vars,
)

BLUEPRINT = """\
services:
  - type: web
    name: autovalor-api
    envVars:
      - key: AUTOVALOR_LOG_LEVEL
        value: INFO
      - key: PORT
        value: "8000"
      - key: AUTOVALOR_SECRET
        sync: false
"""


@pytest.fixture
def blueprint(tmp_path: Path) -> Path:
    path = tmp_path / "render.yaml"
    path.write_text(BLUEPRINT, encoding="utf-8")
    return path


def test_reads_the_literal_environment(blueprint: Path) -> None:
    assert service_env_vars("autovalor-api", path=blueprint) == {
        "AUTOVALOR_LOG_LEVEL": "INFO",
        "PORT": "8000",
    }


def test_a_dashboard_only_secret_is_skipped_rather_than_guessed(blueprint: Path) -> None:
    # `sync: false` means "typed into the dashboard, not in the repository". There is no
    # honest local stand-in, and inventing one would make a test pass against a value the
    # platform never sees.
    assert "AUTOVALOR_SECRET" not in service_env_vars("autovalor-api", path=blueprint)


def test_an_unknown_service_is_an_error(blueprint: Path) -> None:
    with pytest.raises(BlueprintError, match="no service named"):
        service_env_vars("autovalor-nope", path=blueprint)


def test_a_missing_blueprint_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(BlueprintError, match="does not exist"):
        service_env_vars(path=tmp_path / "absent.yaml")


def test_a_blueprint_without_services_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "render.yaml"
    path.write_text("databases: []\n", encoding="utf-8")

    with pytest.raises(BlueprintError, match="no 'services' list"):
        service_env_vars(path=path)


def test_the_cli_prints_env_file_lines(blueprint: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # The exact format `docker run --env-file` reads, which is how CI starts the image
    # with the deployment's environment.
    code = main(["--service", "autovalor-api", "--blueprint", str(blueprint)])

    assert code == 0
    assert capsys.readouterr().out == "AUTOVALOR_LOG_LEVEL=INFO\nPORT=8000\n"


def test_the_cli_fails_loudly_on_an_unknown_service(
    blueprint: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--service", "nope", "--blueprint", str(blueprint)])

    assert code == 1
    assert "no service named" in capsys.readouterr().err


def test_the_repository_blueprint_describes_the_api() -> None:
    assert service(API_SERVICE)["runtime"] == "docker"
    assert service(API_SERVICE)["healthCheckPath"] == "/health"


def test_the_blueprint_describes_the_static_site_too() -> None:
    # F4 ships two things: the API and the site that calls it. Both in one blueprint, so
    # connecting the repository once is the whole deployment.
    web = service(WEB_SERVICE)

    assert web["runtime"] == "static"
    assert web["rootDir"] == "frontend"
    assert web["staticPublishPath"] == "out"


def test_the_site_is_built_against_the_api_this_blueprint_deploys() -> None:
    # The front end bakes the API's URL in at build time, so a blueprint that points the
    # site at one service while deploying another would produce a site that cannot talk
    # to anything — and it would still deploy green.
    base_url = service_env_vars(WEB_SERVICE)["NEXT_PUBLIC_API_BASE_URL"]
    allowed = service_env_vars(API_SERVICE)["AUTOVALOR_CORS_ALLOW_ORIGINS"].split(",")

    assert base_url.startswith("https://")
    assert not base_url.endswith("/")
    # And the API has to allow the site's own origin, or every request fails in the
    # browser with a CORS error that says nothing about the cause.
    assert f"https://{WEB_SERVICE}.onrender.com" in [origin.strip() for origin in allowed]
