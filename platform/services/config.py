"""Validated application configuration for Phase 0.

This module is the framework-agnostic source of truth for runtime settings.
It loads from `.env`, then environment variables, then code defaults.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ALLOWED_ENVIRONMENTS = {"development", "staging", "production"}
_ALLOWED_LOG_FORMATS = {"console", "json"}


class Settings(BaseSettings):
    """Application settings with validation and compatibility aliases."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = Field(default="development", description="development|staging|production")

    # Database
    db_backend: str = Field(default="duckdb")
    unified_db_path: str = Field(default="")
    google_drive_sync_path: str = Field(default="")
    toolkit_db_path: str = Field(default="")
    reporting_db_path: str = Field(default="")
    database_url: str = Field(default="")

    # API keys
    emig_api_key: str = Field(default="")
    juggle_api_key: str = Field(default="")
    nrel_api_key: str = Field(default="")
    solargis_api_key: str = Field(default="")

    # Feature flags
    feature_live_mode: bool = True
    use_cached_views: bool = False
    enable_background_jobs: bool = False
    enable_observability: bool = True

    # Polling/performance
    live_poll_interval_seconds: int = 30
    query_cache_ttl: int = 300
    max_query_results: int = 10000

    # Alerts
    alert_pr_low: float = 0.70
    alert_availability_low: float = 95.0
    alert_data_gap_minutes: int = 60

    # Cache/redis
    cache_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"

    # Streamlit
    streamlit_server_port: int = 8501
    streamlit_server_headless: bool = True

    # Logging
    log_level: str = "INFO"
    log_format: str = "console"

    # Auth and integrations (future-safe)
    jwt_secret_key: str = "change-me-in-production"
    default_admin_password: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@ampyr.com"
    slack_webhook_url: str = ""

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in _ALLOWED_ENVIRONMENTS:
            allowed = ", ".join(sorted(_ALLOWED_ENVIRONMENTS))
            raise ValueError(f"environment must be one of: {allowed}")
        return normalized

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in _ALLOWED_LOG_FORMATS:
            allowed = ", ".join(sorted(_ALLOWED_LOG_FORMATS))
            raise ValueError(f"log_format must be one of: {allowed}")
        return normalized

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper().strip()

    @field_validator("live_poll_interval_seconds")
    @classmethod
    def validate_live_poll_interval(cls, value: int) -> int:
        if value < 5 or value > 300:
            raise ValueError("live_poll_interval_seconds must be between 5 and 300")
        return value

    @property
    def effective_api_key(self) -> str:
        """EMIG API key with legacy JUGGLE fallback."""
        return self.emig_api_key or self.juggle_api_key

    @property
    def db_path(self) -> Path:
        """Resolved DuckDB path with compatibility fallbacks."""
        if self.unified_db_path:
            return Path(self.unified_db_path).expanduser()

        if self.toolkit_db_path:
            return Path(self.toolkit_db_path).expanduser()

        if self.reporting_db_path:
            return Path(self.reporting_db_path).expanduser()

        if self.google_drive_sync_path:
            drive = Path(self.google_drive_sync_path).expanduser()
            if drive.exists():
                return drive / "plant_registry.duckdb"

        return Path.home() / ".solar_toolkit" / "plant_registry.duckdb"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def use_postgres(self) -> bool:
        return bool(self.database_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached validated settings object."""
    return Settings()
