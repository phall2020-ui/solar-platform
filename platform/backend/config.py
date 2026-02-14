"""
Centralized application settings using pydantic-settings.

Loads from environment variables and .env file. Every knob that may change
between environments or deployments is captured here with a sensible default.

Usage:
    from backend.config import get_settings
    settings = get_settings()
    print(settings.database_url)
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings, grouped by concern."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",            # no prefix — keys match env var names
        extra="ignore",           # ignore unknown env vars
        case_sensitive=False,
    )

    # ── Environment ─────────────────────────────────────────────────────
    environment: Literal["development", "staging", "production"] = "development"

    # ── Database ────────────────────────────────────────────────────────
    db_backend: Literal["duckdb", "postgresql"] = "duckdb"

    # DuckDB-specific
    duckdb_path: str = Field(
        default="",
        description="Path to DuckDB file. If empty, resolved from TOOLKIT_DB or default.",
    )

    # PostgreSQL / TimescaleDB (future)
    database_url: str = Field(
        default="",
        description="PostgreSQL connection string, e.g. postgresql://user:pass@host:5432/db",
    )
    db_pool_min: int = Field(default=2, ge=1)
    db_pool_max: int = Field(default=10, ge=1)

    # ── API keys ────────────────────────────────────────────────────────
    emig_api_key: str = Field(default="", alias="EMIG_API_KEY")
    juggle_api_key: str = Field(default="", alias="JUGGLE_API_KEY")
    nrel_api_key: str = Field(default="", alias="NREL_API_KEY")
    solargis_api_key: str = Field(default="", alias="SOLARGIS_API_KEY")

    # ── Feature flags ──────────────────────────────────────────────────
    feature_live_mode: bool = Field(default=True, description="Enable live auto-refresh on Site Monitor")
    feature_cached_views: bool = Field(default=False, alias="USE_CACHED_VIEWS")
    feature_background_jobs: bool = Field(default=False, alias="ENABLE_BACKGROUND_JOBS")
    feature_observability: bool = Field(default=True, alias="ENABLE_OBSERVABILITY")

    # ── Polling & refresh ──────────────────────────────────────────────
    live_poll_interval_seconds: int = Field(default=30, ge=5, le=300)
    query_cache_ttl: int = Field(default=300, ge=0, description="Cache TTL in seconds")

    # ── Alert thresholds ───────────────────────────────────────────────
    alert_pr_low: float = Field(default=0.70, description="PR below this triggers alert")
    alert_availability_low: float = Field(default=95.0, description="Availability (%) alert threshold")
    alert_data_gap_minutes: int = Field(default=60, description="Missing data gap alert threshold (min)")

    # ── Cache backend ──────────────────────────────────────────────────
    cache_backend: Literal["memory", "redis"] = "memory"
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis URL for cache")

    # ── Logging ────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"

    # ── Derived ────────────────────────────────────────────────────────
    @model_validator(mode="after")
    def _resolve_duckdb_path(self) -> "Settings":
        """If no explicit DuckDB path, fall back to the existing app default."""
        if self.db_backend == "duckdb" and not self.duckdb_path:
            import os

            # Honour the existing TOOLKIT_DB_PATH env var used by app_config
            env_path = os.getenv("TOOLKIT_DB_PATH", "")
            if env_path:
                self.duckdb_path = env_path
            else:
                # Mirror app_config.base logic
                gdrive = os.getenv("GOOGLE_DRIVE_SYNC_PATH", "")
                if gdrive and Path(gdrive).exists():
                    self.duckdb_path = str(Path(gdrive) / "plant_registry.duckdb")
                else:
                    self.duckdb_path = str(
                        Path.home() / ".solar_toolkit" / "plant_registry.duckdb"
                    )
        return self


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of application settings."""
    return Settings()
