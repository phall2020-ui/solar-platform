# Phase 1: Data Layer & API Integrations — Detailed Action Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Duration:** 3–4 weeks  
**Goal:** Build a multi-source data ingestion pipeline with adapter interfaces for EMIG, Juggle, SolarGIS, SMA, Enphase, SolarEdge, Huawei, and Fronius. Design for background polling (Celery future) but run synchronously from Streamlit for now. Implement deduplication, quality scoring at ingestion, and rate limiting.

**Key Principle:** Every adapter implements the same `DataSourceAdapter` interface. Modules call the `IngestionCoordinator` — never individual adapters directly. All business logic remains in `services/` (extractable to FastAPI later).

**Prerequisite:** Phase 0 complete (database abstraction layer, config, Docker).

---

## Table of Contents

1. [Progress Tracker](#1-progress-tracker)
2. [Dependency Graph](#2-dependency-graph)
3. [Task 1.1: Adapter Interface & Base Classes](#task-11-adapter-interface--base-classes)
4. [Task 1.2: EMIG API Adapter](#task-12-emig-api-adapter)
5. [Task 1.3: Juggle API Adapter](#task-13-juggle-api-adapter)
6. [Task 1.4: SolarGIS API Adapter](#task-14-solargis-api-adapter)
7. [Task 1.5: SMA Sunny Portal Adapter](#task-15-sma-sunny-portal-adapter)
8. [Task 1.6: Enphase API Adapter](#task-16-enphase-api-adapter)
9. [Task 1.7: SolarEdge API Adapter](#task-17-solaredge-api-adapter)
10. [Task 1.8: Huawei FusionSolar Adapter](#task-18-huawei-fusionsolar-adapter)
11. [Task 1.9: Fronius Solar.web Adapter](#task-19-fronius-solarweb-adapter)
12. [Task 1.10: Ingestion Coordinator](#task-110-ingestion-coordinator)
13. [Task 1.11: Background Polling Design](#task-111-background-polling-design)
14. [Task 1.12: Data Deduplication](#task-112-data-deduplication)
15. [Task 1.13: Generic CSV/Excel Ingestion](#task-113-generic-csvexcel-ingestion)
16. [Risks](#risks)
17. [Definition of Done](#definition-of-done)

---

## 1. Progress Tracker

| Task | Status | Est Hours | Priority | Dependencies |
|------|--------|-----------|----------|--------------|
| 1.1 Adapter Interface & Base Classes | ✅ Done | 6 | P0 | Phase 0 |
| 1.2 EMIG API Adapter | ✅ Done | 8 | P0 | 1.1 |
| 1.3 Juggle API Adapter | ✅ Done | 8 | P1 | 1.1 |
| 1.4 SolarGIS API Adapter | ✅ Done | 8 | P1 | 1.1 |
| 1.5 SMA Sunny Portal Adapter | ✅ Done | 6 | P2 | 1.1 |
| 1.6 Enphase API Adapter | ✅ Done | 6 | P2 | 1.1 |
| 1.7 SolarEdge API Adapter | ✅ Done | 6 | P2 | 1.1 |
| 1.8 Huawei FusionSolar Adapter | ✅ Done | 6 | P2 | 1.1 |
| 1.9 Fronius Solar.web Adapter | ✅ Done | 6 | P2 | 1.1 |
| 1.10 Ingestion Coordinator | ✅ Done | 10 | P0 | 1.1, 1.2 |
| 1.11 Background Polling Design | ✅ Done | 4 | P1 | 1.10 |
| 1.12 Data Deduplication | ✅ Done | 4 | P0 | 1.1 |
| 1.13 Generic CSV/Excel Ingestion | ✅ Done | 6 | P1 | 1.1 |
| **TOTAL** | | **84** | | |

---

## 2. Dependency Graph

```
                    ┌───────────────────┐
                    │ 1.1 Adapter       │
                    │ Interface & Base  │
                    └────────┬──────────┘
                             │
          ┌──────────────────┼──────────────────────┐
          │                  │                      │
    ┌─────┴─────┐     ┌─────┴─────┐          ┌─────┴──────┐
    │ 1.2 EMIG  │     │ 1.3 Juggle│          │1.5–1.9     │
    │ (primary) │     │           │          │Inverter    │
    └─────┬─────┘     └─────┬─────┘          │Adapters    │
          │                 │                └─────┬──────┘
          │    ┌────────────┤                      │
          │    │  1.4 SolarGIS                     │
          │    │  (fallback)│                      │
          │    └────────────┤                      │
          ▼                 ▼                      │
    ┌─────────────────────────┐                    │
    │ 1.10 Ingestion          │◄───────────────────┘
    │ Coordinator             │
    └────────┬────────────────┘
             │
    ┌────────┼────────────┐
    │        │            │
    ▼        ▼            ▼
┌───────┐ ┌───────┐ ┌──────────┐
│ 1.11  │ │ 1.12  │ │ 1.13     │
│ Polling│ │ Dedup │ │ CSV/Excel│
│ Design│ │       │ │ Ingestion│
└───────┘ └───────┘ └──────────┘
```

---

## Task 1.1: Adapter Interface & Base Classes

**Goal:** Define the standard interface that every data source adapter must implement, plus shared models for readings, quality, and rate limiting.

**Estimated Hours:** 6

### Files to Create

#### `services/ingestion/__init__.py`
```python
"""
Data ingestion package.

Provides a uniform interface for pulling data from multiple sources
(EMIG, Juggle, SolarGIS, SMA, Enphase, SolarEdge, Huawei, Fronius)
and a coordinator that orchestrates multi-source acquisition with fallback.
"""
from services.ingestion.base import DataSourceAdapter, Reading, ReadingBatch
from services.ingestion.coordinator import IngestionCoordinator

__all__ = [
    "DataSourceAdapter",
    "Reading",
    "ReadingBatch",
    "IngestionCoordinator",
]
```

#### `services/ingestion/base.py`
```python
"""
Abstract base class for all data source adapters.

Every API integration (EMIG, Juggle, SolarGIS, etc.) must implement
DataSourceAdapter. This ensures all ingestion logic is interchangeable.

DESIGN NOTES FOR EXTRACTION:
- This module is framework-agnostic (no Streamlit imports)
- When adding FastAPI, adapters can be called from Celery tasks
- The interface stays the same regardless of caller
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Standard Reading Model ──────────────────────────────────────────

class QualityFlag(str, Enum):
    """Quality flags applied per-field."""
    MEASURED = "measured"           # Direct sensor measurement
    SATELLITE = "satellite"         # Satellite-derived
    INTERPOLATED = "interpolated"   # Gap-filled via interpolation
    ESTIMATED = "estimated"         # Modeled/expected value
    SUSPECT = "suspect"             # Failed validation check
    MISSING = "missing"             # No data available


class Reading(BaseModel):
    """Standard reading record. All adapters must map to this schema.
    
    Fields use SI units unless noted:
    - Power: kW
    - Energy: kWh
    - Irradiance: W/m²
    - Temperature: °C
    - Wind speed: m/s
    - Voltage: V
    - Current: A
    - Frequency: Hz
    """
    timestamp: datetime
    device_id: str | None = None
    
    # Power & Energy
    power_kw: float | None = None
    energy_kwh: float | None = None
    
    # Irradiance
    irradiance_poa_wm2: float | None = None
    irradiance_ghi_wm2: float | None = None
    irradiance_dhi_wm2: float | None = None
    irradiance_dni_wm2: float | None = None
    
    # Environmental
    ambient_temp_c: float | None = None
    module_temp_c: float | None = None
    wind_speed_ms: float | None = None
    
    # Electrical
    voltage_v: float | None = None
    current_a: float | None = None
    frequency_hz: float | None = None
    
    # Grid
    export_power_kw: float | None = None
    grid_limit_kw: float | None = None
    
    # Quality metadata
    quality_flags: dict[str, str] = Field(default_factory=dict)
    source: str = ""


class TimeRange(BaseModel):
    """A time range, used for gap detection."""
    start: datetime
    end: datetime
    duration_minutes: float = 0.0


class ReadingBatch(BaseModel):
    """A batch of readings from a single source for a single plant."""
    plant_uid: str
    source: str
    readings: list[Reading]
    quality_score: float = Field(ge=0.0, le=1.0, default=1.0)
    fetch_timestamp: datetime = Field(default_factory=datetime.utcnow)
    gaps: list[TimeRange] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def reading_count(self) -> int:
        return len(self.readings)

    @property
    def time_range(self) -> tuple[datetime, datetime] | None:
        if not self.readings:
            return None
        timestamps = [r.timestamp for r in self.readings]
        return min(timestamps), max(timestamps)


class HealthStatus(BaseModel):
    """Health check result for a data source."""
    source: str
    is_healthy: bool
    latency_ms: float = 0.0
    message: str = ""
    checked_at: datetime = Field(default_factory=datetime.utcnow)


class RateLimitInfo(BaseModel):
    """Rate limit status for a data source."""
    source: str
    requests_remaining: int = -1   # -1 = unknown
    requests_limit: int = -1
    reset_at: datetime | None = None
    window_seconds: int = 60


# ── Rate Limiter ────────────────────────────────────────────────────

class RateLimiter:
    """Simple token-bucket rate limiter.
    
    Usage:
        limiter = RateLimiter(max_requests=60, window_seconds=60)
        await limiter.acquire()  # blocks until a slot is available
    """
    
    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: list[float] = []
    
    def acquire(self) -> None:
        """Block until a request slot is available (synchronous)."""
        now = time.time()
        cutoff = now - self.window_seconds
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        
        if len(self._timestamps) >= self.max_requests:
            oldest = self._timestamps[0]
            sleep_time = oldest + self.window_seconds - now
            if sleep_time > 0:
                time.sleep(sleep_time)
            self._timestamps = [t for t in self._timestamps if t > time.time() - self.window_seconds]
        
        self._timestamps.append(time.time())
    
    @property
    def remaining(self) -> int:
        now = time.time()
        cutoff = now - self.window_seconds
        active = sum(1 for t in self._timestamps if t > cutoff)
        return max(0, self.max_requests - active)


# ── Abstract Adapter ───────────────────────────────────────────────

class DataSourceAdapter(ABC):
    """Abstract base class for all data source adapters.

    Every adapter (EMIG, Juggle, SolarGIS, etc.) must implement these methods.
    The IngestionCoordinator calls adapters through this interface.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Canonical name: 'emig', 'juggle', 'solargis', etc."""
        ...

    @property
    @abstractmethod
    def source_reliability(self) -> float:
        """Reliability score 0.0–1.0 for quality scoring."""
        ...

    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the data source. Returns True if successful."""
        ...

    @abstractmethod
    def fetch_readings(
        self, plant_uid: str, start: datetime, end: datetime,
        device_ids: list[str] | None = None,
    ) -> ReadingBatch:
        """Fetch readings for a plant in a time range.
        
        Args:
            plant_uid: Internal plant identifier
            start: Start of time range (inclusive)
            end: End of time range (inclusive)  
            device_ids: Optional filter for specific devices
            
        Returns:
            ReadingBatch with standardized readings
        """
        ...

    @abstractmethod
    def list_plants(self) -> list[dict[str, Any]]:
        """List available plants/sites from this source.
        
        Returns list of dicts with at least: 
        {"source_id": str, "name": str, "capacity_kw": float}
        """
        ...

    @abstractmethod
    def health_check(self) -> HealthStatus:
        """Check if this data source is accessible."""
        ...

    def get_rate_limits(self) -> RateLimitInfo:
        """Get current rate limit status. Override if the API provides this."""
        return RateLimitInfo(source=self.source_name)

    def _apply_quality_score(self, batch: ReadingBatch) -> ReadingBatch:
        """Apply the source reliability score to the batch."""
        batch.quality_score = self.source_reliability
        for reading in batch.readings:
            reading.source = self.source_name
        return batch
```

#### `services/ingestion/field_mapping.py`
```python
"""
Field mapping tables for each data source.

Each adapter uses these mappings to translate source-specific field names
to the standard Reading model fields.
"""

# ── EMIG API ────────────────────────────────────────────────────────

EMIG_FIELD_MAP = {
    "apparentPower_value": "power_kw",
    "poaIrradiance_value": "irradiance_poa_wm2",
    "ambientTemperature_value": "ambient_temp_c",
    "moduleTemperature_value": "module_temp_c",
    "dcVoltage_value": "voltage_v",
    "dcCurrent_value": "current_a",
    "activePower_value": "export_power_kw",
    "frequency_value": "frequency_hz",
    "windSpeed_value": "wind_speed_ms",
    "globalHorizontalIrradiance_value": "irradiance_ghi_wm2",
}

# EMIG units: power in kW, irradiance in W/m², temperature in °C
EMIG_UNIT_CONVERSIONS = {
    # No conversions needed — EMIG already uses standard units
}


# ── SolarGIS ────────────────────────────────────────────────────────

SOLARGIS_FIELD_MAP = {
    "GHI": "irradiance_ghi_wm2",
    "DNI": "irradiance_dni_wm2",
    "DHI": "irradiance_dhi_wm2",
    "GTI": "irradiance_poa_wm2",    # Global Tilted Irradiance ≈ POA
    "TEMP": "ambient_temp_c",
    "WS": "wind_speed_ms",
    "PVOUT": "power_kw",            # Modeled PV output (if available)
}


# ── SMA Sunny Portal ───────────────────────────────────────────────

SMA_FIELD_MAP = {
    "TotWhOut": "energy_kwh",        # Total energy output (Wh → kWh)
    "GridMs.TotW": "power_kw",       # Grid feed-in power (W → kW)
    "GridMs.W.phsA": "power_kw",     # Phase A power
    "Pac": "power_kw",               # AC power (W → kW)
    "DcMs.Vol": "voltage_v",         # DC voltage
    "DcMs.Amp": "current_a",         # DC current
    "GridMs.Hz": "frequency_hz",
    "Env.TmpMdul.C": "module_temp_c",
    "Env.TmpAmb.C": "ambient_temp_c",
    "SunIntens": "irradiance_poa_wm2",
}

SMA_UNIT_CONVERSIONS = {
    "energy_kwh": {"from": "Wh", "factor": 0.001},     # Wh → kWh
    "power_kw": {"from": "W", "factor": 0.001},         # W → kW
}


# ── Enphase ─────────────────────────────────────────────────────────

ENPHASE_FIELD_MAP = {
    "powr": "power_kw",              # W → kW
    "enwh": "energy_kwh",            # Wh → kWh
    "dcv": "voltage_v",              # DC voltage
    "dci": "current_a",              # DC current
    "acv": "voltage_v",              # AC voltage (choose DC or AC)
    "freq": "frequency_hz",
}

ENPHASE_UNIT_CONVERSIONS = {
    "power_kw": {"from": "W", "factor": 0.001},
    "energy_kwh": {"from": "Wh", "factor": 0.001},
}


# ── SolarEdge ───────────────────────────────────────────────────────

SOLAREDGE_FIELD_MAP = {
    "value": "power_kw",              # Power in W → kW
    "voltage": "voltage_v",
    "current": "current_a",
    "temperature": "module_temp_c",
}

SOLAREDGE_UNIT_CONVERSIONS = {
    "power_kw": {"from": "W", "factor": 0.001},
}


# ── Huawei FusionSolar ──────────────────────────────────────────────

HUAWEI_FIELD_MAP = {
    "active_power": "power_kw",       # Already kW
    "day_cap": "energy_kwh",          # Daily energy kWh
    "pv_input_voltage": "voltage_v",
    "pv_input_current": "current_a",
    "temperature": "module_temp_c",
    "power_factor": None,             # Not mapped
    "efficiency": None,               # Not mapped
    "inverter_state": None,           # Metadata only
}


# ── Fronius Solar.web ───────────────────────────────────────────────

FRONIUS_FIELD_MAP = {
    "PAC": "power_kw",                # W → kW
    "DAY_ENERGY": "energy_kwh",       # Wh → kWh
    "TOTAL_ENERGY": None,             # Cumulative (derive interval energy)
    "UDC": "voltage_v",               # DC voltage
    "IDC": "current_a",               # DC current
    "UAC": None,                      # AC voltage (not standard field)
    "IAC": None,                      # AC current
    "FAC": "frequency_hz",
}

FRONIUS_UNIT_CONVERSIONS = {
    "power_kw": {"from": "W", "factor": 0.001},
    "energy_kwh": {"from": "Wh", "factor": 0.001},
}


# ── Juggle ──────────────────────────────────────────────────────────

JUGGLE_FIELD_MAP = {
    # Juggle uses configurable virtual meter names — these are common defaults
    "power": "power_kw",
    "energy": "energy_kwh",
    "irradiance": "irradiance_poa_wm2",
    "ambient_temperature": "ambient_temp_c",
    "module_temperature": "module_temp_c",
    "wind_speed": "wind_speed_ms",
    "voltage": "voltage_v",
    "current": "current_a",
    "grid_power": "export_power_kw",
}


def apply_unit_conversions(
    reading_dict: dict, conversions: dict[str, dict]
) -> dict:
    """Apply unit conversions to a reading dictionary.
    
    Args:
        reading_dict: Dict with standard field names and raw values
        conversions: Map of field_name → {"from": unit, "factor": float}
    
    Returns:
        Dict with converted values
    """
    for field, conv in conversions.items():
        if field in reading_dict and reading_dict[field] is not None:
            reading_dict[field] = reading_dict[field] * conv["factor"]
    return reading_dict
```

### Testing Steps

```bash
cd "/Users/peterhall/Documents/GitHub/Unified app"
python -m pytest tests/test_ingestion_base.py -v
```

Create `tests/test_ingestion_base.py`:
```python
"""Tests for ingestion base classes."""
from datetime import datetime

from services.ingestion.base import (
    DataSourceAdapter,
    HealthStatus,
    RateLimiter,
    Reading,
    ReadingBatch,
    TimeRange,
)


def test_reading_model():
    r = Reading(
        timestamp=datetime(2025, 6, 15, 12, 0),
        device_id="INV-01",
        power_kw=450.5,
        irradiance_poa_wm2=850.0,
        ambient_temp_c=25.0,
    )
    assert r.power_kw == 450.5
    assert r.source == ""


def test_reading_batch():
    readings = [
        Reading(timestamp=datetime(2025, 6, 15, 12, 0), power_kw=100),
        Reading(timestamp=datetime(2025, 6, 15, 12, 5), power_kw=110),
    ]
    batch = ReadingBatch(
        plant_uid="uid-001",
        source="emig",
        readings=readings,
        quality_score=0.95,
    )
    assert batch.reading_count == 2
    assert batch.time_range is not None


def test_rate_limiter():
    limiter = RateLimiter(max_requests=5, window_seconds=1)
    for _ in range(5):
        limiter.acquire()
    assert limiter.remaining == 0
```

### Acceptance Criteria

- [ ] `Reading`, `ReadingBatch`, `TimeRange` models validate correctly
- [ ] `DataSourceAdapter` cannot be instantiated directly (ABC)
- [ ] `RateLimiter` correctly throttles requests
- [ ] Field mapping dicts cover all known fields per platform
- [ ] Unit conversion function works for W→kW, Wh→kWh

---

## Task 1.2: EMIG API Adapter

**Goal:** Migrate the existing EMIG integration from `Solar Toolkit/emig_api.py` + `services/toolkit_bridge.py` into a clean adapter implementing `DataSourceAdapter`.

**Estimated Hours:** 8

### Authentication

- **Method:** API Key in HTTP header (`X-Api-Key`)
- **Config:** `EMIG_API_KEY` environment variable
- **Rate Limit:** Conservative 60 requests/minute (undocumented — be safe)

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/plants` | GET | List available plants |
| `/api/v1/plants/{uid}/readings` | GET | Fetch time-series readings |
| `/api/v1/plants/{uid}/devices` | GET | List devices (inverters, meters) |

### Files to Create

#### `services/ingestion/emig.py`
```python
"""
EMIG API adapter.

Migrated from Solar Toolkit/emig_api.py with clean interface.
Uses requests (sync) for now; designed for httpx (async) migration.

Authentication: API key in X-Api-Key header.
Resolution: 5-minute intervals.
Existing data: ~1.28M readings rows in DuckDB.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import requests
import structlog

from services.config import get_settings
from services.ingestion.base import (
    DataSourceAdapter,
    HealthStatus,
    RateLimiter,
    Reading,
    ReadingBatch,
    TimeRange,
)
from services.ingestion.field_mapping import EMIG_FIELD_MAP

logger = structlog.get_logger("ingestion.emig")

# Base URL — adjust if EMIG provides different environments
EMIG_BASE_URL = "https://api.emig.io/api/v1"


class EmigAdapter(DataSourceAdapter):
    """EMIG API data source adapter."""

    def __init__(self, api_key: str | None = None, base_url: str = EMIG_BASE_URL):
        self._api_key = api_key or get_settings().effective_api_key
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({
            "X-Api-Key": self._api_key,
            "Accept": "application/json",
        })
        self._rate_limiter = RateLimiter(max_requests=60, window_seconds=60)

    @property
    def source_name(self) -> str:
        return "emig"

    @property
    def source_reliability(self) -> float:
        return 0.95  # Direct inverter API

    def authenticate(self) -> bool:
        """Verify API key by listing plants."""
        try:
            resp = self._request("GET", "/plants", params={"limit": 1})
            return resp.status_code == 200
        except Exception as e:
            logger.error("emig_auth_failed", error=str(e))
            return False

    def fetch_readings(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
        device_ids: list[str] | None = None,
    ) -> ReadingBatch:
        """Fetch readings from EMIG API.
        
        Handles pagination automatically. Maps EMIG field names to standard schema.
        """
        all_readings: list[Reading] = []
        page = 1
        has_more = True

        while has_more:
            params = {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "page": page,
                "limit": 1000,
            }
            if device_ids:
                params["device_ids"] = ",".join(device_ids)

            try:
                resp = self._request("GET", f"/plants/{plant_uid}/readings", params=params)
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                logger.error("emig_fetch_failed", plant_uid=plant_uid, page=page, error=str(e))
                break

            rows = data.get("data", data.get("readings", []))
            if not rows:
                break

            for row in rows:
                reading = self._map_reading(row)
                if reading:
                    all_readings.append(reading)

            # Pagination
            has_more = len(rows) >= 1000
            page += 1

        batch = ReadingBatch(
            plant_uid=plant_uid,
            source=self.source_name,
            readings=all_readings,
        )
        return self._apply_quality_score(batch)

    def list_plants(self) -> list[dict[str, Any]]:
        """List available plants from EMIG."""
        try:
            resp = self._request("GET", "/plants")
            resp.raise_for_status()
            data = resp.json()
            plants = data.get("data", data.get("plants", []))
            return [
                {
                    "source_id": p.get("uid", p.get("id", "")),
                    "name": p.get("name", p.get("alias", "")),
                    "capacity_kw": p.get("capacity_kw", 0),
                }
                for p in plants
            ]
        except requests.RequestException as e:
            logger.error("emig_list_plants_failed", error=str(e))
            return []

    def health_check(self) -> HealthStatus:
        """Check EMIG API availability."""
        start = time.time()
        try:
            resp = self._request("GET", "/plants", params={"limit": 1})
            latency = (time.time() - start) * 1000
            return HealthStatus(
                source=self.source_name,
                is_healthy=resp.status_code == 200,
                latency_ms=latency,
                message=f"HTTP {resp.status_code}",
            )
        except Exception as e:
            return HealthStatus(
                source=self.source_name,
                is_healthy=False,
                latency_ms=(time.time() - start) * 1000,
                message=str(e),
            )

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make a rate-limited request to EMIG API."""
        self._rate_limiter.acquire()
        url = f"{self._base_url}{path}"
        logger.debug("emig_request", method=method, url=url)
        return self._session.request(method, url, timeout=30, **kwargs)

    def _map_reading(self, raw: dict) -> Reading | None:
        """Map EMIG API response row to standard Reading."""
        timestamp_str = raw.get("timestamp") or raw.get("date") or raw.get("time")
        if not timestamp_str:
            return None

        try:
            ts = datetime.fromisoformat(str(timestamp_str).replace("Z", "+00:00"))
        except ValueError:
            return None

        # Map fields using the field mapping table
        mapped: dict[str, Any] = {"timestamp": ts}
        mapped["device_id"] = raw.get("device_id") or raw.get("inverter_id")

        for emig_field, standard_field in EMIG_FIELD_MAP.items():
            value = raw.get(emig_field)
            if value is not None:
                try:
                    mapped[standard_field] = float(value)
                except (ValueError, TypeError):
                    pass

        return Reading(**mapped)
```

### Example API Response (Realistic Mock)

```json
{
    "data": [
        {
            "timestamp": "2025-06-15T12:00:00Z",
            "device_id": "INV-001",
            "apparentPower_value": 450.2,
            "poaIrradiance_value": 872.5,
            "ambientTemperature_value": 24.3,
            "moduleTemperature_value": 41.7,
            "dcVoltage_value": 620.1,
            "dcCurrent_value": 14.8,
            "activePower_value": 445.0,
            "frequency_value": 50.01
        },
        {
            "timestamp": "2025-06-15T12:05:00Z",
            "device_id": "INV-001",
            "apparentPower_value": 455.8,
            "poaIrradiance_value": 891.2,
            "ambientTemperature_value": 24.5,
            "moduleTemperature_value": 42.1,
            "dcVoltage_value": 621.3,
            "dcCurrent_value": 15.0,
            "activePower_value": 450.2,
            "frequency_value": 49.99
        }
    ],
    "pagination": {
        "page": 1,
        "limit": 1000,
        "total": 2
    }
}
```

### Error Handling

| HTTP Status | Meaning | Action |
|-------------|---------|--------|
| 200 | Success | Process data |
| 401 | Unauthorized | Log error, mark adapter unhealthy |
| 429 | Rate limited | Back off, retry after `Retry-After` header |
| 500 | Server error | Retry with exponential backoff (3 retries) |
| Timeout | No response | Retry once, then skip |

### Testing

```python
# tests/test_emig_adapter.py
"""Tests for EMIG adapter with mocked API responses."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from services.ingestion.emig import EmigAdapter


@pytest.fixture
def adapter():
    return EmigAdapter(api_key="test-key", base_url="https://mock.emig.io/api/v1")


def test_source_name(adapter):
    assert adapter.source_name == "emig"
    assert adapter.source_reliability == 0.95


def test_map_reading(adapter):
    raw = {
        "timestamp": "2025-06-15T12:00:00Z",
        "device_id": "INV-001",
        "apparentPower_value": 450.2,
        "poaIrradiance_value": 872.5,
        "ambientTemperature_value": 24.3,
    }
    reading = adapter._map_reading(raw)
    assert reading is not None
    assert reading.power_kw == 450.2
    assert reading.irradiance_poa_wm2 == 872.5
    assert reading.ambient_temp_c == 24.3


@patch("services.ingestion.emig.EmigAdapter._request")
def test_health_check(mock_request, adapter):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_request.return_value = mock_resp
    
    status = adapter.health_check()
    assert status.is_healthy is True
```

### Acceptance Criteria

- [ ] `EmigAdapter` implements full `DataSourceAdapter` interface
- [ ] Field mapping matches existing `Solar Toolkit/emig_api.py` behavior
- [ ] Pagination handled automatically
- [ ] Rate limiter prevents > 60 req/min
- [ ] Health check works
- [ ] Unit tests pass with mocked API

---

## Task 1.3: Juggle API Adapter

**Goal:** Create adapter for Juggle aggregation platform.

**Estimated Hours:** 8

### Authentication

- **Method:** OAuth2 Bearer Token or API Key (platform-dependent)
- **Config:** `JUGGLE_API_KEY` environment variable
- **Rate Limit:** TBD — implement conservative 30 requests/minute

### API Endpoints (Expected)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/sites` | GET | List monitoring sites |
| `/api/sites/{id}/data` | GET | Fetch time-series data |
| `/api/sites/{id}/devices` | GET | List devices and virtual meters |
| `/api/sites/{id}/alarms` | GET | Active alarm feed |

### Files to Create

#### `services/ingestion/juggle.py`
```python
"""
Juggle API adapter.

Juggle is a data aggregation platform that collects from multiple OEMs.
It provides virtual meters and device tree navigation.

Authentication: API key or OAuth2 (configurable).
Resolution: Configurable (typically 5-15 minute).

NOTE: Juggle API documentation may vary by installation.
      This adapter uses common REST patterns — adjust endpoints as needed.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import requests
import structlog

from services.config import get_settings
from services.ingestion.base import (
    DataSourceAdapter,
    HealthStatus,
    RateLimiter,
    Reading,
    ReadingBatch,
)
from services.ingestion.field_mapping import JUGGLE_FIELD_MAP

logger = structlog.get_logger("ingestion.juggle")


class JuggleAdapter(DataSourceAdapter):
    """Juggle aggregation platform data source adapter."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.juggle.io/api/v1",
    ):
        self._api_key = api_key or get_settings().juggle_api_key
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        })
        self._rate_limiter = RateLimiter(max_requests=30, window_seconds=60)

    @property
    def source_name(self) -> str:
        return "juggle"

    @property
    def source_reliability(self) -> float:
        return 0.90  # Aggregator — slight reliability reduction

    def authenticate(self) -> bool:
        try:
            resp = self._request("GET", "/sites", params={"limit": 1})
            return resp.status_code == 200
        except Exception:
            return False

    def fetch_readings(
        self, plant_uid: str, start: datetime, end: datetime,
        device_ids: list[str] | None = None,
    ) -> ReadingBatch:
        readings: list[Reading] = []
        try:
            params = {
                "from": start.isoformat(),
                "to": end.isoformat(),
                "resolution": "5min",
            }
            resp = self._request("GET", f"/sites/{plant_uid}/data", params=params)
            resp.raise_for_status()
            data = resp.json()

            for row in data.get("data", []):
                reading = self._map_reading(row)
                if reading:
                    readings.append(reading)

        except requests.RequestException as e:
            logger.error("juggle_fetch_failed", plant_uid=plant_uid, error=str(e))

        batch = ReadingBatch(plant_uid=plant_uid, source=self.source_name, readings=readings)
        return self._apply_quality_score(batch)

    def list_plants(self) -> list[dict[str, Any]]:
        try:
            resp = self._request("GET", "/sites")
            resp.raise_for_status()
            return [
                {"source_id": s["id"], "name": s["name"], "capacity_kw": s.get("capacity", 0)}
                for s in resp.json().get("sites", [])
            ]
        except Exception:
            return []

    def health_check(self) -> HealthStatus:
        start = time.time()
        try:
            resp = self._request("GET", "/sites", params={"limit": 1})
            return HealthStatus(
                source=self.source_name,
                is_healthy=resp.status_code == 200,
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return HealthStatus(source=self.source_name, is_healthy=False, message=str(e))

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        self._rate_limiter.acquire()
        return self._session.request(method, f"{self._base_url}{path}", timeout=30, **kwargs)

    def _map_reading(self, raw: dict) -> Reading | None:
        ts_str = raw.get("timestamp")
        if not ts_str:
            return None
        try:
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        except ValueError:
            return None

        mapped: dict[str, Any] = {"timestamp": ts, "device_id": raw.get("device_id")}
        for src_field, std_field in JUGGLE_FIELD_MAP.items():
            val = raw.get(src_field)
            if val is not None:
                try:
                    mapped[std_field] = float(val)
                except (ValueError, TypeError):
                    pass
        return Reading(**mapped)
```

### Acceptance Criteria

- [ ] `JuggleAdapter` implements `DataSourceAdapter`
- [ ] Virtual meter data handled
- [ ] Rate limiter at 30 req/min
- [ ] Mock tests pass

---

## Task 1.4: SolarGIS API Adapter

**Goal:** Integrate SolarGIS Monitor API for satellite-derived irradiance data. This is the critical fallback source when site sensors have gaps.

**Estimated Hours:** 8

### Authentication

- **Method:** API Key in query parameter or header
- **Config:** `SOLARGIS_API_KEY` environment variable
- **Rate Limit:** ~1000 requests/day (standard plan)
- **Resolution:** 15-minute data

### Key Role

SolarGIS provides **gap-free irradiance data** from satellite imagery. It serves as:
1. Fallback irradiance when site sensors are offline
2. Validation reference for on-site pyranometer calibration
3. Independent weather data for analysis modules

### Files to Create

#### `services/ingestion/solargis.py`
```python
"""
SolarGIS API adapter.

Provides satellite-derived irradiance data for gap filling and validation.
Quality score: 0.85 (satellite-derived, validated but modeled).

SolarGIS Monitor API provides:
- GHI, DNI, DHI, GTI (tilted = POA)
- Ambient temperature
- Wind speed
- 15-minute resolution
- 99% global coverage

This is the PRIMARY FALLBACK source for irradiance data.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import requests
import structlog

from services.config import get_settings
from services.ingestion.base import (
    DataSourceAdapter,
    HealthStatus,
    RateLimiter,
    Reading,
    ReadingBatch,
)
from services.ingestion.field_mapping import SOLARGIS_FIELD_MAP

logger = structlog.get_logger("ingestion.solargis")

SOLARGIS_BASE_URL = "https://api.solargis.com/v1"


class SolarGISAdapter(DataSourceAdapter):
    """SolarGIS satellite irradiance data adapter."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or get_settings().solargis_api_key
        self._session = requests.Session()
        self._session.headers.update({
            "X-Api-Key": self._api_key,
            "Accept": "application/json",
        })
        # 1000 requests/day ≈ 0.7 requests/minute
        self._rate_limiter = RateLimiter(max_requests=40, window_seconds=3600)

    @property
    def source_name(self) -> str:
        return "solargis"

    @property
    def source_reliability(self) -> float:
        return 0.85  # Satellite-derived, validated but modeled

    def authenticate(self) -> bool:
        if not self._api_key:
            return False
        return self.health_check().is_healthy

    def fetch_readings(
        self, plant_uid: str, start: datetime, end: datetime,
        device_ids: list[str] | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> ReadingBatch:
        """Fetch satellite irradiance for a location.
        
        SolarGIS requires coordinates, not plant UIDs. The coordinator
        should pass latitude/longitude from the plant registry.
        """
        readings: list[Reading] = []
        
        if latitude is None or longitude is None:
            logger.warning("solargis_no_coordinates", plant_uid=plant_uid)
            return ReadingBatch(plant_uid=plant_uid, source=self.source_name, readings=[])

        try:
            params = {
                "lat": latitude,
                "lng": longitude,
                "from": start.strftime("%Y-%m-%d"),
                "to": end.strftime("%Y-%m-%d"),
                "resolution": "PT15M",  # 15-minute intervals
                "parameters": "GHI,DNI,DHI,GTI,TEMP,WS",
            }
            resp = self._request("GET", "/data/monitor", params=params)
            resp.raise_for_status()
            data = resp.json()

            for row in data.get("data", []):
                reading = self._map_reading(row)
                if reading:
                    readings.append(reading)

        except requests.RequestException as e:
            logger.error("solargis_fetch_failed", plant_uid=plant_uid, error=str(e))

        batch = ReadingBatch(plant_uid=plant_uid, source=self.source_name, readings=readings)
        return self._apply_quality_score(batch)

    def list_plants(self) -> list[dict[str, Any]]:
        # SolarGIS doesn't have a "plants" concept — it works by coordinates
        return []

    def health_check(self) -> HealthStatus:
        start = time.time()
        try:
            # Simple latency check — fetch one data point for London
            resp = self._request("GET", "/data/monitor", params={
                "lat": 51.5, "lng": -0.12,
                "from": "2025-01-01", "to": "2025-01-01",
                "parameters": "GHI",
            })
            return HealthStatus(
                source=self.source_name,
                is_healthy=resp.status_code == 200,
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return HealthStatus(source=self.source_name, is_healthy=False, message=str(e))

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        self._rate_limiter.acquire()
        return self._session.request(
            method, f"{SOLARGIS_BASE_URL}{path}", timeout=60, **kwargs
        )

    def _map_reading(self, raw: dict) -> Reading | None:
        ts_str = raw.get("timestamp") or raw.get("datetime")
        if not ts_str:
            return None
        try:
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        except ValueError:
            return None

        mapped: dict[str, Any] = {"timestamp": ts}
        for sg_field, std_field in SOLARGIS_FIELD_MAP.items():
            val = raw.get(sg_field)
            if val is not None:
                try:
                    mapped[std_field] = float(val)
                except (ValueError, TypeError):
                    pass
        
        # Mark all fields as satellite-derived
        mapped["quality_flags"] = {std_field: "satellite" for std_field in mapped if std_field != "timestamp"}
        return Reading(**mapped)
```

### Acceptance Criteria

- [ ] Fetches irradiance by lat/lng coordinates
- [ ] Quality score = 0.85
- [ ] All readings flagged as `satellite` source
- [ ] Rate limiter at ~40/hour (1000/day budget)
- [ ] Gracefully handles missing coordinates

---

## Tasks 1.5–1.9: Inverter Platform Adapters

**Goal:** Create adapters for SMA, Enphase, SolarEdge, Huawei, and Fronius. These all follow the same pattern as EMIG but with platform-specific auth and field mapping.

**Estimated Hours:** 6 each (30 total)

### Summary Table

| Platform | Auth Method | Base URL | Resolution | Rate Limit | Reliability |
|----------|------------|----------|------------|------------|-------------|
| SMA | OAuth2 (Sunny Portal) | `https://portal.sma.de/api` | 5-min | 300 req/15min | 0.95 |
| Enphase | OAuth2 (Enlighten v4) | `https://api.enphaseenergy.com/api/v4` | 5-min | 10,000 req/day | 0.95 |
| SolarEdge | API Key | `https://monitoringapi.solaredge.com` | 15-min | Varies by plan | 0.95 |
| Huawei | OAuth2 (Northbound) | `https://eu5.fusionsolar.huawei.com/thirdData` | 5-min | TBD | 0.95 |
| Fronius | API Key | `https://api.solarweb.com/swqapi` | 5-min | TBD | 0.95 |

### File Pattern

Each adapter follows the exact same pattern as `emig.py`. Create:
- `services/ingestion/sma.py`
- `services/ingestion/enphase.py`
- `services/ingestion/solaredge.py`
- `services/ingestion/huawei.py`
- `services/ingestion/fronius.py`

Each file: ~100–150 lines, implements `DataSourceAdapter`, uses corresponding field map from `field_mapping.py`.

### Acceptance Criteria (per adapter)

- [ ] Implements `DataSourceAdapter` interface
- [ ] Uses correct authentication method
- [ ] Field mapping applied correctly (with unit conversions)
- [ ] Rate limiter configured to documented limits
- [ ] Health check implemented
- [ ] At least 3 unit tests with mocked responses

---

## Task 1.10: Ingestion Coordinator

**Goal:** Build the orchestrator that manages multi-source ingestion with fallback chain, gap detection, and quality scoring.

**Estimated Hours:** 10

### Files to Create

#### `services/ingestion/coordinator.py`
```python
"""
Ingestion coordinator — multi-source data orchestration.

For each plant, tries data sources in priority order:
1. Primary (e.g., EMIG direct API)
2. Secondary (e.g., Juggle aggregator)
3. Tertiary (e.g., SolarGIS satellite)

If a source has gaps, fills from the next source in the chain.
All data points receive a quality score based on their source.

DESIGN NOTES FOR EXTRACTION:
- This is the main entry point for data ingestion
- Called from Streamlit UI buttons now, Celery tasks later
- No Streamlit imports — pure business logic
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import structlog

from services.database.engine import get_engine
from services.database.repository import PlantRepository, ReadingsRepository
from services.ingestion.base import (
    DataSourceAdapter,
    HealthStatus,
    Reading,
    ReadingBatch,
    TimeRange,
)

logger = structlog.get_logger("ingestion.coordinator")


class IngestionResult:
    """Result of an ingestion cycle for one plant."""

    def __init__(self, plant_uid: str):
        self.plant_uid = plant_uid
        self.sources_tried: list[str] = []
        self.sources_succeeded: list[str] = []
        self.total_readings: int = 0
        self.new_readings: int = 0
        self.duplicates_skipped: int = 0
        self.gaps_filled: int = 0
        self.errors: list[str] = []
        self.quality_score: float = 0.0
        self.duration_seconds: float = 0.0


class IngestionCoordinator:
    """Orchestrates multi-source data ingestion."""

    def __init__(self):
        self._adapters: dict[str, DataSourceAdapter] = {}
        self._plant_repo = PlantRepository()
        self._readings_repo = ReadingsRepository()

    def register_adapter(self, adapter: DataSourceAdapter) -> None:
        """Register a data source adapter."""
        self._adapters[adapter.source_name] = adapter

    def get_adapter(self, source_name: str) -> DataSourceAdapter | None:
        return self._adapters.get(source_name)

    def list_adapters(self) -> list[str]:
        return list(self._adapters.keys())

    def health_check_all(self) -> dict[str, HealthStatus]:
        """Check health of all registered adapters."""
        results = {}
        for name, adapter in self._adapters.items():
            try:
                results[name] = adapter.health_check()
            except Exception as e:
                results[name] = HealthStatus(
                    source=name, is_healthy=False, message=str(e)
                )
        return results

    def ingest_plant(
        self,
        plant_uid: str,
        start: datetime | None = None,
        end: datetime | None = None,
        source_priority: list[str] | None = None,
    ) -> IngestionResult:
        """Full ingestion cycle for one plant.
        
        Args:
            plant_uid: Plant to ingest
            start: Start of time range (default: last reading timestamp)
            end: End of time range (default: now)
            source_priority: Ordered list of source names to try
                           (default: all registered, by reliability)
        """
        import time as _time
        t0 = _time.time()
        result = IngestionResult(plant_uid)

        # Determine time range
        if start is None:
            last_ts = self._readings_repo.get_latest_timestamp(plant_uid)
            start = last_ts or datetime(2024, 1, 1)
        if end is None:
            end = datetime.utcnow()

        # Determine source priority
        if source_priority is None:
            source_priority = sorted(
                self._adapters.keys(),
                key=lambda s: self._adapters[s].source_reliability,
                reverse=True,
            )

        # Get plant info for coordinate-based sources
        plant = self._plant_repo.get_by_uid(plant_uid)
        lat = plant.get("latitude") if plant else None
        lng = plant.get("longitude") if plant else None

        all_readings: list[Reading] = []

        for source_name in source_priority:
            adapter = self._adapters.get(source_name)
            if not adapter:
                continue

            result.sources_tried.append(source_name)

            try:
                # SolarGIS needs coordinates
                kwargs: dict[str, Any] = {}
                if source_name == "solargis" and lat and lng:
                    kwargs["latitude"] = lat
                    kwargs["longitude"] = lng

                batch = adapter.fetch_readings(
                    plant_uid, start, end, **kwargs
                )

                if batch.readings:
                    result.sources_succeeded.append(source_name)
                    all_readings.extend(batch.readings)
                    logger.info(
                        "ingestion_source_success",
                        plant_uid=plant_uid,
                        source=source_name,
                        readings=len(batch.readings),
                    )

            except Exception as e:
                error_msg = f"{source_name}: {e}"
                result.errors.append(error_msg)
                logger.error("ingestion_source_failed", plant_uid=plant_uid, source=source_name, error=str(e))

        # Deduplicate by timestamp + device_id (prefer higher reliability source)
        deduplicated = self._deduplicate(all_readings)
        result.total_readings = len(all_readings)
        result.duplicates_skipped = len(all_readings) - len(deduplicated)

        # Store in database
        if deduplicated:
            new_count = self._store_readings(plant_uid, deduplicated)
            result.new_readings = new_count

        # Calculate overall quality score
        if deduplicated:
            scores = [
                self._adapters[r.source].source_reliability
                for r in deduplicated
                if r.source in self._adapters
            ]
            result.quality_score = sum(scores) / len(scores) if scores else 0.0

        result.duration_seconds = _time.time() - t0
        logger.info(
            "ingestion_complete",
            plant_uid=plant_uid,
            total=result.total_readings,
            new=result.new_readings,
            dupes=result.duplicates_skipped,
            quality=round(result.quality_score, 3),
            sources=result.sources_succeeded,
            duration_s=round(result.duration_seconds, 2),
        )
        return result

    def ingest_all(
        self, source_priority: list[str] | None = None
    ) -> list[IngestionResult]:
        """Ingest all active plants."""
        plant_uids = self._plant_repo.list_uids()
        results = []
        for uid in plant_uids:
            try:
                result = self.ingest_plant(uid, source_priority=source_priority)
                results.append(result)
            except Exception as e:
                logger.error("ingest_all_plant_error", plant_uid=uid, error=str(e))
        return results

    def _deduplicate(self, readings: list[Reading]) -> list[Reading]:
        """Deduplicate readings by timestamp + device_id.
        
        When multiple sources provide data for the same timestamp,
        keep the one from the highest-reliability source.
        """
        seen: dict[tuple, Reading] = {}
        for reading in readings:
            key = (reading.timestamp, reading.device_id or "")
            existing = seen.get(key)
            if existing is None:
                seen[key] = reading
            else:
                # Keep higher reliability source
                existing_reliability = self._adapters.get(existing.source, None)
                new_reliability = self._adapters.get(reading.source, None)
                if (
                    new_reliability
                    and existing_reliability
                    and new_reliability.source_reliability > existing_reliability.source_reliability
                ):
                    seen[key] = reading
        return list(seen.values())

    def _store_readings(self, plant_uid: str, readings: list[Reading]) -> int:
        """Store readings in the database, skipping existing timestamps."""
        if not readings:
            return 0

        # Convert to DataFrame for bulk insert
        records = []
        for r in readings:
            record = {
                "timestamp": r.timestamp,
                "plant_uid": plant_uid,
                "device_id": r.device_id or "",
                "apparentPower_value": r.power_kw,
                "poaIrradiance_value": r.irradiance_poa_wm2,
                "ambientTemperature_value": r.ambient_temp_c,
                "moduleTemperature_value": r.module_temp_c,
                "source": r.source,
            }
            records.append(record)

        df = pd.DataFrame(records)
        
        # Simple dedup against existing data — check latest timestamp
        existing_latest = self._readings_repo.get_latest_timestamp(plant_uid)
        if existing_latest:
            df = df[df["timestamp"] > existing_latest]

        if df.empty:
            return 0

        return self._readings_repo.insert_batch(df)
```

### Testing Steps

```python
# tests/test_coordinator.py
"""Tests for ingestion coordinator."""
from datetime import datetime
from unittest.mock import MagicMock

from services.ingestion.base import DataSourceAdapter, HealthStatus, Reading, ReadingBatch
from services.ingestion.coordinator import IngestionCoordinator


class MockAdapter(DataSourceAdapter):
    def __init__(self, name: str, reliability: float, readings: list[Reading]):
        self._name = name
        self._reliability = reliability
        self._readings = readings
    
    @property
    def source_name(self) -> str:
        return self._name
    
    @property
    def source_reliability(self) -> float:
        return self._reliability
    
    def authenticate(self) -> bool:
        return True
    
    def fetch_readings(self, plant_uid, start, end, **kwargs):
        return ReadingBatch(
            plant_uid=plant_uid,
            source=self._name,
            readings=self._readings,
            quality_score=self._reliability,
        )
    
    def list_plants(self):
        return []
    
    def health_check(self):
        return HealthStatus(source=self._name, is_healthy=True)


def test_deduplication():
    coord = IngestionCoordinator()
    
    ts = datetime(2025, 6, 15, 12, 0)
    r1 = Reading(timestamp=ts, power_kw=100, source="emig")
    r2 = Reading(timestamp=ts, power_kw=95, source="juggle")
    
    coord.register_adapter(MockAdapter("emig", 0.95, [r1]))
    coord.register_adapter(MockAdapter("juggle", 0.90, [r2]))
    
    deduped = coord._deduplicate([r1, r2])
    assert len(deduped) == 1
    assert deduped[0].source == "emig"  # Higher reliability kept
```

### Acceptance Criteria

- [ ] Coordinator tries sources in priority order
- [ ] Deduplication keeps highest-reliability source
- [ ] Gap detection identifies missing intervals
- [ ] Results include statistics (total, new, dupes, errors)
- [ ] Works with any combination of registered adapters
- [ ] Logging provides clear ingestion audit trail

---

## Task 1.11: Background Polling Design

**Goal:** Design (not fully implement) the background polling architecture for future Celery integration. Create the task definitions and schedule configuration that will work when Celery is added.

**Estimated Hours:** 4

### Files to Create

#### `services/ingestion/polling.py`
```python
"""
Background polling for data ingestion.

CURRENT STATE: Runs synchronously when called from Streamlit UI buttons.
FUTURE STATE: Runs as Celery periodic tasks every 5 minutes.

The function signatures are designed to work as both:
- Direct function calls (now)
- Celery task functions (later, with @celery_app.task decorator)

DESIGN NOTES FOR EXTRACTION:
- Add @celery_app.task decorator when Celery is introduced
- Schedule via Celery Beat (see POLLING_SCHEDULE below)
- No Streamlit imports — pure business logic
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from services.ingestion.coordinator import IngestionCoordinator, IngestionResult

logger = structlog.get_logger("ingestion.polling")


# Future Celery Beat schedule
POLLING_SCHEDULE = {
    "poll-all-plants": {
        "task": "services.ingestion.polling.poll_all_plants",
        "schedule_minutes": 5,
        "description": "Poll all plants from configured sources",
    },
    "backfill-gaps": {
        "task": "services.ingestion.polling.backfill_gaps",
        "schedule_hours": 6,
        "description": "Detect and fill gaps in historical data",
    },
}


def poll_all_plants() -> list[IngestionResult]:
    """Poll all active plants for new data.
    
    Fetches data from the last known timestamp to now for each plant.
    Future: This becomes a Celery periodic task.
    """
    coordinator = _get_coordinator()
    return coordinator.ingest_all()


def poll_plant(plant_uid: str) -> IngestionResult:
    """Poll a single plant for new data."""
    coordinator = _get_coordinator()
    return coordinator.ingest_plant(plant_uid)


def backfill_plant(
    plant_uid: str, start: datetime, end: datetime
) -> IngestionResult:
    """Backfill historical data for a plant."""
    coordinator = _get_coordinator()
    return coordinator.ingest_plant(plant_uid, start=start, end=end)


def _get_coordinator() -> IngestionCoordinator:
    """Build a coordinator with all configured adapters.
    
    Registered adapters depend on which API keys are configured.
    """
    from services.config import get_settings
    
    coordinator = IngestionCoordinator()
    settings = get_settings()

    # Register adapters based on available API keys
    if settings.effective_api_key:
        from services.ingestion.emig import EmigAdapter
        coordinator.register_adapter(EmigAdapter())

    if settings.juggle_api_key and settings.juggle_api_key != settings.emig_api_key:
        from services.ingestion.juggle import JuggleAdapter
        coordinator.register_adapter(JuggleAdapter())

    if settings.solargis_api_key:
        from services.ingestion.solargis import SolarGISAdapter
        coordinator.register_adapter(SolarGISAdapter())

    # Future: Register SMA, Enphase, SolarEdge, etc. based on config
    
    return coordinator
```

### Acceptance Criteria

- [ ] `poll_all_plants()` callable directly from Streamlit
- [ ] Coordinator auto-registers adapters based on config
- [ ] Polling schedule defined for future Celery integration
- [ ] No Celery dependency required yet

---

## Task 1.12: Data Deduplication

**Goal:** Ensure no duplicate readings are inserted, even across multiple ingestion runs.

**Estimated Hours:** 4

### Strategy

```
Deduplication layers:
1. In-memory: IngestionCoordinator._deduplicate() — same-batch cross-source dedup
2. At insert: Check latest timestamp — skip readings older than last known
3. Database: UNIQUE constraint on (timestamp, plant_uid, device_id) — safety net
```

### Files to Modify

Add UNIQUE constraint migration to `scripts/add_dedup_index.py`:
```python
"""Add deduplication index to readings table."""
from services.database.engine import get_engine


def add_dedup_index():
    engine = get_engine()
    with engine.connection() as conn:
        # DuckDB doesn't support UNIQUE constraints after table creation,
        # but we can create a unique index
        try:
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_readings_dedup 
                ON readings (timestamp, plant_uid, device_id)
            """)
            print("Deduplication index created successfully.")
        except Exception as e:
            print(f"Index creation note: {e}")
            # May fail if duplicates already exist — clean first
            

if __name__ == "__main__":
    add_dedup_index()
```

### Acceptance Criteria

- [ ] No duplicate readings after multiple ingestion runs
- [ ] Cross-source deduplication prefers higher-reliability source
- [ ] Performance acceptable for 1M+ row table

---

## Task 1.13: Generic CSV/Excel Ingestion

**Goal:** Migrate and enhance the existing CSV upload functionality from `modules/data_explorer.py` and `modules/poa_import.py` into the adapter framework.

**Estimated Hours:** 6

### Files to Create

#### `services/ingestion/csv_adapter.py`
```python
"""
Generic CSV/Excel file ingestion adapter.

Handles manual file uploads with:
- Auto-detection of column mapping via fuzzy header matching
- Pydantic validation
- Quality scoring based on completeness
- Support for CSV, XLSX, and Parquet files

Migrated from: modules/data_explorer.py and modules/poa_import.py
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from services.ingestion.base import Reading, ReadingBatch

logger = structlog.get_logger("ingestion.csv")

# Common column name patterns for fuzzy matching
COLUMN_PATTERNS = {
    "timestamp": ["timestamp", "datetime", "date", "time", "Date/Time", "Timestamp"],
    "power_kw": ["power", "ac_power", "active_power", "pac", "Power (kW)", "kW"],
    "energy_kwh": ["energy", "yield", "production", "Energy (kWh)", "kWh"],
    "irradiance_poa_wm2": ["poa", "irradiance", "gti", "POA Irradiance", "W/m2", "W/m²"],
    "irradiance_ghi_wm2": ["ghi", "global_horizontal", "GHI"],
    "ambient_temp_c": ["ambient", "air_temp", "temp_amb", "Temperature", "°C"],
    "module_temp_c": ["module_temp", "panel_temp", "cell_temp"],
    "wind_speed_ms": ["wind", "wind_speed", "ws", "m/s"],
}


def ingest_file(
    file_data: bytes | BytesIO | str | Path,
    plant_uid: str,
    column_mapping: dict[str, str] | None = None,
    file_format: str = "csv",
) -> ReadingBatch:
    """Ingest a file into the standard Reading format.
    
    Args:
        file_data: File bytes, BytesIO, or file path
        plant_uid: Plant to associate this data with
        column_mapping: Optional explicit column mapping {file_col: standard_col}
        file_format: "csv", "xlsx", or "parquet"
    
    Returns:
        ReadingBatch with readings and quality info
    """
    # Load DataFrame
    if file_format == "parquet":
        if isinstance(file_data, (str, Path)):
            df = pd.read_parquet(file_data)
        else:
            df = pd.read_parquet(BytesIO(file_data) if isinstance(file_data, bytes) else file_data)
    elif file_format == "xlsx":
        if isinstance(file_data, (str, Path)):
            df = pd.read_excel(file_data)
        else:
            df = pd.read_excel(BytesIO(file_data) if isinstance(file_data, bytes) else file_data)
    else:
        if isinstance(file_data, (str, Path)):
            df = pd.read_csv(file_data)
        else:
            df = pd.read_csv(BytesIO(file_data) if isinstance(file_data, bytes) else file_data)

    if df.empty:
        return ReadingBatch(plant_uid=plant_uid, source="manual_upload", readings=[])

    # Auto-detect or apply column mapping
    if column_mapping is None:
        column_mapping = _auto_detect_columns(df.columns.tolist())

    # Rename columns to standard names
    rename_map = {v: k for k, v in column_mapping.items() if v in df.columns}
    df = df.rename(columns=rename_map)

    # Parse timestamps
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"])

    # Convert to readings
    readings: list[Reading] = []
    for _, row in df.iterrows():
        reading_dict: dict[str, Any] = {}
        for field in Reading.model_fields:
            if field in row.index and pd.notna(row[field]):
                reading_dict[field] = row[field]
        if "timestamp" in reading_dict:
            reading_dict["source"] = "manual_upload"
            readings.append(Reading(**reading_dict))

    # Quality score based on completeness
    total_fields = len(Reading.model_fields) - 2  # exclude timestamp and quality_flags
    avg_fields = sum(
        sum(1 for f in Reading.model_fields if getattr(r, f, None) is not None)
        for r in readings
    ) / max(len(readings), 1)
    quality = min(0.80, avg_fields / total_fields)  # Cap at 0.80 for manual uploads

    return ReadingBatch(
        plant_uid=plant_uid,
        source="manual_upload",
        readings=readings,
        quality_score=quality,
    )


def _auto_detect_columns(columns: list[str]) -> dict[str, str]:
    """Fuzzy-match file columns to standard field names."""
    from difflib import SequenceMatcher

    mapping = {}
    for std_field, patterns in COLUMN_PATTERNS.items():
        best_match = None
        best_score = 0.0
        for col in columns:
            for pattern in patterns:
                score = SequenceMatcher(None, col.lower(), pattern.lower()).ratio()
                if score > best_score and score > 0.6:
                    best_score = score
                    best_match = col
        if best_match:
            mapping[std_field] = best_match

    return mapping
```

### Acceptance Criteria

- [ ] CSV, XLSX, and Parquet files loadable
- [ ] Auto-detection of column mapping works
- [ ] Quality score reflects data completeness
- [ ] Integrates with `IngestionCoordinator` pattern
- [ ] Backward compatible with existing `poa_import.py` workflow

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| EMIG API changes or goes down | High | Low | Adapter has error handling; fallback to Juggle/SolarGIS |
| API rate limits hit during bulk historical pull | Medium | High | Rate limiters on every adapter; implement exponential backoff |
| Juggle API documentation unavailable | Medium | Medium | Start with EMIG + SolarGIS; add Juggle when docs obtained |
| SolarGIS API costs at scale | Medium | Low | Cache satellite data aggressively; use only for gap-filling |
| DuckDB lock contention during ingestion | Medium | Medium | Read-only fallback in engine; batch inserts to minimize lock time |
| Field mapping errors cause data quality issues | High | Medium | Validation checks after mapping; unit tests with real-format mock data |

---

## Definition of Done

- [ ] `DataSourceAdapter` interface defined with full type hints
- [ ] EMIG adapter working and tested against mock API
- [ ] At least 2 additional adapters implemented (Juggle, SolarGIS)
- [ ] `IngestionCoordinator` orchestrates multi-source ingestion
- [ ] Deduplication prevents duplicate readings
- [ ] Field mapping tables complete for all 8 platforms
- [ ] Rate limiting on every adapter
- [ ] CSV/Excel import migrated to new framework
- [ ] `poll_all_plants()` callable from Streamlit and future Celery
- [ ] 20+ unit tests passing
- [ ] Ingestion audit trail in structured logs
- [ ] Existing Plant Management page can use new coordinator
