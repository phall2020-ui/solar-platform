"""
Backend service layer for Solar Portfolio Manager.

Provides a scalable, protocol-based abstraction over the data layer.
Currently backed by DuckDB; designed for future migration to
PostgreSQL/TimescaleDB and Redis without changing consumer code.

Modules:
    models   – Pydantic v2 data contracts
    database – Connection pool & query interface (DuckDB / PostgreSQL)
    cache    – CacheBackend protocol with in-memory default

Note: Settings/config now lives in services.config.
"""

from services.config import get_settings
from backend.database import get_db

__all__ = ["get_settings", "get_db"]
