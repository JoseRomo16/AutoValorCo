"""Application settings, loaded from environment variables or a local ``.env`` file."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration shared by the ingestion, modeling and API layers.

    Every field maps to an environment variable prefixed with ``AUTOVALOR_``,
    for example ``AUTOVALOR_DATA_DIR``. See ``.env.example`` for the full list.
    """

    model_config = SettingsConfigDict(
        env_prefix="AUTOVALOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Paths
    data_dir: Path = PROJECT_ROOT / "data"
    duckdb_path: Path = PROJECT_ROOT / "data" / "autovalor.duckdb"

    # MLflow. A SQLite file rather than ``file:./mlruns``: MLflow 3 put the filesystem
    # tracking backend in maintenance mode and refuses it outright. SQLite keeps the
    # setup local and serverless while being a supported database backend.
    mlflow_tracking_uri: str = "sqlite:///mlflow.db"
    mlflow_experiment: str = "autovalor-baseline"

    # Scraping
    scraper_user_agent: str = (
        "AutoValorCO/0.1 (+https://github.com/JoseRomo16/AutoValorCo; research project)"
    )
    scraper_min_delay_seconds: float = 2.0
    scraper_max_delay_seconds: float = 6.0
    scraper_max_pages: int = 50
    scraper_respect_robots: bool = True
    # Verify TLS against the OS certificate store instead of certifi. Needed on
    # networks that inspect TLS (corporate proxies, some antivirus suites).
    use_system_certs: bool = False

    # API
    # Binds all interfaces so the container is reachable from the host.
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    served_model_version: str = "unreleased"

    # Origins allowed to call the API from a browser. The frontend is a static site on
    # another host, so without this it cannot reach the service at all. An allow-list
    # rather than "*": the wildcard is refused by browsers as soon as credentials are
    # involved, and naming the origins costs one environment variable.
    #
    # Either form is accepted, see the validator below:
    # AUTOVALOR_CORS_ALLOW_ORIGINS=https://autovalor-web.onrender.com,http://localhost:3000
    # AUTOVALOR_CORS_ALLOW_ORIGINS=["https://autovalor-web.onrender.com"]
    cors_allow_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # Where `make results` wrote the F3 tables that /market serves. None uses the
    # repository's docs/results, which is what ships inside the image.
    results_dir: Path | None = None

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: Any) -> Any:
        """Accept a comma-separated list as well as a JSON array.

        ``NoDecode`` on the field turns off pydantic-settings' own JSON decoding, which is
        what made this a production bug: a list field only accepted
        ``["https://a","https://b"]`` and a plain ``https://a,https://b`` — the form a
        dashboard's env-var box invites — raised a settings error at import time, so the
        service failed to start rather than starting with the wrong origins. Both forms are
        handled here, because the JSON form is what any already-deployed value looks like.

        Args:
            value: Whatever the environment, a ``.env`` file or a direct constructor call
                supplied.

        Returns:
            A list of origins, or the value unchanged when it is not a string (a list
            passed in code needs no parsing).

        Raises:
            ValueError: If the value looks like JSON but does not parse, or parses into
                something that is not an array of strings. Guessing at a malformed
                allow-list would mean serving CORS headers nobody wrote.
        """
        if not isinstance(value, str):
            return value

        text = value.strip()
        if text.startswith("["):
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError as error:
                msg = f"cors_allow_origins looks like JSON but does not parse: {error}"
                raise ValueError(msg) from error
            if not isinstance(decoded, list):
                msg = f"cors_allow_origins as JSON must be an array, got {type(decoded).__name__}"
                raise ValueError(msg)
            return [str(item).strip() for item in decoded]

        return [origin.strip() for origin in text.split(",") if origin.strip()]

    @property
    def bronze_dir(self) -> Path:
        """Immutable raw capture layer, one file per scraping run."""
        return self.data_dir / "bronze"

    @property
    def detail_dir(self) -> Path:
        """Listing-page attributes, one row per listing.

        A sibling of bronze rather than a directory inside it: the layer is bronze-grade,
        but dbt unions ``bronze/**/*.parquet`` into one source and a second schema there
        would leak null columns into silver.
        """
        return self.data_dir / "detail"

    @property
    def silver_dir(self) -> Path:
        """Cleaned and deduplicated listings."""
        return self.data_dir / "silver"

    @property
    def gold_dir(self) -> Path:
        """Analysis-ready tables consumed by models and the API."""
        return self.data_dir / "gold"


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance (also usable as a FastAPI dependency)."""
    return Settings()
