"""Tests for autovalor.config."""

from pathlib import Path

import pytest

from autovalor.config import Settings, get_settings


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
