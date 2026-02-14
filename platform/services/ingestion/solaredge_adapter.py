"""
SolarEdge Monitoring API adapter.

SolarEdge exposes equipment-level data via a simple **API-key** authentication
scheme.  Power optimizers allow module-level granularity.

Key endpoints:
    GET /sites                                  – list sites
    GET /site/{siteId}/overview                 – site overview
    GET /site/{siteId}/energy                   – energy production
    GET /site/{siteId}/power                    – power measurements
    GET /site/{siteId}/powerDetails             – per-inverter power
    GET /equipment/{siteId}/list                – equipment list
    GET /equipment/{siteId}/{serialNumber}/data – equipment telemetry

Base URL: https://monitoringapi.solaredge.com

Environment variables:
    SOLAREDGE_API_KEY   – site-level API key
    SOLAREDGE_API_URL   – override (optional)

Resolution: 15-minute (power), daily (energy); some endpoints support
            higher resolution with module-level add-on.
Rate limit: Not formally published; conservative 300 req/15min assumed.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from services.ingestion.base import (
    DataSourceAdapter,
    FieldMapping,
    HealthState,
    HealthStatus,
    Reading,
    ReadingBatch,
    ReadingQuality,
    apply_field_mappings,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = os.getenv(
    "SOLAREDGE_API_URL",
    "https://monitoringapi.solaredge.com",
)
RATE_LIMIT_PER_15MIN = 300
INTERVAL_SECONDS = 900          # 15-minute resolution
MAX_DAYS_PER_CHUNK = 30         # SolarEdge recommends ≤ 1 month per request

# ---------------------------------------------------------------------------
# Field mapping: SolarEdge → Reading
# ---------------------------------------------------------------------------

SOLAREDGE_FIELD_MAPPINGS: list[FieldMapping] = [
    # From /power and /powerDetails
    FieldMapping(vendor_field="value",              reading_field="power_kw", transform="to_kw"),
    FieldMapping(vendor_field="power",              reading_field="power_kw", transform="to_kw"),
    # From /energy
    FieldMapping(vendor_field="energy",             reading_field="energy_kwh", transform="to_kwh"),
    # Equipment data
    FieldMapping(vendor_field="totalActivePower",   reading_field="power_kw", transform="to_kw"),
    FieldMapping(vendor_field="totalEnergy",        reading_field="energy_kwh", transform="to_kwh"),
    FieldMapping(vendor_field="dcVoltage",          reading_field="voltage_v"),
    FieldMapping(vendor_field="groundFaultResistance", reading_field="voltage_v"),
    FieldMapping(vendor_field="L1Data.acCurrent",   reading_field="current_a"),
    FieldMapping(vendor_field="L1Data.acVoltage",   reading_field="voltage_v"),
    FieldMapping(vendor_field="L1Data.acFrequency", reading_field="frequency_hz"),
    FieldMapping(vendor_field="L1Data.apparentPower", reading_field="apparent_power_kva", transform="to_kw"),
    FieldMapping(vendor_field="L1Data.activePower", reading_field="power_kw", transform="to_kw"),
    FieldMapping(vendor_field="L1Data.reactivePower", reading_field="reactive_power_kvar", transform="to_kw"),
    FieldMapping(vendor_field="L1Data.cosPhi",      reading_field="power_factor"),
    # Environmental (weather station)
    FieldMapping(vendor_field="temperature",        reading_field="ambient_temp_c"),
    FieldMapping(vendor_field="irradiance",         reading_field="poa_wm2"),
    FieldMapping(vendor_field="windSpeed",          reading_field="wind_speed_ms"),
]


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class _SlidingLimiter:
    def __init__(self, max_calls: int = RATE_LIMIT_PER_15MIN, window_s: float = 900.0) -> None:
        self._max = max_calls
        self._window = window_s
        self._calls: list[float] = []

    async def acquire(self) -> None:
        now = time.monotonic()
        self._calls = [t for t in self._calls if now - t < self._window]
        if len(self._calls) >= self._max:
            wait = self._window - (now - self._calls[0])
            if wait > 0:
                await asyncio.sleep(wait)
        self._calls.append(time.monotonic())


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class SolarEdgeAdapter(DataSourceAdapter):
    """
    Adapter for the SolarEdge Monitoring API.

    Uses a simple **API key** passed as a query parameter for all requests.
    Module-level data is available via power optimizers.

    Usage::

        adapter = SolarEdgeAdapter(api_key="...")
        ok = adapter.sync_authenticate()
        batch = adapter.sync_fetch_readings("12345", start, end)
    """

    source_name: ClassVar[str] = "solaredge"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = 60.0,
    ) -> None:
        super().__init__()
        self.api_key = api_key or os.getenv("SOLAREDGE_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_s, connect=15.0)
        self._limiter = _SlidingLimiter()
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def _close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        await self._limiter.acquire()
        client = await self._get_client()
        params = params or {}
        params["api_key"] = self.api_key
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # DataSourceAdapter interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        if not self.api_key:
            self.log.warning("solaredge_auth_failed", reason="no_api_key")
            return False
        try:
            data = await self._get("/sites/list", params={"size": 1})
            count = data.get("sites", {}).get("count", 0)
            self.log.info("solaredge_auth_ok", sites=count)
            return True
        except httpx.HTTPStatusError as exc:
            self.log.warning("solaredge_auth_failed", status=exc.response.status_code)
            return False
        except Exception as exc:
            self.log.error("solaredge_auth_error", error=str(exc))
            return False

    async def fetch_readings(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
    ) -> ReadingBatch:
        """
        Fetch power data for a SolarEdge site.

        Uses ``/site/{id}/power`` for 15-minute power values and
        ``/site/{id}/energy`` for energy totals.
        """
        batch = ReadingBatch(source=self.source_name, plant_uid=plant_uid,
                             requested_start=start, requested_end=end)
        try:
            chunk_start = start
            while chunk_start < end:
                chunk_end = min(chunk_start + timedelta(days=MAX_DAYS_PER_CHUNK), end)

                # Fetch power data (15-min resolution)
                power_data = await self._get(
                    f"/site/{plant_uid}/power",
                    params={
                        "startTime": chunk_start.strftime("%Y-%m-%d %H:%M:%S"),
                        "endTime": chunk_end.strftime("%Y-%m-%d %H:%M:%S"),
                    },
                )
                values = power_data.get("power", {}).get("values", [])
                batch.total_raw_records += len(values)

                for raw in values:
                    reading = self._map_power_reading(raw, plant_uid)
                    if reading:
                        batch.readings.append(reading)

                chunk_start = chunk_end

        except Exception as exc:
            batch.errors.append(f"SolarEdge fetch error: {exc}")

        return batch.finalize()

    def _map_power_reading(self, raw: dict, plant_uid: str) -> Reading | None:
        """Map a power value entry from the /power endpoint."""
        ts = raw.get("date")
        if not ts:
            return None
        power_w = raw.get("value")
        try:
            return Reading(
                timestamp=ts,
                plant_uid=plant_uid,
                device_id="site",
                source=self.source_name,
                power_kw=power_w / 1000.0 if power_w is not None else None,
                quality=ReadingQuality.MEASURED,
                quality_score=self.reliability,
                interval_seconds=INTERVAL_SECONDS,
                raw_payload=raw,
            )
        except Exception:
            return None

    async def fetch_equipment_data(
        self,
        site_id: str,
        serial_number: str,
        start: datetime,
        end: datetime,
    ) -> ReadingBatch:
        """
        Fetch detailed equipment (inverter / optimizer) data.

        This provides per-device electrical detail including DC voltage,
        current phases, and power factor.
        """
        batch = ReadingBatch(source=self.source_name, plant_uid=site_id,
                             requested_start=start, requested_end=end)
        try:
            data = await self._get(
                f"/equipment/{site_id}/{serial_number}/data",
                params={
                    "startTime": start.strftime("%Y-%m-%d %H:%M:%S"),
                    "endTime": end.strftime("%Y-%m-%d %H:%M:%S"),
                },
            )
            telemetries = data.get("data", {}).get("telemetries", [])
            batch.total_raw_records = len(telemetries)

            for raw in telemetries:
                mapped = apply_field_mappings(raw, SOLAREDGE_FIELD_MAPPINGS)
                ts = raw.get("date")
                if not ts:
                    continue
                try:
                    reading = Reading(
                        timestamp=ts,
                        plant_uid=site_id,
                        device_id=serial_number,
                        source=self.source_name,
                        quality=ReadingQuality.MEASURED,
                        quality_score=self.reliability,
                        interval_seconds=INTERVAL_SECONDS,
                        raw_payload=raw,
                        **mapped,
                    )
                    batch.readings.append(reading)
                except Exception:
                    continue

        except Exception as exc:
            batch.errors.append(f"Equipment data error: {exc}")

        return batch.finalize()

    async def list_available_plants(self) -> list[dict[str, Any]]:
        try:
            data = await self._get("/sites/list")
            sites = data.get("sites", {}).get("site", [])
            return [
                {
                    "uid": str(s.get("id")),
                    "name": s.get("name", ""),
                    "source": self.source_name,
                    "status": s.get("status", ""),
                    "peak_power_kw": s.get("peakPower"),
                    "install_date": s.get("installationDate"),
                }
                for s in (sites if isinstance(sites, list) else [])
                if s.get("id")
            ]
        except Exception as exc:
            self.log.error("solaredge_list_error", error=str(exc))
            return []

    async def health_check(self) -> HealthStatus:
        t0 = time.monotonic()
        try:
            data = await self._get("/sites/list", params={"size": 1})
            return HealthStatus(
                source=self.source_name,
                state=HealthState.HEALTHY,
                message=f"OK – {data.get('sites', {}).get('count', '?')} sites",
                latency_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            return HealthStatus(
                source=self.source_name,
                state=HealthState.UNHEALTHY,
                message=str(exc)[:200],
                latency_ms=(time.monotonic() - t0) * 1000,
            )

    def get_field_mapping(self) -> list[FieldMapping]:
        return list(SOLAREDGE_FIELD_MAPPINGS)
