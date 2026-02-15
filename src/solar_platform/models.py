"""
Pydantic v2 data models defining the data contract for Solar Portfolio Manager.

These models are backend-agnostic — they describe the shape of data flowing
between the service layer and consumers (Streamlit pages, future API endpoints)
regardless of whether the storage is DuckDB, PostgreSQL, or anything else.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ── Enums ───────────────────────────────────────────────────────────────


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class DataQualityLevel(str, Enum):
    GOOD = "good"           # ≥ 95 %
    ACCEPTABLE = "acceptable"  # 80–95 %
    POOR = "poor"           # < 80 %


# ── Core domain models ─────────────────────────────────────────────────


class Plant(BaseModel):
    """Registered solar plant / site."""

    alias: str = Field(..., description="Human-friendly plant name")
    plant_uid: str = Field(..., description="Unique plant identifier (from monitoring API)")
    inverter_ids: list[str] = Field(default_factory=list, description="EMIG IDs for inverters")
    weather_id: str | None = Field(default=None, description="Weather station EMIG ID")
    dc_size_kw: float | None = Field(default=None, ge=0, description="DC nameplate capacity (kW)")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    tilt: float | None = Field(default=None, ge=0, le=90, description="Panel tilt (degrees)")
    azimuth: float | None = Field(default=None, ge=0, le=360, description="Panel azimuth (degrees)")

    @model_validator(mode="before")
    @classmethod
    def _parse_inverter_ids(cls, data: Any) -> Any:
        """Handle inverter_ids stored as JSON string in DuckDB."""
        if isinstance(data, dict):
            ids = data.get("inverter_ids")
            if isinstance(ids, str):
                import json
                try:
                    data["inverter_ids"] = json.loads(ids)
                except (json.JSONDecodeError, TypeError):
                    data["inverter_ids"] = [s.strip() for s in ids.split(",") if s.strip()]
        return data


class Reading(BaseModel):
    """Single time-series reading from a device."""

    plant_uid: str
    emig_id: str = Field(..., description="Device / inverter EMIG ID")
    ts: datetime = Field(..., description="Timestamp (UTC)")
    payload: dict[str, Any] = Field(default_factory=dict, description="Raw measurement payload")

    # Convenience accessors that extract from payload
    @property
    def active_power_kw(self) -> float | None:
        """Active power in kW, extracted from payload."""
        return self._extract_value("activePower")

    @property
    def apparent_power_kva(self) -> float | None:
        """Apparent power in kVA, extracted from payload."""
        return self._extract_value("apparentPower")

    @property
    def poa_irradiance(self) -> float | None:
        """POA irradiance in W/m², extracted from payload."""
        return self._extract_value("poaIrradiance")

    def _extract_value(self, key: str) -> float | None:
        """Extract a scalar value from a possibly-nested payload entry."""
        v = self.payload.get(key)
        if v is None:
            return None
        if isinstance(v, dict):
            return v.get("value")
        try:
            return float(v)
        except (TypeError, ValueError):
            return None


class ReadingBatch(BaseModel):
    """A batch of readings, typically for a single query response."""

    readings: list[Reading] = Field(default_factory=list)
    total_count: int = Field(default=0, description="Total matching rows (before LIMIT)")

    @property
    def count(self) -> int:
        return len(self.readings)


# ── Query / response contracts ──────────────────────────────────────────


class TimeSeriesQuery(BaseModel):
    """Parameters for a time-series data request."""

    plant_uid: str
    start: datetime
    end: datetime
    device_ids: list[str] | None = Field(
        default=None,
        description="Filter to specific EMIG IDs; None = all devices",
    )
    resolution: str = Field(
        default="raw",
        description="Aggregation bucket: 'raw', '5min', '15min', '1h', '1d'",
    )
    limit: int = Field(default=50_000, ge=1, le=500_000)

    @model_validator(mode="after")
    def _validate_range(self) -> "TimeSeriesQuery":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class TimeSeriesResponse(BaseModel):
    """Response wrapper for time-series data."""

    query: TimeSeriesQuery
    total_rows: int = 0
    truncated: bool = False
    data: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Flat list of dicts ready for pd.DataFrame()",
    )


# ── Alerts & tickets ───────────────────────────────────────────────────


class Alert(BaseModel):
    """System or plant-level alert."""

    id: str = Field(default="", description="Unique alert ID")
    plant_uid: str | None = None
    severity: AlertSeverity = AlertSeverity.INFO
    title: str = ""
    message: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    acknowledged: bool = False


class Ticket(BaseModel):
    """O&M or corrective-maintenance ticket."""

    id: str = Field(default="", description="Unique ticket ID")
    plant_uid: str
    status: TicketStatus = TicketStatus.OPEN
    title: str = ""
    description: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    assignee: str | None = None


# ── Data quality ────────────────────────────────────────────────────────


class DataQualityScore(BaseModel):
    """Data completeness / quality assessment for a plant over a period."""

    plant_uid: str
    start: datetime
    end: datetime
    expected_readings: int = Field(default=0, ge=0)
    actual_readings: int = Field(default=0, ge=0)

    @property
    def completeness_pct(self) -> float:
        if self.expected_readings == 0:
            return 0.0
        return round(100.0 * self.actual_readings / self.expected_readings, 2)

    @property
    def level(self) -> DataQualityLevel:
        pct = self.completeness_pct
        if pct >= 95.0:
            return DataQualityLevel.GOOD
        if pct >= 80.0:
            return DataQualityLevel.ACCEPTABLE
        return DataQualityLevel.POOR
