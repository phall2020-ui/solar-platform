"""
Abstract base class and data models for solar data source adapters.

All inverter-platform adapters inherit from ``DataSourceAdapter`` and map their
vendor-specific payloads onto a common ``Reading`` / ``ReadingBatch`` model so
that downstream analytics are source-agnostic.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar

import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Source reliability scores (0–1)
# Higher = more trusted when merging overlapping data from multiple sources.
# ---------------------------------------------------------------------------
SOURCE_RELIABILITY: dict[str, float] = {
    "emig": 0.95,
    "juggle": 0.93,
    "sma": 0.92,
    "enphase": 0.92,
    "solaredge": 0.91,
    "huawei": 0.90,
    "fronius": 0.90,
    "solargis": 0.85,       # satellite-derived
    "generic_csv": 0.80,    # manual upload
    "interpolated": 0.50,   # gap-filled
    "unknown": 0.30,
}


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ReadingQuality(str, Enum):
    """Quality classification for an individual reading."""
    MEASURED = "measured"
    SATELLITE = "satellite"
    INTERPOLATED = "interpolated"
    ESTIMATED = "estimated"
    FLAGGED = "flagged"
    MISSING = "missing"


class HealthState(str, Enum):
    """Health states for an adapter connection."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class GapSeverity(str, Enum):
    """Gap severity classification by duration."""
    SHORT = "short"      # < 1 hour
    MEDIUM = "medium"    # 1–24 hours
    LONG = "long"        # > 24 hours


# ---------------------------------------------------------------------------
# Pydantic v2 models
# ---------------------------------------------------------------------------

