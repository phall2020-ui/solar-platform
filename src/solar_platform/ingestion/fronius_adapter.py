"""
Fronius Solar.web API adapter.

Fronius inverters expose monitoring data through the Solar.web portal
and the local Solar API (for on-site access).  This adapter targets the
**Solar.web cloud API** with API-key authentication.

Key endpoints (Solar.web API v1):
    GET  /pvsystems                                     – list PV systems
    GET  /pvsystems/{pvSystemId}/flowdata                – live power flow
    GET  /pvsystems/{pvSystemId}/aggdata/{period}        – aggregated data
    GET  /pvsystems/{pvSystemId}/devices                 – device list
    GET  /pvsystems/{pvSystemId}/devices/{id}/channels   – channel data

Fronius also supports local LAN access via the Fronius Solar API (Symo,
Primo, Gen24).  The local API is not covered here but could be added as
a separate ``FroniusLocalAdapter``.

Environment variables:
    FRONIUS_API_KEY   – Solar.web access key / personal token
    FRONIUS_API_URL   – override (default: https://api.solarweb.com/swqapi)

Resolution: 5-minute
Rate limit: Not formally published; conservative 300 req/15min assumed.
Hybrid inverter support: Yes (battery channels mapped when present).
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

DEFAULT_BASE_URL = os.getenv(
    "FRONIUS_API_URL",
    "https://api.solarweb.com/swqapi",
)
RATE_LIMIT_PER_15MIN = 300
INTERVAL_SECONDS = 300          # 5-minute resolution
MAX_DAYS_PER_CHUNK = 31

# ---------------------------------------------------------------------------
# Field mapping: Fronius → Reading
# ---------------------------------------------------------------------------

FRONIUS_FIELD_MAPPINGS: list[FieldMapping] = [
    # Power & energy
    FieldMapping(vendor_field="P_PV",              reading_field="power_kw", transform="to_kw"),
    FieldMapping(vendor_field="P_Grid",            reading_field="power_kw", transform="to_kw"),
    FieldMapping(vendor_field="E_Day",             reading_field="energy_kwh", transform="to_kwh"),
    FieldMapping(vendor_field="E_Total",           reading_field="energy_kwh", transform="to_kwh"),
    FieldMapping(vendor_field="PAC",               reading_field="power_kw", transform="to_kw"),
    FieldMapping(vendor_field="DAY_ENERGY",        reading_field="energy_kwh", transform="to_kwh"),
    # Voltage / current
    FieldMapping(vendor_field="UAC",               reading_field="voltage_v"),
    FieldMapping(vendor_field="IAC",               reading_field="current_a"),
    FieldMapping(vendor_field="FAC",               reading_field="frequency_hz"),
    FieldMapping(vendor_field="UDC",               reading_field="voltage_v"),
    FieldMapping(vendor_field="IDC",               reading_field="current_a"),
    # Environmental
    FieldMapping(vendor_field="ambientTemperature", reading_field="ambient_temp_c"),
    FieldMapping(vendor_field="moduleTemperature",  reading_field="module_temp_c"),
    FieldMapping(vendor_field="irradiation",        reading_field="poa_wm2"),
    FieldMapping(vendor_field="windSpeed",          reading_field="wind_speed_ms"),
    # Battery (hybrid inverter support)
    FieldMapping(vendor_field="P_Akku",            reading_field="power_kw", transform="to_kw"),
    # Reactive power
    FieldMapping(vendor_field="Q_Total",           reading_field="reactive_power_kvar", transform="to_kw"),
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

class FroniusAdapter(DataSourceAdapter):
    """
    Adapter for the Fronius Solar.web cloud API.

    Uses **API-key** authentication via an ``AccessKeyId`` / ``AccessKeyValue``
    header pair (or a simple bearer token depending on Solar.web version).

    Supports hybrid inverters — battery charge/discharge channels are
    mapped when present in the response.

    Usage::

        adapter = FroniusAdapter(api_key="...")
        ok = adapter.sync_authenticate()
        batch = adapter.sync_fetch_readings("PV_SYSTEM_ID", start, end)
    """

    source_name: ClassVar[str] = "fronius"

    def __init__(
        self,
        api_key: str | None = None,
        access_key_id: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = 60.0,
    ) -> None:
        """
        Args:
            api_key: Solar.web access key value (AccessKeyValue header).
            access_key_id: Solar.web access key ID (AccessKeyId header).
            base_url: API root.
            timeout_s: HTTP timeout.
        """
        super().__init__()
        self.api_key = api_key or os.getenv("FRONIUS_API_KEY", "")
        self.access_key_id = access_key_id or os.getenv("FRONIUS_ACCESS_KEY_ID", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_s, connect=15.0)
        self._limiter = _SlidingLimiter()
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {"Accept": "application/json"}
            if self.access_key_id:
                headers["AccessKeyId"] = self.access_key_id
                headers["AccessKeyValue"] = self.api_key
            else:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=headers,
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
        resp = await client.get(path, params=params or {})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # DataSourceAdapter interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        if not self.api_key:
            self.log.warning("fronius_auth_failed", reason="no_api_key")
            return False
        try:
            data = await self._get("/pvsystems")
            count = len(data.get("pvSystems", data)) if isinstance(data, (dict, list)) else "?"
            self.log.info("fronius_auth_ok", systems=count)
            return True
        except httpx.HTTPStatusError as exc:
            self.log.warning("fronius_auth_failed", status=exc.response.status_code)
            return False
        except Exception as exc:
            self.log.error("fronius_auth_error", error=str(exc))
            return False

    async def fetch_readings(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
    ) -> ReadingBatch:
        """
        Fetch aggregated data for a Fronius PV system.

        Uses the ``/aggdata/5minutes`` endpoint for 5-minute resolution,
        chunked by month to stay within API limits.
        """
        batch = ReadingBatch(source=self.source_name, plant_uid=plant_uid,
                             requested_start=start, requested_end=end)
        try:
            chunk_start = start
            while chunk_start < end:
                chunk_end = min(chunk_start + timedelta(days=MAX_DAYS_PER_CHUNK), end)

                # TODO: Confirm exact aggdata endpoint path and period parameter
                data = await self._get(
                    f"/pvsystems/{plant_uid}/aggdata/5minutes",
                    params={
                        "from": chunk_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "to": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    },
                )

                items = data.get("data", data.get("channels", []))
                if isinstance(items, dict):
                    # Some Fronius endpoints return {channel_name: [values]}
                    items = self._flatten_channel_data(items, chunk_start)

                batch.total_raw_records += len(items)

                for raw in (items if isinstance(items, list) else []):
                    reading = self._map_reading(raw, plant_uid)
                    if reading:
                        batch.readings.append(reading)

                chunk_start = chunk_end

        except Exception as exc:
            batch.errors.append(f"Fronius fetch error: {exc}")

        return batch.finalize()

    def _flatten_channel_data(
        self,
        channels: dict[str, Any],
        base_time: datetime,
    ) -> list[dict]:
        """
        Flatten Fronius channel-based response into a list of time-keyed dicts.

        Some Fronius endpoints return data as::

            {"P_PV": {"values": [{"timestamp": ..., "value": ...}, ...]}, ...}
        """
        merged: dict[str, dict] = {}  # timestamp → {field: value, ...}
        for channel_name, channel_data in channels.items():
            values = channel_data if isinstance(channel_data, list) else channel_data.get("values", [])
            for v in values:
                ts = v.get("timestamp") or v.get("time")
                if not ts:
                    continue
                ts_key = str(ts)
                if ts_key not in merged:
                    merged[ts_key] = {"timestamp": ts}
                merged[ts_key][channel_name] = v.get("value", v.get("val"))
        return list(merged.values())

    def _map_reading(self, raw: dict, plant_uid: str) -> Reading | None:
        ts = raw.get("timestamp") or raw.get("time") or raw.get("logDateTime")
        if not ts:
            return None
        mapped = apply_field_mappings(raw, FRONIUS_FIELD_MAPPINGS)
        try:
            return Reading(
                timestamp=ts,
                plant_uid=plant_uid,
                device_id=raw.get("deviceId", ""),
                source=self.source_name,
                quality=ReadingQuality.MEASURED,
                quality_score=self.reliability,
                interval_seconds=INTERVAL_SECONDS,
                raw_payload=raw,
                **mapped,
            )
        except Exception:
            return None

    async def list_available_plants(self) -> list[dict[str, Any]]:
        try:
            data = await self._get("/pvsystems")
            systems = data.get("pvSystems", data) if isinstance(data, dict) else data
            return [
                {
                    "uid": s.get("pvSystemId") or s.get("id"),
                    "name": s.get("name", ""),
                    "source": self.source_name,
                    "peak_power_kw": s.get("peakPower"),
                }
                for s in (systems if isinstance(systems, list) else [])
                if s.get("pvSystemId") or s.get("id")
            ]
        except Exception as exc:
            self.log.error("fronius_list_error", error=str(exc))
            return []

    async def health_check(self) -> HealthStatus:
        t0 = time.monotonic()
        try:
            data = await self._get("/pvsystems")
            return HealthStatus(
                source=self.source_name,
                state=HealthState.HEALTHY,
                message="OK",
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
        return list(FRONIUS_FIELD_MAPPINGS)
