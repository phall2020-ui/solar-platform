"""
Multi-source ingestion coordinator.

Manages all registered ``DataSourceAdapter`` instances and orchestrates
data fetching across multiple sources with a **cumulative fallback chain**:

    Primary → Secondary → Satellite → Interpolation → Gap flag

This is the main entry point for all data ingestion — callers interact
with :class:`IngestionCoordinator` rather than individual adapters.

Usage::

    from solar_platform.ingestion.coordinator import IngestionCoordinator
    from solar_platform.ingestion.emig_adapter import EMIGAdapter
    from solar_platform.ingestion.solargis_adapter import SolarGISAdapter

    coord = IngestionCoordinator()
    coord.register_adapter(EMIGAdapter(api_key="..."))
    coord.register_adapter(SolarGISAdapter(api_key="..."))

    # Configure source priority per plant
    coord.set_plant_sources("ERS:00001", ["emig", "solargis"])

    # Ingest with fallback
    result = coord.sync_ingest_plant("ERS:00001", start, end)
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field

from solar_platform.ingestion.base import (
    DataSourceAdapter,
    GapSeverity,
    HealthStatus,
    Reading,
    ReadingBatch,
    ReadingQuality,
    SOURCE_RELIABILITY,
    _run_async,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class IngestionResult(BaseModel):
    """Aggregated result of ingesting data for one plant from multiple sources."""
    model_config = ConfigDict(frozen=False)

    plant_uid: str
    readings: list[Reading] = Field(default_factory=list)
    sources_attempted: list[str] = Field(default_factory=list)
    sources_succeeded: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)
    total_raw: int = 0
    total_mapped: int = 0
    total_deduplicated: int = 0
    gaps_detected: int = 0
    gaps_filled: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def success(self) -> bool:
        return len(self.readings) > 0 and len(self.sources_succeeded) > 0


class PlantSourceConfig(BaseModel):
    """Source priority and configuration for a single plant."""
    model_config = ConfigDict(frozen=False)

    plant_uid: str
    source_priority: list[str] = Field(
        default_factory=lambda: ["emig"],
        description="Ordered list of source names to try (first = highest priority)",
    )
    satellite_fallback: str | None = Field(
        "solargis",
        description="Satellite source to use for gap-filling",
    )
    interpolation_max_gap_minutes: int = Field(
        60,
        description="Max gap (minutes) to fill via interpolation",
    )
    enabled: bool = True


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------

class IngestionCoordinator:
    """
    Multi-source ingestion orchestrator.

    Manages adapter registration, per-plant source configuration, and the
    fallback chain:  Primary → Secondary → Satellite → Interpolation → Flag.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, DataSourceAdapter] = {}
        self._plant_configs: dict[str, PlantSourceConfig] = {}
        self.log = structlog.get_logger("ingestion.coordinator")

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_adapter(self, adapter: DataSourceAdapter) -> None:
        """
        Register a data source adapter.

        Adapters are keyed by their ``source_name`` — registering a second
        adapter with the same name replaces the first.
        """
        self._adapters[adapter.source_name] = adapter
        self.log.info("adapter_registered", source=adapter.source_name)

    def get_adapter(self, source_name: str) -> DataSourceAdapter | None:
        """Look up a registered adapter by name."""
        return self._adapters.get(source_name)

    @property
    def registered_sources(self) -> list[str]:
        """Return names of all registered adapters."""
        return list(self._adapters.keys())

    # ------------------------------------------------------------------
    # Plant source configuration
    # ------------------------------------------------------------------

    def set_plant_sources(
        self,
        plant_uid: str,
        source_priority: list[str],
        satellite_fallback: str | None = "solargis",
        interpolation_max_gap_minutes: int = 60,
    ) -> None:
        """
        Configure the source priority for a plant.

        Args:
            plant_uid: Plant identifier.
            source_priority: Ordered adapter names (first tried first).
            satellite_fallback: Adapter name for satellite gap-filling (or None).
            interpolation_max_gap_minutes: Max gap length to interpolate.
        """
        self._plant_configs[plant_uid] = PlantSourceConfig(
            plant_uid=plant_uid,
            source_priority=source_priority,
            satellite_fallback=satellite_fallback,
            interpolation_max_gap_minutes=interpolation_max_gap_minutes,
        )

    def get_plant_config(self, plant_uid: str) -> PlantSourceConfig:
        """
        Return the source config for a plant.

        Falls back to a default config (just ``["emig"]``) if not explicitly set.
        """
        return self._plant_configs.get(
            plant_uid,
            PlantSourceConfig(plant_uid=plant_uid),
        )

    # ------------------------------------------------------------------
    # Ingestion: single plant
    # ------------------------------------------------------------------

    async def ingest_plant(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
        skip_dedup: bool = False,
        skip_gap_fill: bool = False,
    ) -> IngestionResult:
        """
        Ingest data for a single plant from configured sources.

        Walks the fallback chain:

        1. Try each source in ``source_priority`` order.
        2. Merge & deduplicate readings by timestamp.
        3. Detect gaps in the merged timeline.
        4. For SHORT gaps (< ``interpolation_max_gap_minutes``), linearly
           interpolate.
        5. For MEDIUM gaps, try the ``satellite_fallback`` adapter.
        6. For LONG gaps (> 24 h), flag as :attr:`ReadingQuality.MISSING`.
        """
        import time as _t

        t0 = _t.monotonic()
        config = self.get_plant_config(plant_uid)
        result = IngestionResult(plant_uid=plant_uid)

        # --- Step 1: Fetch from each priority source ---
        all_readings: list[Reading] = []
        for source_name in config.source_priority:
            adapter = self._adapters.get(source_name)
            if adapter is None:
                result.warnings.append(f"Adapter '{source_name}' not registered — skipped")
                continue

            result.sources_attempted.append(source_name)
            try:
                batch = await adapter.fetch_readings(plant_uid, start, end)
                result.total_raw += batch.total_raw_records

                if batch.errors:
                    result.errors.extend(batch.errors)
                if batch.warnings:
                    result.warnings.extend(batch.warnings)

                if not batch.is_empty:
                    all_readings.extend(batch.readings)
                    result.sources_succeeded.append(source_name)
                    self.log.info(
                        "source_fetched",
                        plant=plant_uid,
                        source=source_name,
                        count=len(batch.readings),
                    )
                else:
                    result.sources_failed.append(source_name)
                    self.log.warning(
                        "source_empty",
                        plant=plant_uid,
                        source=source_name,
                        errors=batch.errors,
                    )
            except Exception as exc:
                result.sources_failed.append(source_name)
                result.errors.append(f"{source_name}: {exc}")
                self.log.error(
                    "source_error",
                    plant=plant_uid,
                    source=source_name,
                    error=str(exc),
                )

        # --- Step 2: Deduplicate ---
        if not skip_dedup and all_readings:
            all_readings = self._deduplicate(all_readings)
            result.total_deduplicated = result.total_raw - len(all_readings)

        # --- Step 3 & 4 & 5: Gap detection & filling ---
        if not skip_gap_fill and all_readings:
            all_readings, gaps_found, gaps_filled = await self._fill_gaps(
                all_readings, plant_uid, start, end, config
            )
            result.gaps_detected = gaps_found
            result.gaps_filled = gaps_filled

        result.readings = all_readings
        result.total_mapped = len(all_readings)
        result.duration_seconds = round(_t.monotonic() - t0, 2)

        self.log.info(
            "ingestion_complete",
            plant=plant_uid,
            readings=result.total_mapped,
            sources=result.sources_succeeded,
            gaps=result.gaps_detected,
            duration_s=result.duration_seconds,
        )

        return result

    # ------------------------------------------------------------------
    # Ingestion: all plants
    # ------------------------------------------------------------------

    async def ingest_all(
        self,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None = None,
    ) -> dict[str, IngestionResult]:
        """
        Ingest data for multiple plants (default: all configured plants).

        Returns a dict of ``{plant_uid: IngestionResult}``.
        """
        uids = plant_uids or list(self._plant_configs.keys())
        results: dict[str, IngestionResult] = {}

        for uid in uids:
            cfg = self.get_plant_config(uid)
            if not cfg.enabled:
                continue
            results[uid] = await self.ingest_plant(uid, start, end)

        return results

    # ------------------------------------------------------------------
    # Backfill
    # ------------------------------------------------------------------

    async def backfill(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
        chunk_days: int = 30,
    ) -> IngestionResult:
        """
        Historical backfill for a plant.

        Splits the range into ``chunk_days`` windows and ingests
        each sequentially, concatenating results.
        """
        combined = IngestionResult(plant_uid=plant_uid)
        current = start

        while current < end:
            chunk_end = min(current + timedelta(days=chunk_days), end)
            result = await self.ingest_plant(plant_uid, current, chunk_end)
            combined.readings.extend(result.readings)
            combined.total_raw += result.total_raw
            combined.total_mapped += result.total_mapped
            combined.errors.extend(result.errors)
            combined.warnings.extend(result.warnings)
            combined.sources_attempted = list(
                set(combined.sources_attempted) | set(result.sources_attempted)
            )
            combined.sources_succeeded = list(
                set(combined.sources_succeeded) | set(result.sources_succeeded)
            )
            combined.sources_failed = list(
                set(combined.sources_failed) | set(result.sources_failed)
            )
            combined.gaps_detected += result.gaps_detected
            combined.gaps_filled += result.gaps_filled
            current = chunk_end

        return combined

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    async def health_check_all(self) -> dict[str, HealthStatus]:
        """Run health checks on all registered adapters."""
        results: dict[str, HealthStatus] = {}
        for name, adapter in self._adapters.items():
            results[name] = await adapter.health_check()
        return results

    # ------------------------------------------------------------------
    # Synchronous wrappers (for Streamlit)
    # ------------------------------------------------------------------

    def sync_ingest_plant(
        self, plant_uid: str, start: datetime, end: datetime, **kwargs: Any
    ) -> IngestionResult:
        """Blocking wrapper around :meth:`ingest_plant`."""
        return _run_async(self.ingest_plant(plant_uid, start, end, **kwargs))

    def sync_ingest_all(
        self, start: datetime, end: datetime, **kwargs: Any
    ) -> dict[str, IngestionResult]:
        """Blocking wrapper around :meth:`ingest_all`."""
        return _run_async(self.ingest_all(start, end, **kwargs))

    def sync_backfill(
        self, plant_uid: str, start: datetime, end: datetime, **kwargs: Any
    ) -> IngestionResult:
        """Blocking wrapper around :meth:`backfill`."""
        return _run_async(self.backfill(plant_uid, start, end, **kwargs))

    def sync_health_check_all(self) -> dict[str, HealthStatus]:
        """Blocking wrapper around :meth:`health_check_all`."""
        return _run_async(self.health_check_all())

    # ------------------------------------------------------------------
    # Internal: deduplication
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate(readings: list[Reading]) -> list[Reading]:
        """
        Deduplicate readings by ``(timestamp, plant_uid, device_id)``.

        When duplicates exist, keep the reading with the **highest
        quality_score** (i.e. prefer measured over satellite over
        interpolated).
        """
        best: dict[tuple, Reading] = {}
        for r in readings:
            key = (r.timestamp, r.plant_uid, r.device_id)
            existing = best.get(key)
            if existing is None or r.quality_score > existing.quality_score:
                best[key] = r
        return sorted(best.values(), key=lambda r: r.timestamp)

    # ------------------------------------------------------------------
    # Internal: gap detection & filling
    # ------------------------------------------------------------------

    async def _fill_gaps(
        self,
        readings: list[Reading],
        plant_uid: str,
        start: datetime,
        end: datetime,
        config: PlantSourceConfig,
    ) -> tuple[list[Reading], int, int]:
        """
        Detect and fill gaps in the reading timeline.

        Returns ``(readings_with_fills, gaps_detected, gaps_filled)``.
        """
        if not readings:
            return readings, 0, 0

        # Sort by timestamp
        readings = sorted(readings, key=lambda r: r.timestamp)

        # Detect expected interval from most common delta
        interval_s = self._detect_interval(readings)
        if interval_s is None or interval_s <= 0:
            return readings, 0, 0

        # Find gaps
        gaps: list[tuple[datetime, datetime, GapSeverity]] = []
        for i in range(1, len(readings)):
            delta = (readings[i].timestamp - readings[i - 1].timestamp).total_seconds()
            if delta > interval_s * 1.5:  # >1.5x expected = gap
                gap_start = readings[i - 1].timestamp
                gap_end = readings[i].timestamp
                gap_minutes = delta / 60
                if gap_minutes < 60:
                    severity = GapSeverity.SHORT
                elif gap_minutes < 24 * 60:
                    severity = GapSeverity.MEDIUM
                else:
                    severity = GapSeverity.LONG
                gaps.append((gap_start, gap_end, severity))

        if not gaps:
            return readings, 0, 0

        gaps_detected = len(gaps)
        gaps_filled = 0
        fill_readings: list[Reading] = []

        for gap_start, gap_end, severity in gaps:
            gap_minutes = (gap_end - gap_start).total_seconds() / 60

            if severity == GapSeverity.SHORT and gap_minutes <= config.interpolation_max_gap_minutes:
                # LINEAR INTERPOLATION
                fills = self._interpolate_gap(readings, gap_start, gap_end, interval_s, plant_uid)
                fill_readings.extend(fills)
                gaps_filled += 1

            elif severity == GapSeverity.MEDIUM and config.satellite_fallback:
                # SATELLITE FALLBACK
                sat_adapter = self._adapters.get(config.satellite_fallback)
                if sat_adapter:
                    try:
                        sat_batch = await sat_adapter.fetch_readings(plant_uid, gap_start, gap_end)
                        if not sat_batch.is_empty:
                            fill_readings.extend(sat_batch.readings)
                            gaps_filled += 1
                    except Exception as exc:
                        self.log.warning(
                            "satellite_fallback_failed",
                            plant=plant_uid,
                            gap=f"{gap_start}–{gap_end}",
                            error=str(exc),
                        )

            else:
                # FLAG as missing
                ts_cursor = gap_start + timedelta(seconds=interval_s)
                while ts_cursor < gap_end:
                    fill_readings.append(Reading(
                        timestamp=ts_cursor,
                        plant_uid=plant_uid,
                        device_id="gap_flag",
                        source="gap_detector",
                        quality=ReadingQuality.MISSING,
                        quality_score=0.0,
                    ))
                    ts_cursor += timedelta(seconds=interval_s)

        # Merge fills into readings and deduplicate
        all_combined = readings + fill_readings
        all_combined = sorted(set_key_dedup(all_combined), key=lambda r: r.timestamp)

        return all_combined, gaps_detected, gaps_filled

    @staticmethod
    def _detect_interval(readings: list[Reading]) -> int | None:
        """Detect the most common interval (seconds) between consecutive readings."""
        if len(readings) < 2:
            return None
        deltas: list[int] = []
        for i in range(1, min(len(readings), 100)):
            d = int((readings[i].timestamp - readings[i - 1].timestamp).total_seconds())
            if 0 < d < 86400:
                deltas.append(d)
        if not deltas:
            return None
        # Most common delta
        from collections import Counter
        return Counter(deltas).most_common(1)[0][0]

    @staticmethod
    def _interpolate_gap(
        readings: list[Reading],
        gap_start: datetime,
        gap_end: datetime,
        interval_s: int,
        plant_uid: str,
    ) -> list[Reading]:
        """
        Linearly interpolate numeric fields across a short gap.

        Uses the last reading before and first reading after the gap as
        boundary points.
        """
        # Find boundary readings
        before = next((r for r in reversed(readings) if r.timestamp <= gap_start), None)
        after = next((r for r in readings if r.timestamp >= gap_end), None)
        if before is None or after is None:
            return []

        total_seconds = (after.timestamp - before.timestamp).total_seconds()
        if total_seconds <= 0:
            return []

        fills: list[Reading] = []
        numeric_fields = [
            "power_kw", "energy_kwh", "ghi_wm2", "poa_wm2", "dni_wm2",
            "dhi_wm2", "gti_wm2", "ambient_temp_c", "module_temp_c",
            "wind_speed_ms", "voltage_v", "current_a",
        ]

        ts_cursor = gap_start + timedelta(seconds=interval_s)
        while ts_cursor < gap_end:
            frac = (ts_cursor - before.timestamp).total_seconds() / total_seconds
            kwargs: dict[str, Any] = {}
            for field in numeric_fields:
                v_before = getattr(before, field, None)
                v_after = getattr(after, field, None)
                if v_before is not None and v_after is not None:
                    kwargs[field] = v_before + (v_after - v_before) * frac

            fills.append(Reading(
                timestamp=ts_cursor,
                plant_uid=plant_uid,
                device_id=before.device_id,
                source="interpolated",
                quality=ReadingQuality.INTERPOLATED,
                quality_score=SOURCE_RELIABILITY.get("interpolated", 0.5),
                interval_seconds=interval_s,
                **kwargs,
            ))
            ts_cursor += timedelta(seconds=interval_s)

        return fills


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def set_key_dedup(readings: list[Reading]) -> list[Reading]:
    """Deduplicate by (timestamp, plant_uid, device_id), keeping highest quality."""
    best: dict[tuple, Reading] = {}
    for r in readings:
        key = (r.timestamp, r.plant_uid, r.device_id)
        existing = best.get(key)
        if existing is None or r.quality_score > existing.quality_score:
            best[key] = r
    return list(best.values())
