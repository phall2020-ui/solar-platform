"""Solar data ingestion framework.

Provides a unified interface for fetching solar plant data from multiple
inverter platforms, satellite services, and manual uploads.

Adapters:
    - EMIGAdapter: EMIG / Juggle Energy API (primary)
    - JuggleAdapter: Juggle Energy direct API
    - SolarGISAdapter: Satellite-derived irradiance data
    - SMAAdapter: SMA Sunny Portal / ennexOS
    - EnphaseAdapter: Enphase Enlighten API v4
    - SolarEdgeAdapter: SolarEdge Monitoring API
    - HuaweiAdapter: Huawei FusionSolar northbound API
    - FroniusAdapter: Fronius Solar.web API
    - GenericCSVAdapter: Manual CSV/Excel/Parquet upload

Orchestration:
    - IngestionCoordinator: Multi-source orchestration with fallback chains
"""

from solar_platform.ingestion.base import (
    DataSourceAdapter,
    FieldMapping,
    HealthStatus,
    Reading,
    ReadingBatch,
    SOURCE_RELIABILITY,
)
from solar_platform.ingestion.coordinator import IngestionCoordinator

__all__ = [
    # Base
    "DataSourceAdapter",
    "Reading",
    "ReadingBatch",
    "HealthStatus",
    "FieldMapping",
    "SOURCE_RELIABILITY",
    # Orchestration
    "IngestionCoordinator",
]
