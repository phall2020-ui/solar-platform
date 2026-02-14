"""
Juggle Energy direct API adapter.

The Juggle platform (https://app.juggle.energy) is closely related to EMIG but
exposes a slightly different REST surface using Bearer-token auth and a
``/plants/{uid}/devices`` device-tree.  This adapter handles that variant.

Environment variables:
    JUGGLE_API_KEY   – API bearer token
    JUGGLE_BASE_URL  – override for the API root (optional)
"""

from __future__ import annotations

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

# TODO: Confirm actual Juggle API base URL — this is inferred from data_fetcher.py
DEFAULT_BASE_URL = os.getenv(
    "JUGGLE_BASE_URL",
    "https://api.juggle.energy/v1",
)
MAX_DAYS_PER_CHUNK = 104        # from Solar Toolkit data_fetcher.py
RATE_LIMIT_RPM = 60
INTERVAL_SECONDS = 900          # 15-minute default

# ---------------------------------------------------------------------------
# Field mapping: Juggle payload → Reading
#
# Juggle uses the same nested {value, unit} structure as EMIG but may use
# different top-level keys on newer endpoints.
# ---------------------------------------------------------------------------

JUGGLE_FIELD_MAPPINGS: list[FieldMapping] = [
    FieldMapping(vendor_field="apparentPower.value", reading_field="apparent_power_kva"),
    FieldMapping(vendor_field="activePower.value",   reading_field="power_kw"),
    FieldMapping(vendor_field="reactivePower.value",  reading_field="reactive_power_kvar"),
    FieldMapping(vendor_field="voltage.value",        reading_field="voltage_v"),
    FieldMapping(vendor_field="current.value",        reading_field="current_a"),
    FieldMapping(vendor_field="frequency.value",      reading_field="frequency_hz"),
    FieldMapping(vendor_field="powerFactor.value",    reading_field="power_factor"),
    FieldMapping(vendor_field="energy.value",         reading_field="energy_kwh"),
    FieldMapping(vendor_field="yieldTotal.value",     reading_field="energy_kwh"),
    FieldMapping(vendor_field="irradiance.value",     reading_field="poa_wm2"),
    FieldMapping(vendor_field="ambientTemp.value",    reading_field="ambient_temp_c"),
    FieldMapping(vendor_field="moduleTemp.value",     reading_field="module_temp_c"),
    FieldMapping(vendor_field="windSpeed.value",      reading_field="wind_speed_ms"),
]


