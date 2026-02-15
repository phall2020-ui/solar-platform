"""Database abstraction layer.

All database access should go through this package.
Current backend: DuckDB. Designed for PostgreSQL/TimescaleDB migration.
"""

from solar_platform.db.engine import DatabaseEngine, DuckDBEngine, get_engine
from solar_platform.db.repository import (
    BaseRepository,
    PlantRepository,
    ReadingsRepository,
    SolarDataRepository,
)

__all__ = [
    "DatabaseEngine",
    "DuckDBEngine",
    "get_engine",
    "BaseRepository",
    "PlantRepository",
    "ReadingsRepository",
    "SolarDataRepository",
]
