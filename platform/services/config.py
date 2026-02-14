"""Validated application configuration for Phase 0.

This module is the framework-agnostic source of truth for runtime settings.
It loads from `.env`, then environment variables, then code defaults.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ALLOWED_ENVIRONMENTS = {"development", "staging", "production"}
_ALLOWED_LOG_FORMATS = {"console", "json"}

# ── Module-level constants (non-env, static) ─────────────────────────
APP_NAME: str = "☀️ Solar Portfolio Manager"
APP_VERSION: str = "2.0.0"
PAGE_TITLE: str = "Solar Portfolio Manager"
PAGE_ICON: str = "☀️"
BASE_PATH: Path = Path(__file__).resolve().parent.parent
SOLAR_TOOLKIT_PATH: Path = BASE_PATH / "Solar Toolkit"
MONTHLY_REPORTING_PATH: Path = BASE_PATH / "Monthly reporting"

BRAND_COLORS: dict[str, str] = {
    "primary": "#5FBFA0",
    "secondary": "#1B4D5C",
    "accent": "#2ECC71",
    "positive": "#2ECC71",
    "negative": "#E74C3C",
    "warning": "#F39C12",
    "danger": "#E74C3C",
    "info": "#3498DB",
    "dark": "#34495E",
    "light": "#ECF0F1",
    "surface": "#FFFFFF",
    "background": "#F8F9FA",
    "border": "#DEE2E6",
    "text": "#2C3E50",
    "text_secondary": "#7F8C8D",
}

CHART_COLORS: list[str] = [
    "#5FBFA0", "#1B4D5C", "#2ECC71", "#F39C12", "#E74C3C",
    "#3498DB", "#9B59B6", "#1ABC9C", "#E67E22", "#95A5A6",
    "#34495E", "#16A085",
]


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
    jwt_secret_key: str = ""
    default_admin_password: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@ampyr.com"
    slack_webhook_url: str = ""

    # Analysis defaults
    default_fiscal_start: int = Field(default=4, description="Fiscal year start month (1-12)")
    target_availability: float = Field(default=97.0, description="Target availability %")
    default_pr_budget: float = Field(default=80.0, description="Default PR budget %")
    default_fouling_clean_days: int = Field(default=90, description="Days between fouling cleans")
    default_shading_baseline_months: int = Field(default=3, description="Shading baseline months")
    default_shading_compare_months: int = Field(default=1, description="Shading comparison months")

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

    @model_validator(mode="after")
    def validate_jwt_secret_in_production(self) -> "Settings":
        if self.environment == "production" and (
            not self.jwt_secret_key or self.jwt_secret_key == "change-me-in-production"
        ):
            raise ValueError(
                "jwt_secret_key must be set to a secure value in production"
            )
        return self

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
