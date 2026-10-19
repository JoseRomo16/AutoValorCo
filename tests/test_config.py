"""Tests for autovalor.config."""

import typing
from pathlib import Path

import pytest

from autovalor.config import Settings, get_settings
from autovalor.deploy import API_SERVICE, service_env_vars


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("AUTOVALOR_DATA_DIR", str(tmp_path))
    return Settings(_env_file=None)


def test_reads_environment_with_prefix(settings: Settings, tmp_path: Path) -> None:
    assert settings.data_dir == tmp_path


def test_layer_directories_hang_off_data_dir(settings: Settings, tmp_path: Path) -> None:
    assert settings.bronze_dir == tmp_path / "bronze"
    assert settings.silver_dir == tmp_path / "silver"
    assert settings.gold_dir == tmp_path / "gold"


def test_scraping_defaults_are_polite() -> None:
    defaults = Settings(_env_file=None)
    assert defaults.scraper_respect_robots is True
    assert defaults.scraper_min_delay_seconds >= 1.0
    assert defaults.scraper_max_delay_seconds > defaults.scraper_min_delay_seconds
    assert "AutoValorCO" in defaults.scraper_user_agent


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


# --------------------------------------------------------------------------- #
# The CORS allow-list, in both forms a deployment actually writes it
# --------------------------------------------------------------------------- #


def test_comma_separated_origins_are_split(monkeypatch: pytest.MonkeyPatch) -> None:
    # The form a dashboard's env-var box invites, and the one that used to crash the
    # service at import time: a list field without NoDecode only accepted JSON.
    monkeypatch.setenv(
        "AUTOVALOR_CORS_ALLOW_ORIGINS",
        "https://autovalor-web.onrender.com,http://localhost:3000",
    )

    assert Settings(_env_file=None).cors_allow_origins == [
        "https://autovalor-web.onrender.com",
        "http://localhost:3000",
    ]


def test_a_json_array_of_origins_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    # Whatever is already deployed may be written this way, so the fix must not break it.
    monkeypatch.setenv(
        "AUTOVALOR_CORS_ALLOW_ORIGINS",
        '["https://autovalor-web.onrender.com", "http://localhost:3000"]',
    )

    assert Settings(_env_file=None).cors_allow_origins == [
        "https://autovalor-web.onrender.com",
        "http://localhost:3000",
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://one.example", ["https://one.example"]),
        (" https://a.example , https://b.example ", ["https://a.example", "https://b.example"]),
        ("https://a.example,,https://b.example", ["https://a.example", "https://b.example"]),
        ('["https://a.example"]', ["https://a.example"]),
        ("[]", []),
    ],
)
def test_origin_shapes(monkeypatch: pytest.MonkeyPatch, value: str, expected: list[str]) -> None:
    monkeypatch.setenv("AUTOVALOR_CORS_ALLOW_ORIGINS", value)

    assert Settings(_env_file=None).cors_allow_origins == expected


def test_a_malformed_json_allow_list_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    # Not parsed leniently on purpose: guessing at a broken allow-list would serve CORS
    # headers nobody wrote, which is a security decision taken by a typo.
    monkeypatch.setenv("AUTOVALOR_CORS_ALLOW_ORIGINS", '["https://a.example"')

    with pytest.raises(ValueError, match="does not parse"):
        Settings(_env_file=None)


def test_every_collection_setting_parses_a_plain_string(monkeypatch: pytest.MonkeyPatch) -> None:
    # The audit the review asked for, as a test rather than a one-off reading: any *other*
    # field whose type is a collection has the same latent bug, because pydantic-settings
    # JSON-decodes complex types and nothing else. If one is added without a validator,
    # this fails here instead of on the platform.
    collections = {
        name: field
        for name, field in Settings.model_fields.items()
        if typing.get_origin(field.annotation) in {list, set, tuple, dict, frozenset}
    }

    assert set(collections) == {"cors_allow_origins"}, (
        "a new collection-typed setting needs a before-validator that accepts a plain "
        f"string, like _parse_origins: {sorted(collections)}"
    )
    for name in collections:
        monkeypatch.setenv(f"AUTOVALOR_{name.upper()}", "https://one.example")
        assert getattr(Settings(_env_file=None), name) == ["https://one.example"]


# --------------------------------------------------------------------------- #
# The environment the platform will actually pass
# --------------------------------------------------------------------------- #


def test_settings_load_with_exactly_the_render_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The deployment bug this file now guards: render.yaml is the environment the service
    # runs with, and nothing used to read it, so a value that broke Settings was only
    # discovered on the platform. Loaded here from the blueprint itself, not a copy.
    env_vars = service_env_vars(API_SERVICE)
    assert env_vars, "render.yaml declares no literal env vars for the API service"

    monkeypatch.delenv("AUTOVALOR_CORS_ALLOW_ORIGINS", raising=False)
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    settings = Settings(_env_file=None)

    assert settings.log_level == env_vars["AUTOVALOR_LOG_LEVEL"]
    assert settings.cors_allow_origins == [
        origin.strip()
        for origin in env_vars["AUTOVALOR_CORS_ALLOW_ORIGINS"].split(",")
        if origin.strip()
    ]
    # Every origin has to be a usable CORS value: a browser matches the Origin header
    # against these literally, so a trailing slash or a bare host silently never matches.
    for origin in settings.cors_allow_origins:
        assert origin.startswith(("http://", "https://")), origin
        assert not origin.endswith("/"), origin


def test_render_routes_traffic_to_the_port_the_image_binds() -> None:
    # The container's CMD passes --port 8000 to uvicorn literally and reads no
    # environment, so PORT is what tells Render where to probe. If one moves, both move.
    env_vars = service_env_vars(API_SERVICE)
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile.api"

    assert env_vars["PORT"] == "8000"
    assert f'"--port", "{env_vars["PORT"]}"' in dockerfile.read_text(encoding="utf-8")