class Reading(BaseModel):
    """
    A single normalised time-series reading.

    Every adapter maps its vendor-specific payload into this common shape so
    that the rest of the application never needs to know the data source.
    """
    model_config = ConfigDict(frozen=False, extra="allow")

    timestamp: datetime = Field(..., description="UTC timestamp of the reading")
    plant_uid: str = Field(..., description="Unique plant identifier")
    device_id: str = Field(default="", description="Device / inverter identifier")
    source: str = Field(..., description="Data source name (e.g. 'emig', 'sma')")

    # Power & energy
    power_kw: float | None = Field(None, ge=0, description="AC power output (kW)")
    energy_kwh: float | None = Field(None, ge=0, description="Energy produced in interval (kWh)")

    # Irradiance
    ghi_wm2: float | None = Field(None, ge=0, description="Global Horizontal Irradiance (W/m²)")
    poa_wm2: float | None = Field(None, ge=0, description="Plane of Array irradiance (W/m²)")
    dni_wm2: float | None = Field(None, ge=0, description="Direct Normal Irradiance (W/m²)")
    dhi_wm2: float | None = Field(None, ge=0, description="Diffuse Horizontal Irradiance (W/m²)")
    gti_wm2: float | None = Field(None, ge=0, description="Global Tilted Irradiance (W/m²)")

    # Environmental
    ambient_temp_c: float | None = Field(None, description="Ambient temperature (°C)")
    module_temp_c: float | None = Field(None, description="Module temperature (°C)")
    wind_speed_ms: float | None = Field(None, ge=0, description="Wind speed (m/s)")

    # Electrical detail
    voltage_v: float | None = Field(None, ge=0, description="DC or AC voltage (V)")
    current_a: float | None = Field(None, ge=0, description="DC or AC current (A)")
    frequency_hz: float | None = Field(None, ge=0, description="Grid frequency (Hz)")
    reactive_power_kvar: float | None = Field(None, description="Reactive power (kVAr)")
    apparent_power_kva: float | None = Field(None, ge=0, description="Apparent power (kVA)")
    power_factor: float | None = Field(None, ge=-1, le=1, description="Power factor")

    # Quality
    quality: ReadingQuality = Field(
        default=ReadingQuality.MEASURED,
        description="Quality classification",
    )
    quality_score: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Numeric quality score 0-1",
    )

    # Metadata
    raw_payload: dict[str, Any] | None = Field(
        None,
        description="Original vendor payload (for debugging)",
        exclude=True,
    )
    interval_seconds: int | None = Field(
        None, ge=0,
        description="Expected interval between consecutive readings (s)",
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc(cls, v: Any) -> datetime:
        """Coerce timestamp to UTC-aware datetime."""
        if isinstance(v, str):
            # Handle common ISO formats
            for fmt in (
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
            ):
                try:
                    dt = datetime.strptime(v.replace("Z", "+00:00") if "Z" in v else v, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    continue
            raise ValueError(f"Cannot parse timestamp: {v}")
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v
        raise TypeError(f"Expected str or datetime for timestamp, got {type(v)}")


class ReadingBatch(BaseModel):
    """
    A batch of normalised readings returned by an adapter fetch call.

    Carries metadata about the fetch operation alongside the readings
    themselves so callers can inspect success/failure without parsing logs.
    """
    model_config = ConfigDict(frozen=False)

    readings: list[Reading] = Field(default_factory=list)
    source: str = Field(..., description="Adapter source name")
    plant_uid: str = Field(..., description="Plant UID these readings belong to")
    fetch_started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fetch_ended_at: datetime | None = None
    requested_start: datetime | None = None
    requested_end: datetime | None = None

    # Diagnostics
    total_raw_records: int = Field(0, description="Raw records received from API before mapping")
    records_mapped: int = Field(0, description="Records successfully mapped to Reading")
    records_skipped: int = Field(0, description="Records skipped (validation failure, etc.)")
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return len(self.readings) == 0

    @property
    def success_rate(self) -> float:
        if self.total_raw_records == 0:
            return 0.0
        return self.records_mapped / self.total_raw_records

    def finalize(self) -> "ReadingBatch":
        """Set ``fetch_ended_at`` and compute counts."""
        self.fetch_ended_at = datetime.now(timezone.utc)
        self.records_mapped = len(self.readings)
        self.records_skipped = self.total_raw_records - self.records_mapped
        return self


class HealthStatus(BaseModel):
    """Health check result for an adapter."""
    model_config = ConfigDict(frozen=True)

    source: str
    state: HealthState = HealthState.UNKNOWN
    message: str = ""
    latency_ms: float | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = Field(default_factory=dict)


class FieldMapping(BaseModel):
    """
    Describes how a vendor field maps to a ``Reading`` attribute.

    Used by adapters to declaratively define their mapping tables rather than
    writing procedural transformation code for each field.
    """
    model_config = ConfigDict(frozen=True)

    vendor_field: str = Field(..., description="Key in the vendor payload")
    reading_field: str = Field(..., description="Attribute name on Reading")
    transform: str | None = Field(
        None,
        description="Optional transform: 'divide_1000', 'multiply_1000', 'to_kw', 'to_kwh', etc.",
    )
    unit: str | None = Field(None, description="Expected unit in vendor payload")


# ---------------------------------------------------------------------------
# Helper: apply a FieldMapping transform
# ---------------------------------------------------------------------------

_TRANSFORMS: dict[str, Any] = {
    "divide_1000": lambda v: v / 1000.0 if v is not None else None,
    "multiply_1000": lambda v: v * 1000.0 if v is not None else None,
    "to_kw": lambda v: v / 1000.0 if v is not None else None,       # W → kW
    "to_kwh": lambda v: v / 1000.0 if v is not None else None,      # Wh → kWh
    "to_mw": lambda v: v / 1_000_000.0 if v is not None else None,  # W → MW
    "negate": lambda v: -v if v is not None else None,
    "abs": lambda v: abs(v) if v is not None else None,
    "identity": lambda v: v,
}


def apply_field_mappings(
    raw: dict[str, Any],
    mappings: list[FieldMapping],
) -> dict[str, Any]:
    """
    Apply a list of ``FieldMapping`` rules to a raw vendor payload.

    Returns a dict whose keys match ``Reading`` attribute names, ready
    to be unpacked into ``Reading(**result)``.
    """
    result: dict[str, Any] = {}
    for fm in mappings:
        # Support nested keys via dot notation (e.g. "apparentPower.value")
        val = raw
        for part in fm.vendor_field.split("."):
            if isinstance(val, dict):
                val = val.get(part)
            else:
                val = None
                break

        if val is None:
            continue

        # Coerce to float for numeric fields
        try:
            val = float(val)
        except (TypeError, ValueError):
            pass

        if fm.transform and fm.transform in _TRANSFORMS:
            val = _TRANSFORMS[fm.transform](val)

        result[fm.reading_field] = val

    return result


# ---------------------------------------------------------------------------
# Abstract base adapter
# ---------------------------------------------------------------------------

class DataSourceAdapter(ABC):
    """
    Abstract base class for all solar data-source adapters.

    Subclasses implement vendor-specific authentication, data fetching,
    and field mapping.  The coordinator calls only these public methods.
    """

    source_name: ClassVar[str] = "unknown"

    def __init__(self) -> None:
        self.log = structlog.get_logger(adapter=self.source_name)
        self._last_fetch_ts: dict[str, datetime] = {}  # plant_uid → last fetched ts

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Validate credentials / obtain tokens.

        Returns True if authentication succeeded.
        """
        ...

    @abstractmethod
    async def fetch_readings(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
    ) -> ReadingBatch:
        """
        Fetch normalised readings for *plant_uid* in ``[start, end]``.

        Must return a ``ReadingBatch`` — even on failure (with errors populated).
        """
        ...

    @abstractmethod
    async def list_available_plants(self) -> list[dict[str, Any]]:
        """
        List plants/sites visible to the authenticated credentials.

        Returns a list of dicts with at least ``uid`` and ``name`` keys.
        """
        ...

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """
        Check whether the remote API is reachable and credentials are valid.
        """
        ...

    @abstractmethod
    def get_field_mapping(self) -> list[FieldMapping]:
        """
        Return the declarative field-mapping table for this adapter.
        """
        ...

    # ------------------------------------------------------------------
    # Convenience: synchronous wrappers for Streamlit compatibility
    # ------------------------------------------------------------------

    def sync_authenticate(self) -> bool:
        """Blocking wrapper around :meth:`authenticate`."""
        return _run_async(self.authenticate())

    def sync_fetch_readings(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
    ) -> ReadingBatch:
        """Blocking wrapper around :meth:`fetch_readings`."""
        return _run_async(self.fetch_readings(plant_uid, start, end))

    def sync_list_available_plants(self) -> list[dict[str, Any]]:
        """Blocking wrapper around :meth:`list_available_plants`."""
        return _run_async(self.list_available_plants())

    def sync_health_check(self) -> HealthStatus:
        """Blocking wrapper around :meth:`health_check`."""
        return _run_async(self.health_check())

    # ------------------------------------------------------------------
    # Incremental fetch helpers
    # ------------------------------------------------------------------

    def get_last_fetch_ts(self, plant_uid: str) -> datetime | None:
        """Return the last-fetched timestamp for a plant (in-memory)."""
        return self._last_fetch_ts.get(plant_uid)

    def set_last_fetch_ts(self, plant_uid: str, ts: datetime) -> None:
        """Record the last-fetched timestamp for a plant."""
        self._last_fetch_ts[plant_uid] = ts

    # ------------------------------------------------------------------
    # Reliability score
    # ------------------------------------------------------------------

    @property
    def reliability(self) -> float:
        """Return the source  reliability score from the global table."""
        return SOURCE_RELIABILITY.get(self.source_name, 0.30)


# ---------------------------------------------------------------------------
# Async-to-sync helper
# ---------------------------------------------------------------------------

def _run_async(coro):
    """
    Run an async coroutine synchronously.

    Handles the common Streamlit scenario where no event loop is running,
    as well as the case where we're already inside an event loop (e.g. Jupyter).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        return asyncio.run(coro)

    # Already inside an event loop — use nest_asyncio if available,
    # otherwise fall back to a new thread.
    try:
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(coro)
    except ImportError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
