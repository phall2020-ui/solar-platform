# Phase 0: Foundation & Infrastructure — Detailed Action Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Duration:** 1–2 weeks  
**Goal:** Establish project scaffolding, database abstraction layer, Docker multi-service setup, CI/CD, and development environment — all within the existing Streamlit architecture but designed so the service layer can be extracted to FastAPI later.

**Key Principle:** Keep Streamlit as the UI layer. Introduce a clean service/repository pattern underneath so all business logic is framework-agnostic. DuckDB stays for now but behind an abstraction that supports PostgreSQL/TimescaleDB later.

---

## Table of Contents

1. [Progress Tracker](#1-progress-tracker)
2. [Dependency Graph](#2-dependency-graph)
3. [Task 0.1: Database Abstraction Layer](#task-01-database-abstraction-layer)
4. [Task 0.2: Environment Configuration](#task-02-environment-configuration)
5. [Task 0.3: Docker Compose Multi-Service Setup](#task-03-docker-compose-multi-service-setup)
6. [Task 0.4: Project Structure Refactor](#task-04-project-structure-refactor)
7. [Task 0.5: CI/CD Pipeline](#task-05-cicd-pipeline)
8. [Task 0.6: Development Environment Setup](#task-06-development-environment-setup)
9. [Task 0.7: Data Migration Strategy](#task-07-data-migration-strategy)
10. [Task 0.8: Logging & Observability Foundation](#task-08-logging--observability-foundation)
11. [Risks](#risks)
12. [Definition of Done](#definition-of-done)

---

## 1. Progress Tracker

| Task | Status | Est Hours | Priority | Dependencies |
|------|--------|-----------|----------|--------------|
| 0.1 Database Abstraction Layer | ✅ Complete | 12 | P0 | None |
| 0.2 Environment Configuration | ✅ Complete | 4 | P0 | None |
| 0.3 Docker Compose Multi-Service | ✅ Complete | 8 | P0 | 0.2 |
| 0.4 Project Structure Refactor | ✅ Complete | 6 | P1 | 0.1 |
| 0.5 CI/CD Pipeline | ✅ Complete | 6 | P1 | 0.3, 0.4 |
| 0.6 Development Environment Setup | ✅ Complete | 4 | P0 | 0.2, 0.3 |
| 0.7 Data Migration Strategy | ✅ Complete | 8 | P1 | 0.1 |
| 0.8 Logging & Observability Foundation | ✅ Complete | 4 | P2 | 0.4 |
| **TOTAL** | | **52** | | |

---

## 2. Dependency Graph

```
┌─────────────────┐     ┌─────────────────┐
│ 0.1 DB Abstract │     │ 0.2 Env Config  │
│     Layer       │     │                 │
└────────┬────────┘     └───┬─────────┬───┘
         │                  │         │
         ▼                  ▼         ▼
┌─────────────────┐  ┌──────────┐ ┌──────────────┐
│ 0.4 Project     │  │ 0.3 Docker│ │ 0.6 Dev Env  │
│ Structure       │  │ Compose   │ │ Setup        │
└────────┬────────┘  └─────┬────┘ └──────────────┘
         │                 │
         ▼                 ▼
┌─────────────────┐  ┌──────────┐
│ 0.8 Logging &   │  │ 0.5 CI/CD│
│ Observability   │  │ Pipeline │
└─────────────────┘  └──────────┘
         │
         ▼
┌─────────────────┐
│ 0.7 Data Migr.  │
│ Strategy        │
└─────────────────┘
```

---

## Task 0.1: Database Abstraction Layer

**Goal:** Wrap all DuckDB access behind a `DatabaseEngine` abstraction so modules never call `duckdb.connect()` directly. This enables swapping DuckDB for PostgreSQL/TimescaleDB later without touching business logic.

**Estimated Hours:** 12

### Files to Create

#### `services/database/__init__.py`
```python
"""Database abstraction layer.

All database access should go through this package.
Current backend: DuckDB. Designed for PostgreSQL/TimescaleDB migration.
"""
from services.database.engine import DatabaseEngine, get_engine
from services.database.repository import BaseRepository

__all__ = ["DatabaseEngine", "get_engine", "BaseRepository"]
```

#### `services/database/engine.py`
```python
"""
Database engine abstraction.

Provides a unified interface for database operations regardless of backend.
Current: DuckDB. Future: PostgreSQL via SQLAlchemy asyncpg.

DESIGN NOTES FOR EXTRACTION:
- When migrating to PostgreSQL, replace DuckDBEngine with PostgresEngine
- Both implement the same DatabaseEngine protocol
- Repository classes stay unchanged
"""
from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

import duckdb
import pandas as pd


class DatabaseEngine(Protocol):
    """Protocol for database engines. Implement this for new backends."""

    def execute(self, query: str, params: tuple | None = None) -> list[Any]: ...
    def execute_df(self, query: str, params: tuple | None = None) -> pd.DataFrame: ...
    def table_exists(self, table_name: str) -> bool: ...
    def get_tables(self) -> list[str]: ...
    @contextmanager
    def connection(self) -> Generator: ...
    @contextmanager
    def transaction(self) -> Generator: ...


class DuckDBEngine:
    """DuckDB implementation of DatabaseEngine.
    
    Wraps the existing db_utils.py patterns with a cleaner interface.
    Handles the single-writer limitation with automatic fallback.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    @contextmanager
    def connection(self, read_only: bool = False) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Get a DuckDB connection with automatic fallback."""
        conn = None
        try:
            if read_only:
                conn = duckdb.connect(self.db_path, read_only=True)
            else:
                conn = duckdb.connect(self.db_path)
        except duckdb.ConnectionException:
            try:
                conn = duckdb.connect(self.db_path, read_only=True)
            except duckdb.ConnectionException:
                conn = duckdb.connect(
                    self.db_path, config={"access_mode": "automatic"}
                )
        try:
            yield conn
        finally:
            if conn:
                conn.close()

    @contextmanager
    def transaction(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Execute within a transaction (DuckDB auto-commits by default)."""
        with self.connection() as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                yield conn
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def execute(self, query: str, params: tuple | None = None) -> list[Any]:
        """Execute a query and return results as list of tuples."""
        with self.connection() as conn:
            if params:
                return conn.execute(query, params).fetchall()
            return conn.execute(query).fetchall()

    def execute_df(self, query: str, params: tuple | None = None) -> pd.DataFrame:
        """Execute a query and return results as DataFrame."""
        with self.connection() as conn:
            if params:
                return conn.execute(query, params).fetchdf()
            return conn.execute(query).fetchdf()

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        with self.connection(read_only=True) as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                [table_name.lower()],
            ).fetchone()
            return result[0] > 0

    def get_tables(self) -> list[str]:
        """List all tables."""
        with self.connection(read_only=True) as conn:
            result = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
            return [row[0] for row in result]

    def execute_insert(
        self, table: str, data: dict[str, Any]
    ) -> None:
        """Insert a single row. Abstracted for portability."""
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        query = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        self.execute(query, tuple(data.values()))

    def execute_upsert(
        self, table: str, data: dict[str, Any], conflict_columns: list[str]
    ) -> None:
        """Upsert a row. DuckDB supports INSERT OR REPLACE."""
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        conflict = ", ".join(conflict_columns)
        updates = ", ".join(
            f"{k} = EXCLUDED.{k}" for k in data if k not in conflict_columns
        )
        query = (
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
        )
        self.execute(query, tuple(data.values()))

    def bulk_insert_df(self, table: str, df: pd.DataFrame) -> int:
        """Bulk insert from DataFrame. Returns rows inserted."""
        with self.connection() as conn:
            conn.execute(
                f"INSERT INTO {table} SELECT * FROM df"
            )
            return len(df)


# ---------- Singleton ----------

_engines: dict[str, DuckDBEngine] = {}


def get_engine(db_path: str | Path | None = None) -> DuckDBEngine:
    """Get or create a DuckDBEngine for the given path.
    
    If no path given, uses the unified DB path from config.
    """
    if db_path is None:
        from app_config import TOOLKIT_DB
        db_path = str(TOOLKIT_DB)
    
    key = str(db_path)
    if key not in _engines:
        _engines[key] = DuckDBEngine(key)
    return _engines[key]
```

#### `services/database/repository.py`
```python
"""
Base repository pattern for data access.

All data access should go through repository classes that extend BaseRepository.
This keeps SQL isolated from UI/service code and makes the PostgreSQL migration
straightforward — just change the SQL dialect in each repository method.

DESIGN NOTES FOR EXTRACTION:
- Each repository method contains its SQL
- When migrating to PostgreSQL/SQLAlchemy, replace SQL strings with ORM queries
- The interface (method signatures, return types) stays the same
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from services.database.engine import DatabaseEngine, get_engine


class BaseRepository:
    """Base class for all repositories."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self.engine = engine or get_engine()


class PlantRepository(BaseRepository):
    """Data access for plants table."""

    def get_all(self) -> pd.DataFrame:
        return self.engine.execute_df(
            "SELECT * FROM plants ORDER BY alias"
        )

    def get_by_uid(self, plant_uid: str) -> dict[str, Any] | None:
        rows = self.engine.execute(
            "SELECT * FROM plants WHERE plant_uid = ?", (plant_uid,)
        )
        if not rows:
            return None
        # Get column names
        with self.engine.connection(read_only=True) as conn:
            cols = [
                desc[0]
                for desc in conn.execute(
                    "SELECT * FROM plants LIMIT 0"
                ).description
            ]
        return dict(zip(cols, rows[0]))

    def get_by_alias(self, alias: str) -> dict[str, Any] | None:
        rows = self.engine.execute(
            "SELECT * FROM plants WHERE alias = ?", (alias,)
        )
        if not rows:
            return None
        with self.engine.connection(read_only=True) as conn:
            cols = [
                desc[0]
                for desc in conn.execute(
                    "SELECT * FROM plants LIMIT 0"
                ).description
            ]
        return dict(zip(cols, rows[0]))

    def list_aliases(self) -> list[str]:
        rows = self.engine.execute("SELECT alias FROM plants ORDER BY alias")
        return [row[0] for row in rows]

    def list_uids(self) -> list[str]:
        rows = self.engine.execute("SELECT plant_uid FROM plants")
        return [row[0] for row in rows]

    def upsert(self, plant: dict[str, Any]) -> None:
        self.engine.execute_upsert("plants", plant, ["plant_uid"])


class ReadingsRepository(BaseRepository):
    """Data access for time-series readings."""

    def get_readings(
        self,
        plant_uid: str,
        start: datetime | None = None,
        end: datetime | None = None,
        device_id: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        conditions = ["plant_uid = ?"]
        params: list[Any] = [plant_uid]

        if start:
            conditions.append("timestamp >= ?")
            params.append(start.isoformat())
        if end:
            conditions.append("timestamp <= ?")
            params.append(end.isoformat())
        if device_id:
            conditions.append("device_id = ?")
            params.append(device_id)

        where = " AND ".join(conditions)
        query = f"SELECT * FROM readings WHERE {where} ORDER BY timestamp"
        if limit:
            query += f" LIMIT {limit}"

        return self.engine.execute_df(query, tuple(params))

    def get_latest_timestamp(self, plant_uid: str) -> datetime | None:
        rows = self.engine.execute(
            "SELECT MAX(timestamp) FROM readings WHERE plant_uid = ?",
            (plant_uid,),
        )
        if rows and rows[0][0]:
            return pd.Timestamp(rows[0][0]).to_pydatetime()
        return None

    def get_device_ids(self, plant_uid: str) -> list[str]:
        rows = self.engine.execute(
            "SELECT DISTINCT device_id FROM readings WHERE plant_uid = ?",
            (plant_uid,),
        )
        return [row[0] for row in rows if row[0]]

    def insert_batch(self, df: pd.DataFrame) -> int:
        """Insert a batch of readings. Deduplicates by timestamp+plant_uid+device_id."""
        if df.empty:
            return 0
        return self.engine.bulk_insert_df("readings", df)

    def get_row_count(self, plant_uid: str | None = None) -> int:
        if plant_uid:
            rows = self.engine.execute(
                "SELECT COUNT(*) FROM readings WHERE plant_uid = ?",
                (plant_uid,),
            )
        else:
            rows = self.engine.execute("SELECT COUNT(*) FROM readings")
        return rows[0][0]


class SolarDataRepository(BaseRepository):
    """Data access for monthly solar_data table (reporting data)."""

    def get_all(self) -> pd.DataFrame:
        return self.engine.execute_df("SELECT * FROM solar_data ORDER BY Date")

    def get_by_site(self, site: str) -> pd.DataFrame:
        return self.engine.execute_df(
            "SELECT * FROM solar_data WHERE Site = ? ORDER BY Date",
            (site,),
        )

    def get_sites(self) -> list[str]:
        rows = self.engine.execute(
            "SELECT DISTINCT Site FROM solar_data ORDER BY Site"
        )
        return [row[0] for row in rows]
```

### Files to Modify

#### Update `services/db_utils.py` — Add deprecation wrapper
Add a deprecation notice that directs callers to the new abstraction:

```python
# At the top of services/db_utils.py, add:
import warnings

def _deprecation_notice():
    warnings.warn(
        "Direct db_utils usage is deprecated. Use services.database.get_engine() instead.",
        DeprecationWarning,
        stacklevel=3,
    )
```

The existing functions remain for backward compatibility during migration but new code should use `services.database`.

### Testing Steps

1. Create `tests/test_database_engine.py`:
```python
"""Tests for database abstraction layer."""
import tempfile
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from services.database.engine import DuckDBEngine


@pytest.fixture
def test_db():
    """Create a temporary DuckDB database with test data."""
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
        db_path = f.name
    conn = duckdb.connect(db_path)
    conn.execute("""
        CREATE TABLE plants (
            plant_uid VARCHAR PRIMARY KEY,
            alias VARCHAR,
            dc_size_kw DOUBLE
        )
    """)
    conn.execute("""
        INSERT INTO plants VALUES 
        ('uid-001', 'Plant Alpha', 5000),
        ('uid-002', 'Plant Beta', 8000)
    """)
    conn.close()
    yield db_path
    Path(db_path).unlink(missing_ok=True)


def test_engine_execute(test_db):
    engine = DuckDBEngine(test_db)
    rows = engine.execute("SELECT * FROM plants")
    assert len(rows) == 2


def test_engine_execute_df(test_db):
    engine = DuckDBEngine(test_db)
    df = engine.execute_df("SELECT * FROM plants")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2


def test_engine_table_exists(test_db):
    engine = DuckDBEngine(test_db)
    assert engine.table_exists("plants") is True
    assert engine.table_exists("nonexistent") is False


def test_engine_get_tables(test_db):
    engine = DuckDBEngine(test_db)
    tables = engine.get_tables()
    assert "plants" in tables


def test_engine_transaction_commit(test_db):
    engine = DuckDBEngine(test_db)
    with engine.transaction() as conn:
        conn.execute("INSERT INTO plants VALUES ('uid-003', 'Plant Gamma', 3000)")
    rows = engine.execute("SELECT * FROM plants")
    assert len(rows) == 3


def test_engine_transaction_rollback(test_db):
    engine = DuckDBEngine(test_db)
    try:
        with engine.transaction() as conn:
            conn.execute("INSERT INTO plants VALUES ('uid-004', 'Plant Delta', 2000)")
            raise ValueError("Force rollback")
    except ValueError:
        pass
    rows = engine.execute("SELECT * FROM plants")
    assert len(rows) == 2  # Rollback means no new row
```

2. Run: `cd "/Users/peterhall/Documents/GitHub/Unified app" && python -m pytest tests/test_database_engine.py -v`

### Acceptance Criteria

- [ ] `DuckDBEngine` class passes all unit tests
- [ ] `PlantRepository` and `ReadingsRepository` can query existing data
- [ ] `get_engine()` returns a working singleton
- [ ] Existing `db_utils.py` functions still work (backward compat)
- [ ] No existing module breaks

---

## Task 0.2: Environment Configuration

**Goal:** Consolidate all configuration into a `.env`-driven pattern with validation, replacing hardcoded paths and scattered `os.getenv()` calls.

**Estimated Hours:** 4

### Files to Create

#### `.env.example`
```env
# ============================================================
# Solar Portfolio Manager — Environment Configuration
# Copy to .env and fill in values
# ============================================================

# ---------- Environment ----------
ENVIRONMENT=development  # development | staging | production

# ---------- Database ----------
# Path to unified DuckDB database (all tables in one file)
# Default: ~/.solar_toolkit/plant_registry.duckdb
UNIFIED_DB_PATH=

# Optional: Google Drive sync path for cross-device access
GOOGLE_DRIVE_SYNC_PATH=

# Future: PostgreSQL connection (Phase 0.7+)
# DATABASE_URL=postgresql://user:pass@localhost:5432/solar_platform

# ---------- API Keys ----------
# EMIG API key for inverter data
EMIG_API_KEY=
# Also accepted as JUGGLE_API_KEY for backward compatibility
JUGGLE_API_KEY=

# NREL PSM3 API key for weather data (free: https://developer.nrel.gov/)
NREL_API_KEY=DEMO_KEY

# SolarGIS API key (for satellite irradiance fallback)
SOLARGIS_API_KEY=

# ---------- Feature Flags ----------
USE_CACHED_VIEWS=false
ENABLE_BACKGROUND_JOBS=false
ENABLE_OBSERVABILITY=true

# ---------- Redis (for caching, future task queue) ----------
REDIS_URL=redis://localhost:6379/0

# ---------- Streamlit ----------
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_HEADLESS=true

# ---------- Logging ----------
LOG_LEVEL=INFO
LOG_FORMAT=console  # console | json

# ---------- Auth ----------
# Secret key for JWT token signing (generate with: python -c "import secrets; print(secrets.token_hex(32))")
JWT_SECRET_KEY=change-me-in-production
# Default admin password (only used on first run)
DEFAULT_ADMIN_PASSWORD=

# ---------- Email (for report distribution, future) ----------
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@ampyr.com

# ---------- Slack (for alert notifications, future) ----------
SLACK_WEBHOOK_URL=
```

#### `services/config.py`
```python
"""
Validated application configuration using pydantic-settings.

Single source of truth for all configuration values. Loads from:
1. .env file (if present)
2. Environment variables (override .env)
3. Defaults defined here

DESIGN NOTES FOR EXTRACTION:
- This module is framework-agnostic
- Can be used by FastAPI, Celery, CLI scripts, etc.
- No Streamlit imports
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    environment: str = Field(default="development", description="development|staging|production")

    # Database
    unified_db_path: str = Field(
        default="",
        description="Path to DuckDB file. Empty = default ~/.solar_toolkit/plant_registry.duckdb",
    )
    google_drive_sync_path: str = Field(default="", description="Google Drive sync folder")
    database_url: str = Field(
        default="",
        description="PostgreSQL URL (future). Empty = use DuckDB.",
    )

    # API Keys
    emig_api_key: str = Field(default="", description="EMIG API key")
    juggle_api_key: str = Field(default="", description="Juggle API key (legacy alias for EMIG)")
    nrel_api_key: str = Field(default="DEMO_KEY", description="NREL PSM3 API key")
    solargis_api_key: str = Field(default="", description="SolarGIS API key")

    # Feature Flags
    use_cached_views: bool = False
    enable_background_jobs: bool = False
    enable_observability: bool = True

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")

    # Streamlit
    streamlit_server_port: int = 8501

    # Logging
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="console", description="console|json")

    # Auth
    jwt_secret_key: str = Field(default="change-me-in-production")
    default_admin_password: str = Field(default="")

    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@ampyr.com"

    # Slack
    slack_webhook_url: str = ""

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    @property
    def effective_api_key(self) -> str:
        """EMIG key with Juggle fallback for backward compatibility."""
        return self.emig_api_key or self.juggle_api_key

    @property
    def db_path(self) -> Path:
        """Resolved database path with Google Drive fallback."""
        if self.unified_db_path:
            return Path(self.unified_db_path)
        if self.google_drive_sync_path:
            gd = Path(self.google_drive_sync_path)
            if gd.exists():
                return gd / "plant_registry.duckdb"
        return Path.home() / ".solar_toolkit" / "plant_registry.duckdb"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def use_postgres(self) -> bool:
        """Whether to use PostgreSQL instead of DuckDB."""
        return bool(self.database_url)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
```

### Files to Modify

- **`app_config/base.py`** — Add import of `services.config.Settings` with a note that `app_config` is deprecated in favor of `services/config.py` but remains for backward compatibility.
- **`unified_config.py`** — Add a bridge to new `Settings` so new code can use `get_settings()` while old code still uses `config.TOOLKIT_DB`.

### Testing Steps

1. Copy `.env.example` to `.env`
2. Run: `python -c "from services.config import get_settings; s = get_settings(); print(s.environment, s.db_path)"`
3. Verify `.env` overrides work: `ENVIRONMENT=staging python -c "from services.config import get_settings; print(get_settings().environment)"`

### Acceptance Criteria

- [x] `.env.example` documents every config variable
- [x] `get_settings()` returns validated config
- [x] Invalid environment values raise validation errors
- [x] Backward compatibility with `unified_config.py` preserved
- [x] All existing imports of `app_config` still work

---

## Task 0.3: Docker Compose Multi-Service Setup

**Goal:** Expand Docker Compose from single-service to a multi-service setup: Streamlit app + Redis (for caching/future task queue) + optional PostgreSQL (for future migration).

**Estimated Hours:** 8

### Files to Create

#### `docker-compose.yml` (replace existing)
```yaml
version: "3.8"

services:
  app:
    build: .
    ports:
      - "${STREAMLIT_SERVER_PORT:-8501}:8501"
    volumes:
      - .:/app
      - db-data:/app/databases
      - ./data:/app/data
    environment:
      - ENVIRONMENT=${ENVIRONMENT:-production}
      - EMIG_API_KEY=${EMIG_API_KEY:-}
      - NREL_API_KEY=${NREL_API_KEY:-}
      - SOLARGIS_API_KEY=${SOLARGIS_API_KEY:-}
      - REDIS_URL=redis://redis:6379/0
      - UNIFIED_DB_PATH=/app/databases/plant_registry.duckdb
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
    restart: unless-stopped

  # Future: Uncomment when ready to migrate from DuckDB
  # postgres:
  #   image: timescale/timescaledb:latest-pg16
  #   ports:
  #     - "5432:5432"
  #   environment:
  #     POSTGRES_USER: solar
  #     POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-solar_dev}
  #     POSTGRES_DB: solar_platform
  #   volumes:
  #     - pg-data:/var/lib/postgresql/data
  #   healthcheck:
  #     test: ["CMD-SHELL", "pg_isready -U solar"]
  #     interval: 10s
  #     timeout: 5s
  #     retries: 5
  #   restart: unless-stopped

volumes:
  db-data:
  redis-data:
  # pg-data:
```

#### `docker-compose.dev.yml` (development overrides)
```yaml
version: "3.8"

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile.dev
    volumes:
      - .:/app
    environment:
      - ENVIRONMENT=development
      - LOG_LEVEL=DEBUG
    ports:
      - "8501:8501"
    # Enable Streamlit auto-reload in dev
    command: >
      streamlit run app.py
      --server.port=8501
      --server.address=0.0.0.0
      --server.runOnSave=true
      --server.fileWatcherType=auto
```

#### `Dockerfile.dev`
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies including curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install development dependencies
RUN pip install --no-cache-dir \
    pytest>=8.0 \
    pytest-cov>=5.0 \
    ruff>=0.8 \
    mypy>=1.13 \
    pre-commit>=4.0

# Copy application code (in dev, this is overridden by volume mount)
COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

#### `Makefile`
```makefile
.PHONY: dev run test lint format docker-up docker-down docker-build clean

# Development
dev:
	streamlit run app.py --server.port=8501 --server.runOnSave=true

run:
	streamlit run app.py --server.port=8501 --server.headless=true

# Docker
docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-up-dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f app

# Testing
test:
	python -m pytest tests/ -v --tb=short

test-cov:
	python -m pytest tests/ -v --cov=services --cov=modules --cov-report=html

# Code Quality
lint:
	ruff check .
	mypy services/ --ignore-missing-imports

format:
	ruff format .
	ruff check --fix .

# Database
db-shell:
	python -c "import duckdb; conn = duckdb.connect(str(__import__('app_config').TOOLKIT_DB)); print('Tables:', [r[0] for r in conn.execute(\"SELECT table_name FROM information_schema.tables WHERE table_schema='main'\").fetchall()]); conn.close()"

db-stats:
	python scripts/db_stats.py

# Clean
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .ruff_cache .mypy_cache
```

### Files to Modify

#### Update `Dockerfile` — Add curl for healthcheck
```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
```

### Testing Steps

1. `docker compose up -d && docker compose ps` — both `app` and `redis` should be healthy
2. `curl http://localhost:8501/_stcore/health` — returns "ok"
3. `docker compose exec app python -c "import redis; r = redis.from_url('redis://redis:6379/0'); r.ping(); print('Redis OK')"` — prints "Redis OK"
4. `make test` — runs test suite

### Acceptance Criteria

- [ ] `docker compose up` starts app + redis
- [ ] App can connect to Redis
- [ ] Health checks pass for both services
- [ ] `Makefile` commands work: `make dev`, `make test`, `make lint`
- [ ] Dev compose adds auto-reload

---

## Task 0.4: Project Structure Refactor

**Goal:** Organize the codebase into a cleaner structure without breaking existing imports. Add `__init__.py` files and package markers where needed.

**Estimated Hours:** 6

### New Directory Structure

```
Unified app/
├── .env.example                 # NEW (Task 0.2)
├── .env                         # gitignored
├── .gitignore                   # UPDATE
├── Makefile                     # NEW (Task 0.3)
├── Dockerfile                   # UPDATE (Task 0.3)
├── Dockerfile.dev               # NEW (Task 0.3)
├── docker-compose.yml           # UPDATE (Task 0.3)
├── docker-compose.dev.yml       # NEW (Task 0.3)
├── app.py                       # KEEP (entry point)
├── unified_config.py            # KEEP (backward compat)
├── pyproject.toml               # UPDATE (add dev deps, ruff config)
├── requirements.txt             # UPDATE (add redis, pydantic-settings)
├── app_config/                  # KEEP (backward compat)
├── components/                  # KEEP
├── modules/                     # KEEP
├── services/
│   ├── __init__.py              # KEEP
│   ├── config.py                # NEW (Task 0.2)
│   ├── database/                # NEW (Task 0.1)
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   └── repository.py
│   ├── db_utils.py              # KEEP (deprecated, delegates to database/)
│   ├── auth_service.py          # KEEP
│   ├── api_service.py           # KEEP
│   ├── ... (all existing)
│   └── ingestion/               # CREATED in Phase 1
├── scripts/
│   ├── db_stats.py              # NEW
│   ├── migrate_to_postgres.py   # NEW (Task 0.7)
│   └── ... (existing)
├── tests/
│   ├── conftest.py              # NEW
│   ├── test_database_engine.py  # NEW (Task 0.1)
│   ├── test_config.py           # NEW (Task 0.2)
│   └── test_repositories.py    # NEW (Task 0.1)
├── styles/                      # KEEP
├── data/                        # KEEP
└── docs/                        # KEEP
```

### Files to Create

#### `tests/conftest.py`
```python
"""Shared test fixtures for the solar platform."""
import tempfile
from pathlib import Path

import duckdb
import pytest

from services.database.engine import DuckDBEngine


@pytest.fixture
def tmp_db_path():
    """Create a temporary directory for test databases."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.duckdb"


@pytest.fixture
def test_engine(tmp_db_path):
    """DuckDBEngine with empty test database."""
    # Create the database file
    conn = duckdb.connect(str(tmp_db_path))
    conn.close()
    return DuckDBEngine(str(tmp_db_path))


@pytest.fixture
def seeded_engine(tmp_db_path):
    """DuckDBEngine with seed data matching production schema."""
    conn = duckdb.connect(str(tmp_db_path))
    conn.execute("""
        CREATE TABLE plants (
            plant_uid VARCHAR PRIMARY KEY,
            alias VARCHAR,
            dc_size_kw DOUBLE,
            ac_size_kw DOUBLE,
            latitude DOUBLE,
            longitude DOUBLE,
            tilt DOUBLE,
            azimuth DOUBLE,
            timezone VARCHAR DEFAULT 'UTC'
        )
    """)
    conn.execute("""
        CREATE TABLE readings (
            timestamp TIMESTAMP,
            plant_uid VARCHAR,
            device_id VARCHAR,
            apparentPower_value DOUBLE,
            poaIrradiance_value DOUBLE,
            ambientTemperature_value DOUBLE,
            moduleTemperature_value DOUBLE
        )
    """)
    conn.execute("""
        CREATE TABLE solar_data (
            Site VARCHAR,
            Date VARCHAR,
            PR DOUBLE,
            Irradiance DOUBLE,
            Energy DOUBLE,
            Availability DOUBLE
        )
    """)
    # Seed plants
    conn.execute("""
        INSERT INTO plants (plant_uid, alias, dc_size_kw, ac_size_kw, latitude, longitude, tilt, azimuth)
        VALUES 
        ('uid-001', 'Sunny Acres', 5000, 4500, 51.5, -0.12, 30, 180),
        ('uid-002', 'Green Fields', 8000, 7200, 52.0, -1.5, 25, 190),
        ('uid-003', 'Hilltop Solar', 3000, 2700, 50.8, -2.1, 35, 175)
    """)
    conn.close()
    return DuckDBEngine(str(tmp_db_path))
```

#### `scripts/db_stats.py`
```python
"""Print database statistics for the unified DuckDB database."""
from app_config import TOOLKIT_DB
from services.database.engine import DuckDBEngine


def main():
    engine = DuckDBEngine(str(TOOLKIT_DB))
    tables = engine.get_tables()
    
    print(f"Database: {TOOLKIT_DB}")
    print(f"Tables: {len(tables)}")
    print("-" * 60)
    
    for table in sorted(tables):
        try:
            rows = engine.execute(f"SELECT COUNT(*) FROM {table}")
            count = rows[0][0]
            print(f"  {table:30s} {count:>10,} rows")
        except Exception as e:
            print(f"  {table:30s} ERROR: {e}")


if __name__ == "__main__":
    main()
```

### Files to Modify

#### Update `requirements.txt` — Add new dependencies
Add these lines:
```
pydantic-settings>=2.7.0
redis>=5.2.0
```

#### Update `pyproject.toml` — Add ruff and test config
```toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "W", "UP"]
ignore = ["E501"]  # line length handled by formatter

[tool.ruff.format]
quote-style = "double"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short"

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true
```

#### Update `.gitignore` — Add new patterns
Add:
```
.env
*.duckdb
*.duckdb.wal
__pycache__/
.pytest_cache/
.ruff_cache/
.mypy_cache/
htmlcov/
*.egg-info/
dist/
build/
.venv/
```

### Testing Steps

1. `python -m pytest tests/ -v` — all tests pass
2. `make lint` — no errors
3. `python scripts/db_stats.py` — prints table stats
4. Verify app still runs: `make dev`

### Acceptance Criteria

- [ ] All new directories have `__init__.py`
- [ ] Tests pass with `pytest`
- [ ] `ruff check .` passes
- [ ] App starts without import errors
- [ ] Existing functionality unchanged

---

## Task 0.5: CI/CD Pipeline

**Goal:** Set up GitHub Actions for automated linting, testing, and Docker build on every push/PR.

**Estimated Hours:** 6

### Files to Create

#### `.github/workflows/ci.yml`
```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install ruff
        run: pip install ruff>=0.8
      - name: Lint
        run: ruff check .
      - name: Format check
        run: ruff format --check .

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov
      - name: Run tests
        run: python -m pytest tests/ -v --tb=short --cov=services --cov-report=xml
        env:
          ENVIRONMENT: development
          UNIFIED_DB_PATH: /tmp/test_solar.duckdb
      - name: Upload coverage
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage.xml

  docker:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker image
        run: docker build -t solar-platform:test .
      - name: Test Docker image
        run: |
          docker run -d --name test-app -p 8501:8501 solar-platform:test
          sleep 10
          curl -f http://localhost:8501/_stcore/health || exit 1
          docker stop test-app
```

#### `.github/workflows/deploy.yml`
```yaml
name: Deploy

on:
  push:
    tags: ["v*"]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build and tag
        run: |
          VERSION=${GITHUB_REF#refs/tags/}
          docker build -t solar-platform:${VERSION} .
          docker tag solar-platform:${VERSION} solar-platform:latest
      - name: Push (placeholder — configure registry)
        run: echo "Configure Docker registry push here"
```

#### `.pre-commit-config.yaml`
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

### Testing Steps

1. `git add .github/ && git commit -m "Add CI pipeline"`
2. Push to GitHub — verify Actions run successfully
3. `pre-commit install && pre-commit run --all-files` — passes

### Acceptance Criteria

- [ ] CI runs on push to main/develop
- [ ] CI runs on PRs to main
- [ ] Lint, test, Docker build all pass
- [ ] Pre-commit hooks configured

---

## Task 0.6: Development Environment Setup

**Goal:** Document everything a new developer needs to get running.

**Estimated Hours:** 4

### Files to Create

#### `DEVELOPMENT.md`
```markdown
# Development Setup

## Prerequisites

- Python 3.12+
- Docker & Docker Compose
- Git

## Quick Start

1. **Clone and enter:**
   ```bash
   git clone <repo-url> "Unified app"
   cd "Unified app"
   ```

2. **Create virtual environment:**
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install pytest ruff mypy pre-commit pydantic-settings redis
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. **Run the app:**
   ```bash
   make dev
   # Or directly:
   streamlit run app.py --server.port=8501
   ```

6. **Run with Docker:**
   ```bash
   docker compose up -d
   # App at http://localhost:8501
   ```

## Common Tasks

| Task | Command |
|------|---------|
| Run app (dev mode) | `make dev` |
| Run tests | `make test` |
| Run tests with coverage | `make test-cov` |
| Lint code | `make lint` |
| Format code | `make format` |
| View DB stats | `make db-shell` |
| Docker up | `make docker-up` |
| Docker logs | `make docker-logs` |

## Project Structure

```
app.py              → Streamlit entry point, page router
unified_config.py   → Config wrapper (backward compat)
services/config.py  → New validated config (pydantic-settings)
services/database/  → DB abstraction (DuckDB now, PostgreSQL later)
services/           → Business logic (framework-agnostic)
modules/            → Streamlit page renderers
components/         → Reusable Streamlit UI components
styles/             → CSS theme and Python theme helpers
scripts/            → CLI utilities
tests/              → pytest test suite
```

## Architecture Principles

1. **Streamlit is the UI layer** — all business logic lives in `services/`
2. **Database access via repositories** — never call `duckdb.connect()` directly
3. **Configuration via `.env`** — no hardcoded secrets or paths
4. **Every feature extractable** — services can be called from FastAPI later
```

### Acceptance Criteria

- [ ] New developer can run app within 10 minutes following docs
- [ ] All `make` commands documented and working
- [ ] Project structure explanation clear

---

## Task 0.7: Data Migration Strategy

**Goal:** Design and partially implement the migration path from current DuckDB to PostgreSQL/TimescaleDB. Don't execute yet — just build the tooling.

**Estimated Hours:** 8

### Files to Create

#### `scripts/migrate_to_postgres.py`
```python
"""
Migration script: DuckDB → PostgreSQL/TimescaleDB

This script reads all data from the existing DuckDB database and inserts
it into a PostgreSQL database. It handles schema translation, data
validation, and generates a migration report.

Usage:
    python scripts/migrate_to_postgres.py --source ~/.solar_toolkit/plant_registry.duckdb \
                                          --target postgresql://solar:pass@localhost/solar_platform \
                                          --dry-run

Prerequisites:
    pip install psycopg2-binary sqlalchemy asyncpg
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd


def get_duckdb_schema(db_path: str) -> dict[str, list[dict]]:
    """Extract schema information from DuckDB."""
    conn = duckdb.connect(db_path, read_only=True)
    tables = {}
    
    table_names = [
        row[0] for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    ]
    
    for table in table_names:
        cols = conn.execute(
            f"SELECT column_name, data_type, is_nullable "
            f"FROM information_schema.columns "
            f"WHERE table_name = '{table}' AND table_schema = 'main'"
        ).fetchall()
        tables[table] = [
            {"name": c[0], "type": c[1], "nullable": c[2] == "YES"}
            for c in cols
        ]
    
    conn.close()
    return tables


def duckdb_to_pg_type(duckdb_type: str) -> str:
    """Map DuckDB types to PostgreSQL types."""
    mapping = {
        "VARCHAR": "TEXT",
        "BIGINT": "BIGINT",
        "INTEGER": "INTEGER",
        "DOUBLE": "DOUBLE PRECISION",
        "FLOAT": "REAL",
        "BOOLEAN": "BOOLEAN",
        "DATE": "DATE",
        "TIMESTAMP": "TIMESTAMPTZ",
        "TIMESTAMP WITH TIME ZONE": "TIMESTAMPTZ",
        "BLOB": "BYTEA",
        "JSON": "JSONB",
    }
    return mapping.get(duckdb_type.upper(), "TEXT")


def generate_pg_schema(tables: dict[str, list[dict]]) -> str:
    """Generate PostgreSQL CREATE TABLE statements."""
    stmts = []
    for table, cols in tables.items():
        col_defs = []
        for col in cols:
            pg_type = duckdb_to_pg_type(col["type"])
            nullable = "" if col["nullable"] else " NOT NULL"
            col_defs.append(f"    {col['name']} {pg_type}{nullable}")
        
        stmt = f"CREATE TABLE IF NOT EXISTS {table} (\n"
        stmt += ",\n".join(col_defs)
        stmt += "\n);"
        stmts.append(stmt)
    
    # Add TimescaleDB hypertable for readings
    stmts.append(
        "\n-- Convert readings to TimescaleDB hypertable\n"
        "SELECT create_hypertable('readings', 'timestamp',\n"
        "    chunk_time_interval => INTERVAL '7 days',\n"
        "    if_not_exists => TRUE\n"
        ");"
    )
    
    return "\n\n".join(stmts)


def validate_migration(source_path: str, tables: dict) -> dict:
    """Compare row counts between source and expected."""
    conn = duckdb.connect(source_path, read_only=True)
    report = {}
    
    for table in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            report[table] = {"source_rows": count, "status": "ready"}
        except Exception as e:
            report[table] = {"source_rows": 0, "status": f"error: {e}"}
    
    conn.close()
    return report


def main():
    parser = argparse.ArgumentParser(description="Migrate DuckDB to PostgreSQL")
    parser.add_argument("--source", required=True, help="Path to DuckDB file")
    parser.add_argument("--target", default="", help="PostgreSQL connection string")
    parser.add_argument("--dry-run", action="store_true", help="Generate SQL without executing")
    parser.add_argument("--output", default="migration_schema.sql", help="Output SQL file (dry-run)")
    args = parser.parse_args()
    
    if not Path(args.source).exists():
        print(f"Error: Source database not found: {args.source}")
        sys.exit(1)
    
    print(f"Analyzing source: {args.source}")
    tables = get_duckdb_schema(args.source)
    
    print(f"\nFound {len(tables)} tables:")
    report = validate_migration(args.source, tables)
    for table, info in report.items():
        print(f"  {table:30s} {info['source_rows']:>10,} rows  [{info['status']}]")
    
    if args.dry_run:
        schema_sql = generate_pg_schema(tables)
        Path(args.output).write_text(schema_sql)
        print(f"\nSchema SQL written to: {args.output}")
        print("Review and execute manually against PostgreSQL.")
    else:
        if not args.target:
            print("Error: --target required when not using --dry-run")
            sys.exit(1)
        print("\nFull migration not yet implemented. Use --dry-run for now.")


if __name__ == "__main__":
    main()
```

### Testing Steps

1. `python scripts/migrate_to_postgres.py --source ~/.solar_toolkit/plant_registry.duckdb --dry-run`
2. Inspect generated `migration_schema.sql`
3. Verify row counts match expectations from CODEBASE_REPORT (plants ~20, readings ~1.28M, solar_data ~95)

### Acceptance Criteria

- [ ] Script analyzes DuckDB schema and reports row counts
- [ ] Generated SQL valid for PostgreSQL/TimescaleDB
- [ ] Dry-run mode works without PostgreSQL installed
- [ ] Migration report generated

---

## Task 0.8: Logging & Observability Foundation

**Goal:** Standardize logging across the application using structlog with consistent formatting and context.

**Estimated Hours:** 4

### Files to Create

#### `services/logging.py`
```python
"""
Structured logging configuration.

Uses structlog for consistent, parseable logs across all services.
JSON format in production, colored console in development.

DESIGN NOTES FOR EXTRACTION:
- Framework-agnostic logging setup
- Same config works for Streamlit, FastAPI, Celery, CLI scripts
"""
from __future__ import annotations

import logging
import sys

import structlog

from services.config import get_settings


def setup_logging() -> None:
    """Configure structured logging based on environment."""
    settings = get_settings()
    
    # Determine processors based on format
    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a named logger with context."""
    return structlog.get_logger(name)
```

### Files to Modify

#### Update `app.py` — Initialize logging on startup
Add near the top, after imports:
```python
from services.logging import setup_logging
setup_logging()
```

### Testing Steps

1. `python -c "from services.logging import setup_logging, get_logger; setup_logging(); log = get_logger('test'); log.info('hello', foo='bar')"`
2. Verify colored output in development, JSON in production

### Acceptance Criteria

- [x] `get_logger("name")` available everywhere
- [x] Console rendering in dev, JSON in production
- [x] Log level configurable via `.env`
- [x] No impact on existing functionality

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Database abstraction breaks existing queries | High | Medium | Keep `db_utils.py` working during transition; migrate modules one at a time |
| Docker Compose Redis adds complexity | Low | Low | Redis is optional for Phase 0; only required for caching in Phase 1+ |
| `.env` conflicts with existing `os.getenv()` | Medium | Medium | `pydantic-settings` loads `.env` automatically; verify no conflicts with `app_config/base.py` env reads |
| CI pipeline fails on legacy code lint | Medium | High | Start ruff with lenient config (ignore E501); tighten later |
| Team unfamiliar with repository pattern | Low | Medium | Clear docs in `DEVELOPMENT.md`; pair programming sessions |

---

## Definition of Done

- [x] `services/database/engine.py` — Database abstraction working with all unit tests passing
- [x] `services/database/repository.py` — Plant, Readings, SolarData repositories functional
- [x] `services/config.py` — Pydantic settings loading from `.env`
- [x] `.env.example` — Complete and documented
- [ ] `docker-compose.yml` — App + Redis running with health checks
- [x] `Makefile` — All commands functional
- [ ] `.github/workflows/ci.yml` — CI passing on GitHub
- [x] `DEVELOPMENT.md` — New developer can set up in 10 minutes
- [x] `scripts/migrate_to_postgres.py` — Dry-run works, generates valid SQL
- [x] `services/logging.py` — Structured logging configured
- [ ] All existing functionality unchanged — app starts and all pages work
- [ ] Zero new lint errors introduced
- [x] At least 10 unit tests passing
