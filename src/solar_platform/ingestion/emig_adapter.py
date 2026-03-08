"""
EMIG / Juggle Energy API adapter.

Migrates and enhances the existing EMIG integration from ``toolkit_bridge.py``
and ``Solar Toolkit/juggle_crawler.py`` into the new ``DataSourceAdapter``
interface.  Uses **httpx** for async HTTP, adds exponential-backoff retries,
rate-limiting (60 req/min), and maps EMIG's nested payload to the standard
``Reading`` model.

Environment variables / config:
    EMIG_API_KEY   – API key for the EMIG platform
    JUGGLE_API_KEY – alias (legacy compat)
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

import httpx
import structlog
from dateutil import parser as date_parser
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from solar_platform.ingestion.base import (
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

DEFAULT_BASE_URL = "https://www.emig.co.uk/p/api"
MAX_DAYS_PER_CHUNK = 90          # API returns 413 if too much data is requested
RATE_LIMIT_RPM = 60              # conservative requests-per-minute
INTERVAL_SECONDS = 900           # 15-minute data resolution (default)
MIN_INTERVAL_S = 900             # minimum interval supported by EMIG API

# ---------------------------------------------------------------------------
# Field mapping: EMIG payload → Reading
# ---------------------------------------------------------------------------

EMIG_FIELD_MAPPINGS: list[FieldMapping] = [
    FieldMapping(vendor_field="apparentPower.value", reading_field="apparent_power_kva"),
    FieldMapping(vendor_field="activePower.value",   reading_field="power_kw"),
    FieldMapping(vendor_field="reactivePower.value",  reading_field="reactive_power_kvar"),
    FieldMapping(vendor_field="voltage.value",        reading_field="voltage_v"),
    FieldMapping(vendor_field="current.value",        reading_field="current_a"),
    FieldMapping(vendor_field="frequency.value",      reading_field="frequency_hz"),
    FieldMapping(vendor_field="powerFactor.value",    reading_field="power_factor"),
    FieldMapping(vendor_field="energy.value",         reading_field="energy_kwh"),
    # Weather sensors (if present on weather device)
    FieldMapping(vendor_field="irradiance.value",     reading_field="poa_wm2"),
    FieldMapping(vendor_field="ambientTemp.value",    reading_field="ambient_temp_c"),
    FieldMapping(vendor_field="moduleTemp.value",     reading_field="module_temp_c"),
    FieldMapping(vendor_field="windSpeed.value",      reading_field="wind_speed_ms"),
]


# ---------------------------------------------------------------------------
# Simple token-bucket rate limiter
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Sliding-window token-bucket rate limiter."""

    def __init__(self, max_calls: int, period_seconds: float = 60.0) -> None:
        self._max = max_calls
        self._period = period_seconds
        self._calls: list[float] = []

    async def acquire(self) -> None:
        now = time.monotonic()
        self._calls = [t for t in self._calls if now - t < self._period]
        if len(self._calls) >= self._max:
            sleep_for = self._period - (now - self._calls[0])
            if sleep_for > 0:
                logger.debug("emig_rate_limit_wait", sleep_seconds=round(sleep_for, 2))
                import asyncio
                await asyncio.sleep(sleep_for)
        self._calls.append(time.monotonic())


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class EMIGAdapter(DataSourceAdapter):
    """
    Adapter for the EMIG / Juggle Energy monitoring API.

    This is the *primary* data source for the AMPYR Solar portfolio and has
    the highest reliability score (0.95).

    Usage::

        adapter = EMIGAdapter(api_key="...")
        ok = adapter.sync_authenticate()
        batch = adapter.sync_fetch_readings("ERS:00001", start, end)
    """

    source_name: ClassVar[str] = "emig"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        min_interval_s: int = MIN_INTERVAL_S,
        rate_limit_rpm: int = RATE_LIMIT_RPM,
        timeout_s: float = 60.0,
    ) -> None:
        super().__init__()
        self.api_key = api_key or os.getenv("EMIG_API_KEY") or os.getenv("JUGGLE_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.min_interval_s = min_interval_s
        self.timeout = httpx.Timeout(timeout_s, connect=15.0)
        self._rate_limiter = _RateLimiter(rate_limit_rpm)
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # HTTP helpers
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
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        """
        Make an authenticated GET request with retry & rate-limiting.

        Raises:
            httpx.HTTPStatusError: on 4xx/5xx responses (after retries)
        """
        await self._rate_limiter.acquire()
        client = await self._get_client()
        params = params or {}
        params["apikey"] = self.api_key
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # DataSourceAdapter interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        """
        Validate the API key by making a lightweight call to ``/plant-list``.

        Returns True if the key is accepted.
        """
        if not self.api_key:
            self.log.warning("emig_auth_failed", reason="no_api_key")
            return False
        try:
            data = await self._get("/plant-list")
            self.log.info("emig_auth_ok", plant_count=len(data) if isinstance(data, list) else "?")
            return True
        except httpx.HTTPStatusError as exc:
            self.log.warning("emig_auth_failed", status=exc.response.status_code)
            return False
        except Exception as exc:
            self.log.error("emig_auth_error", error=str(exc))
            return False

    async def fetch_readings(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
    ) -> ReadingBatch:
        """
        Fetch readings for all inverters of a plant over ``[start, end]``.

        The date range is automatically chunked into ≤90-day windows to
        stay within the EMIG API's payload limits.
        """
        batch = ReadingBatch(source=self.source_name, plant_uid=plant_uid,
                             requested_start=start, requested_end=end)

        try:
            # 1. Discover devices
            details = await self._get(f"/plant/{plant_uid}")
            meters = details.get("meters", [])
            inverter_ids = [
                m["emigId"] for m in meters
                if m.get("type") == "INVERTER" and "emigId" in m
            ]
            if not inverter_ids:
                batch.warnings.append(f"No inverters found for plant {plant_uid}")
                return batch.finalize()

            # 2. Fetch readings per device, chunked by date
            for emig_id in inverter_ids:
                await self._fetch_device_readings(batch, plant_uid, emig_id, start, end)

        except httpx.HTTPStatusError as exc:
            batch.errors.append(f"HTTP {exc.response.status_code}: {exc.response.text[:200]}")
        except Exception as exc:
            batch.errors.append(f"Unexpected error: {exc}")

        return batch.finalize()

    async def _fetch_device_readings(
        self,
        batch: ReadingBatch,
        plant_uid: str,
        emig_id: str,
        start: datetime,
        end: datetime,
    ) -> None:
        """Fetch and map readings for a single device, chunking by MAX_DAYS_PER_CHUNK."""
        chunk_start = start
        while chunk_start < end:
            chunk_end = min(chunk_start + timedelta(days=MAX_DAYS_PER_CHUNK), end)
            try:
                raw_readings = await self._get(
                    f"/meter/{emig_id}/readings",
                    params={
                        "startDate": chunk_start.strftime("%Y%m%d"),
                        "endDate": chunk_end.strftime("%Y%m%d"),
                        "minIntervalS": self.min_interval_s,
                    },
                )

                items = raw_readings.get("readings", []) if isinstance(raw_readings, dict) else raw_readings
                batch.total_raw_records += len(items)

                for raw in items:
                    reading = self._map_reading(raw, plant_uid, emig_id)
                    if reading is not None:
                        batch.readings.append(reading)

                self.log.debug(
                    "emig_chunk_fetched",
                    device=emig_id,
                    chunk_start=str(chunk_start.date()),
                    chunk_end=str(chunk_end.date()),
                    count=len(items),
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 413:
                    batch.warnings.append(
                        f"413 Payload Too Large for {emig_id} "
                        f"({chunk_start.date()}–{chunk_end.date()}). Try smaller range."
                    )
                else:
                    batch.errors.append(
                        f"HTTP {exc.response.status_code} for {emig_id}: "
                        f"{exc.response.text[:200]}"
                    )
            except Exception as exc:
                batch.errors.append(f"Error fetching {emig_id}: {exc}")

            chunk_start = chunk_end

    def _map_reading(
        self,
        raw: dict[str, Any],
        plant_uid: str,
        emig_id: str,
    ) -> Reading | None:
        """Map a single EMIG API reading dict to a ``Reading``."""
        ts_raw = raw.get("ts") or raw.get("timestamp")
        if not ts_raw:
            return None

        mapped = apply_field_mappings(raw, EMIG_FIELD_MAPPINGS)
        parsed_timestamp = self._parse_timestamp(ts_raw)
        if parsed_timestamp is None:
            self.log.debug("emig_map_error", device=emig_id, ts=ts_raw, error="unparseable timestamp")
            return None

        try:
            reading = Reading(
                timestamp=parsed_timestamp,
                plant_uid=plant_uid,
                device_id=emig_id,
                source=self.source_name,
                quality=ReadingQuality.MEASURED,
                quality_score=self.reliability,
                interval_seconds=self.min_interval_s,
                raw_payload=raw,
                **mapped,
            )
            # Track last timestamp for incremental fetch
            self.set_last_fetch_ts(plant_uid, reading.timestamp)
            return reading
        except Exception as exc:
            self.log.debug("emig_map_error", device=emig_id, ts=ts_raw, error=str(exc))
            return None

    def _parse_timestamp(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

        text = str(value).strip()
        if not text:
            return None

        normalised = text.replace("Z", "+00:00")
        for candidate in (normalised, text):
            try:
                parsed = date_parser.isoparse(candidate)
                return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
        return None

    async def list_available_plants(self) -> list[dict[str, Any]]:
        """
        List all plants visible to the configured API key.

        Returns a list of dicts with ``uid``, ``name``, and ``inverter_count``.
        """
        raw_plants = await self._get("/plant-list")
        result: list[dict[str, Any]] = []
        for p in (raw_plants if isinstance(raw_plants, list) else []):
            uid = p.get("uid") or p.get("id") or p.get("plantUID")
            name = p.get("name") or p.get("plantName") or "Unknown"
            if uid:
                result.append({"uid": uid, "name": name, "source": self.source_name})
        return result

    async def health_check(self) -> HealthStatus:
        """Ping the plant-list endpoint to verify connectivity."""
        t0 = time.monotonic()
        try:
            data = await self._get("/plant-list")
            latency = (time.monotonic() - t0) * 1000
            return HealthStatus(
                source=self.source_name,
                state=HealthState.HEALTHY,
                message=f"OK – {len(data) if isinstance(data, list) else '?'} plants visible",
                latency_ms=latency,
            )
        except Exception as exc:
            latency = (time.monotonic() - t0) * 1000
            return HealthStatus(
                source=self.source_name,
                state=HealthState.UNHEALTHY,
                message=str(exc)[:200],
                latency_ms=latency,
            )

    def get_field_mapping(self) -> list[FieldMapping]:
        """Return the EMIG field-mapping table."""
        return list(EMIG_FIELD_MAPPINGS)
