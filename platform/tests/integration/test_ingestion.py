"""Integration tests for the ingestion coordinator with adapter base."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

import pytest

from services.ingestion.base import (
    DataSourceAdapter,
    FieldMapping,
    HealthState,
    HealthStatus,
    Reading,
    ReadingBatch,
    ReadingQuality,
)
from services.ingestion.coordinator import IngestionCoordinator, IngestionResult


# ── Stub adapter for testing ─────────────────────────────────────────────


class StubAdapter(DataSourceAdapter):
    """A test adapter that returns canned data without network calls."""

    source_name: ClassVar[str] = "stub"

    def __init__(self, readings: list[Reading] | None = None, should_fail: bool = False):
        super().__init__()
        self._readings = readings or []
        self._should_fail = should_fail

    async def authenticate(self) -> bool:
        return not self._should_fail

    async def fetch_readings(self, plant_uid: str, start: datetime, end: datetime) -> ReadingBatch:
        if self._should_fail:
            return ReadingBatch(
                source=self.source_name,
                plant_uid=plant_uid,
                errors=["Simulated failure"],
            )
        filtered = [r for r in self._readings if r.plant_uid == plant_uid]
        batch = ReadingBatch(
            source=self.source_name,
            plant_uid=plant_uid,
            readings=filtered,
            total_raw_records=len(filtered),
        )
        return batch.finalize()

    async def list_available_plants(self) -> list[dict[str, Any]]:
        return [{"uid": "stub-001", "name": "Stub Plant"}]

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            source=self.source_name,
            state=HealthState.HEALTHY if not self._should_fail else HealthState.UNHEALTHY,
            message="OK" if not self._should_fail else "Failed",
        )

    def get_field_mapping(self) -> list[FieldMapping]:
        return [
            FieldMapping(vendor_field="power", reading_field="power_kw", transform="to_kw"),
        ]


class StubFallbackAdapter(DataSourceAdapter):
    """A secondary adapter for fallback testing."""

    source_name: ClassVar[str] = "stub_fallback"

    def __init__(self, readings: list[Reading] | None = None):
        super().__init__()
        self._readings = readings or []

    async def authenticate(self) -> bool:
        return True

    async def fetch_readings(self, plant_uid: str, start: datetime, end: datetime) -> ReadingBatch:
        filtered = [r for r in self._readings if r.plant_uid == plant_uid]
        batch = ReadingBatch(
            source=self.source_name,
            plant_uid=plant_uid,
            readings=filtered,
            total_raw_records=len(filtered),
        )
        return batch.finalize()

    async def list_available_plants(self) -> list[dict[str, Any]]:
        return []

    async def health_check(self) -> HealthStatus:
        return HealthStatus(source=self.source_name, state=HealthState.HEALTHY)

    def get_field_mapping(self) -> list[FieldMapping]:
        return []


# ── Helper ───────────────────────────────────────────────────────────────


def _make_readings(plant_uid: str, source: str, count: int = 5) -> list[Reading]:
    """Generate deterministic test readings."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Reading(
            timestamp=base + timedelta(minutes=i * 15),
            plant_uid=plant_uid,
            device_id="dev-1",
            source=source,
            power_kw=float(100 + i * 10),
            energy_kwh=float(25 + i * 2),
            poa_wm2=float(400 + i * 50),
        )
        for i in range(count)
    ]


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestIngestionCoordinator:
    """Integration tests for the ingestion coordinator."""

    def test_register_adapter(self):
        coord = IngestionCoordinator()
        adapter = StubAdapter()
        coord.register_adapter(adapter)
        assert "stub" in coord.registered_sources
        assert coord.get_adapter("stub") is adapter

    def test_set_and_get_plant_sources(self):
        coord = IngestionCoordinator()
        coord.set_plant_sources("plant-001", ["stub", "stub_fallback"])
        config = coord.get_plant_config("plant-001")
        assert config.source_priority == ["stub", "stub_fallback"]
        assert config.plant_uid == "plant-001"

    def test_get_default_plant_config(self):
        coord = IngestionCoordinator()
        config = coord.get_plant_config("unknown-plant")
        assert config.plant_uid == "unknown-plant"
        assert config.source_priority == ["emig"]  # default

    def test_single_source_ingest(self):
        readings = _make_readings("plant-001", "stub", count=5)
        adapter = StubAdapter(readings=readings)
        coord = IngestionCoordinator()
        coord.register_adapter(adapter)
        coord.set_plant_sources("plant-001", ["stub"])

        result = asyncio.run(
            coord.ingest_plant("plant-001",
                               datetime(2026, 1, 1, tzinfo=timezone.utc),
                               datetime(2026, 1, 2, tzinfo=timezone.utc))
        )
        assert isinstance(result, IngestionResult)
        assert result.plant_uid == "plant-001"
        assert "stub" in result.sources_attempted

    def test_adapter_health_check_sync(self):
        adapter = StubAdapter()
        health = adapter.sync_health_check()
        assert health.state == HealthState.HEALTHY

    def test_adapter_sync_authenticate(self):
        adapter = StubAdapter()
        assert adapter.sync_authenticate() is True

    def test_adapter_sync_list_plants(self):
        adapter = StubAdapter()
        plants = adapter.sync_list_available_plants()
        assert len(plants) == 1
        assert plants[0]["uid"] == "stub-001"


@pytest.mark.integration
class TestReadingModel:
    """Integration tests for the Reading and ReadingBatch models."""

    def test_reading_creation_with_utc(self):
        r = Reading(
            timestamp="2026-01-01T00:00:00Z",
            plant_uid="plant-001",
            source="test",
            power_kw=100.0,
        )
        assert r.timestamp.tzinfo is not None
        assert r.plant_uid == "plant-001"

    def test_reading_batch_finalize(self):
        readings = _make_readings("plant-001", "stub", count=3)
        batch = ReadingBatch(
            source="stub",
            plant_uid="plant-001",
            readings=readings,
            total_raw_records=3,
        )
        batch.finalize()
        assert batch.records_mapped == 3
        assert batch.fetch_ended_at is not None
        assert batch.success_rate == 1.0

    def test_empty_batch(self):
        batch = ReadingBatch(source="stub", plant_uid="plant-001")
        assert batch.is_empty is True
        assert batch.success_rate == 0.0

    def test_reading_quality_enum(self):
        r = Reading(
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            plant_uid="plant-001",
            source="test",
            quality=ReadingQuality.SATELLITE,
        )
        assert r.quality == ReadingQuality.SATELLITE
