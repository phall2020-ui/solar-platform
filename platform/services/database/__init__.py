"""Database abstraction layer.

All database access should go through this package.
Current backend: DuckDB. Designed for PostgreSQL/TimescaleDB migration.
"""

from services.database.engine import DatabaseEngine, get_engine
from services.database.repository import BaseRepository, PlantRepository, ReadingsRepository, SolarDataRepository

__all__ = [
	"DatabaseEngine",
	"get_engine",
	"BaseRepository",
	"PlantRepository",
	"ReadingsRepository",
	"SolarDataRepository",
]
