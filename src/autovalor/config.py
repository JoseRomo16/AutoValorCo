"""Application settings, loaded from environment variables or a local ``.env`` file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

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