# ---------------------------------------------------------------------------
# Rate limiter (reusable helper)
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Simple sliding-window rate limiter."""

    def __init__(self, max_calls: int, period_s: float = 60.0) -> None:
        self._max = max_calls
        self._period = period_s
        self._calls: list[float] = []

    async def acquire(self) -> None:
        import asyncio
        now = time.monotonic()
        self._calls = [t for t in self._calls if now - t < self._period]
        if len(self._calls) >= self._max:
            wait = self._period - (now - self._calls[0])
            if wait > 0:
                await asyncio.sleep(wait)
        self._calls.append(time.monotonic())


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class JuggleAdapter(DataSourceAdapter):
    """
    Adapter for the Juggle Energy REST API.

    Navigates the Juggle device tree (``/plants/{uid}/devices``) and
    fetches per-device readings via ``/devices/{emigId}/readings``.

    This adapter is structurally similar to :class:`EMIGAdapter` because
    Juggle powers the EMIG back-end, but it uses **Bearer-token**
    authentication rather than an ``apikey`` query parameter.

    Usage::

        adapter = JuggleAdapter(api_key="380fe299-...")
        ok = adapter.sync_authenticate()
        batch = adapter.sync_fetch_readings("ERS:00001", start, end)
    """

    source_name: ClassVar[str] = "juggle"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        min_interval_s: int = INTERVAL_SECONDS,
        rate_limit_rpm: int = RATE_LIMIT_RPM,
        timeout_s: float = 60.0,
    ) -> None:
        super().__init__()
        self.api_key = api_key or os.getenv("JUGGLE_API_KEY") or os.getenv("JUGGLE_APIKEY", "")
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.min_interval_s = min_interval_s
        self.timeout = httpx.Timeout(timeout_s, connect=15.0)
        self._limiter = _RateLimiter(rate_limit_rpm)
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def _close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Authenticated GET with retry + rate-limit."""
        await self._limiter.acquire()
        client = await self._get_client()
        resp = await client.get(path, params=params or {})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # DataSourceAdapter interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        """Verify bearer token by listing plants."""
        if not self.api_key:
            self.log.warning("juggle_auth_failed", reason="no_api_key")
            return False
        try:
            # TODO: Confirm correct plant-list endpoint for Juggle direct API
            data = await self._get("/plants")
            self.log.info("juggle_auth_ok", plant_count=len(data.get("results", data)) if isinstance(data, (dict, list)) else "?")
            return True
        except httpx.HTTPStatusError as exc:
            self.log.warning("juggle_auth_failed", status=exc.response.status_code)
            return False
        except Exception as exc:
            self.log.error("juggle_auth_error", error=str(exc))
            return False

    async def fetch_readings(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
    ) -> ReadingBatch:
        """Fetch readings for all devices under *plant_uid*."""
        batch = ReadingBatch(source=self.source_name, plant_uid=plant_uid,
                             requested_start=start, requested_end=end)
        try:
            # 1. Device discovery via tree
            device_ids = await self._get_device_ids(plant_uid)
            if not device_ids:
                batch.warnings.append(f"No inverter devices found for {plant_uid}")
                return batch.finalize()

            # 2. Per-device chunked fetch
            for dev_id in device_ids:
                await self._fetch_device(batch, plant_uid, dev_id, start, end)

        except Exception as exc:
            batch.errors.append(f"Fetch error: {exc}")

        return batch.finalize()

    async def _get_device_ids(self, plant_uid: str) -> list[str]:
        """Navigate device tree and return inverter emig IDs."""
        try:
            # TODO: Confirm exact endpoint path
            data = await self._get(f"/plants/{plant_uid}/devices")
            results = data.get("results", data) if isinstance(data, dict) else data
            return [
                d["emigId"]
                for d in (results if isinstance(results, list) else [])
                if d.get("deviceType", "").lower() == "inverter" and "emigId" in d
            ]
        except Exception as exc:
            self.log.error("juggle_device_tree_error", plant_uid=plant_uid, error=str(exc))
            return []

    async def _fetch_device(
        self,
        batch: ReadingBatch,
        plant_uid: str,
        emig_id: str,
        start: datetime,
        end: datetime,
    ) -> None:
        """Fetch readings for one device, chunked by MAX_DAYS_PER_CHUNK."""
        chunk_start = start
        while chunk_start < end:
            chunk_end = min(chunk_start + timedelta(days=MAX_DAYS_PER_CHUNK), end)
            try:
                start_iso = chunk_start.strftime("%Y-%m-%dT%H:%M:%SZ")
                end_iso = chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ")
                # TODO: Confirm reading endpoint path
                data = await self._get(
                    f"/devices/{emig_id}/readings",
                    params={
                        "start": start_iso,
                        "end": end_iso,
                        "minIntervalS": self.min_interval_s,
                    },
                )
                items = data.get("results", data.get("readings", [])) if isinstance(data, dict) else data
                batch.total_raw_records += len(items)

                for raw in (items if isinstance(items, list) else []):
                    reading = self._map_reading(raw, plant_uid, emig_id)
                    if reading:
                        batch.readings.append(reading)

            except Exception as exc:
                batch.errors.append(f"{emig_id} chunk error: {exc}")

            chunk_start = chunk_end

    def _map_reading(self, raw: dict, plant_uid: str, emig_id: str) -> Reading | None:
        ts = raw.get("ts") or raw.get("timestamp")
        if not ts:
            return None
        mapped = apply_field_mappings(raw, JUGGLE_FIELD_MAPPINGS)
        try:
            return Reading(
                timestamp=ts,
                plant_uid=plant_uid,
                device_id=emig_id,
                source=self.source_name,
                quality=ReadingQuality.MEASURED,
                quality_score=self.reliability,
                interval_seconds=self.min_interval_s,
                raw_payload=raw,
                **mapped,
            )
        except Exception:
            return None

    async def list_available_plants(self) -> list[dict[str, Any]]:
        """List plants visible under the Juggle bearer token."""
        try:
            data = await self._get("/plants")
            results = data.get("results", data) if isinstance(data, dict) else data
            out: list[dict[str, Any]] = []
            for p in (results if isinstance(results, list) else []):
                uid = p.get("uid") or p.get("id") or p.get("plantUID")
                name = p.get("name") or p.get("plantName") or "Unknown"
                if uid:
                    out.append({"uid": uid, "name": name, "source": self.source_name})
            return out
        except Exception as exc:
            self.log.error("juggle_list_plants_error", error=str(exc))
            return []

    async def health_check(self) -> HealthStatus:
        t0 = time.monotonic()
        try:
            data = await self._get("/plants")
            latency = (time.monotonic() - t0) * 1000
            cnt = len(data.get("results", data)) if isinstance(data, (dict, list)) else "?"
            return HealthStatus(
                source=self.source_name,
                state=HealthState.HEALTHY,
                message=f"OK – {cnt} plants",
                latency_ms=latency,
            )
        except Exception as exc:
            return HealthStatus(
                source=self.source_name,
                state=HealthState.UNHEALTHY,
                message=str(exc)[:200],
                latency_ms=(time.monotonic() - t0) * 1000,
            )

    def get_field_mapping(self) -> list[FieldMapping]:
        return list(JUGGLE_FIELD_MAPPINGS)
