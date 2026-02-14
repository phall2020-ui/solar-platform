"""
Enphase Enlighten API v4 adapter.

Enphase microinverters provide **panel-level** monitoring data via the
Enlighten API v4.  This adapter supports OAuth 2.0 authentication and
retrieves per-microinverter 5-minute telemetry.

Key endpoints:
    POST /oauth/token                          – OAuth2 token
    GET  /api/v4/systems                       – list systems
    GET  /api/v4/systems/{id}/telemetry        – system-level telemetry
    GET  /api/v4/systems/{id}/devices/micros   – microinverter-level data

Environment variables:
    ENPHASE_CLIENT_ID     – OAuth2 client ID
    ENPHASE_CLIENT_SECRET – OAuth2 client secret
    ENPHASE_API_KEY       – Enlighten API key
    ENPHASE_API_URL       – override base URL (optional)

Resolution: 5-minute
Rate limit: 10 000 requests / day (standard plan)
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

DEFAULT_BASE_URL = os.getenv("ENPHASE_API_URL", "https://api.enphaseenergy.com")
RATE_LIMIT_DAILY = 10_000
RATE_LIMIT_RPM = 30             # keep well within burst limits
INTERVAL_SECONDS = 300          # 5-minute resolution
MAX_DAYS_PER_CHUNK = 7          # Enphase prefers short ranges for telemetry

# ---------------------------------------------------------------------------
# Field mapping: Enphase telemetry → Reading
# ---------------------------------------------------------------------------

ENPHASE_FIELD_MAPPINGS: list[FieldMapping] = [
    # System-level telemetry
    FieldMapping(vendor_field="powr",          reading_field="power_kw", transform="to_kw"),
    FieldMapping(vendor_field="enwh",          reading_field="energy_kwh", transform="to_kwh"),
    # Micro-inverter level
    FieldMapping(vendor_field="ac_power",      reading_field="power_kw", transform="to_kw"),
    FieldMapping(vendor_field="ac_voltage",    reading_field="voltage_v"),
    FieldMapping(vendor_field="dc_voltage",    reading_field="voltage_v"),      # DC side
    FieldMapping(vendor_field="dc_current",    reading_field="current_a"),
    # Environmental (if weather station connected)
    FieldMapping(vendor_field="temperature",   reading_field="ambient_temp_c"),
    FieldMapping(vendor_field="irradiance",    reading_field="poa_wm2"),
]


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class _DailyRateLimiter:
    def __init__(self, rpm: int = RATE_LIMIT_RPM, daily: int = RATE_LIMIT_DAILY) -> None:
        self._rpm = rpm
        self._daily = daily
        self._minute_calls: list[float] = []
        self._day_count = 0
        self._day_reset = time.monotonic() + 86_400

    async def acquire(self) -> None:
        now = time.monotonic()
        if now >= self._day_reset:
            self._day_count = 0
            self._day_reset = now + 86_400
        if self._day_count >= self._daily:
            raise RuntimeError(f"Enphase daily limit reached ({self._daily}/day)")
        self._minute_calls = [t for t in self._minute_calls if now - t < 60]
        if len(self._minute_calls) >= self._rpm:
            wait = 60.0 - (now - self._minute_calls[0])
            if wait > 0:
                await asyncio.sleep(wait)
        self._minute_calls.append(time.monotonic())
        self._day_count += 1


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class EnphaseAdapter(DataSourceAdapter):
    """
    Adapter for the Enphase Enlighten API v4.

    Supports both **system-level** and **microinverter-level** telemetry,
    making it uniquely suitable for panel-level monitoring and diagnostics.

    Usage::

        adapter = EnphaseAdapter(
            client_id="...",
            client_secret="...",
            api_key="...",
        )
        ok = adapter.sync_authenticate()
        plants = adapter.sync_list_available_plants()
        batch = adapter.sync_fetch_readings(plants[0]["uid"], start, end)
    """

    source_name: ClassVar[str] = "enphase"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        fetch_micro_level: bool = False,
        timeout_s: float = 60.0,
    ) -> None:
        """
        Args:
            client_id: OAuth2 client ID.
            client_secret: OAuth2 client secret.
            api_key: Enlighten developer API key.
            base_url: API root.
            fetch_micro_level: If True, fetch per-microinverter data (slower).
            timeout_s: HTTP request timeout.
        """
        super().__init__()
        self.client_id = client_id or os.getenv("ENPHASE_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("ENPHASE_CLIENT_SECRET", "")
        self.api_key = api_key or os.getenv("ENPHASE_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.fetch_micro_level = fetch_micro_level
        self.timeout = httpx.Timeout(timeout_s, connect=15.0)
        self._limiter = _DailyRateLimiter()
        self._client: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------
    # OAuth 2.0
    # ------------------------------------------------------------------

    async def _ensure_token(self) -> str:
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token

        client = await self._get_client()
        # TODO: Confirm Enphase OAuth URL — may need user authorization code flow
        resp = await client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        self._access_token = body["access_token"]
        self._token_expires_at = time.monotonic() + body.get("expires_in", 3600) - 60
        return self._access_token

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
        token = await self._ensure_token()
        client = await self._get_client()
        params = params or {}
        params["key"] = self.api_key  # Enphase requires API key as query param
        resp = await client.get(
            path,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # DataSourceAdapter interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        if not self.client_id or not self.client_secret:
            self.log.warning("enphase_auth_failed", reason="missing_credentials")
            return False
        try:
            await self._ensure_token()
            return True
        except Exception as exc:
            self.log.warning("enphase_auth_failed", error=str(exc))
            return False

    async def fetch_readings(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
    ) -> ReadingBatch:
        """
        Fetch telemetry for an Enphase system.

        By default fetches system-level data.  Set ``fetch_micro_level=True``
        on the adapter to also pull per-microinverter readings.
        """
        batch = ReadingBatch(source=self.source_name, plant_uid=plant_uid,
                             requested_start=start, requested_end=end)
        try:
            chunk_start = start
            while chunk_start < end:
                chunk_end = min(chunk_start + timedelta(days=MAX_DAYS_PER_CHUNK), end)

                # --- System-level telemetry ---
                start_epoch = int(chunk_start.timestamp())
                end_epoch = int(chunk_end.timestamp())
                # TODO: Confirm endpoint path and parameter names
                data = await self._get(
                    f"/api/v4/systems/{plant_uid}/telemetry",
                    params={
                        "start_at": start_epoch,
                        "end_at": end_epoch,
                        "granularity": "5mins",
                    },
                )
                intervals = data.get("intervals", data.get("data", []))
                batch.total_raw_records += len(intervals)

                for raw in (intervals if isinstance(intervals, list) else []):
                    reading = self._map_reading(raw, plant_uid, device_id="system")
                    if reading:
                        batch.readings.append(reading)

                # --- Micro-inverter level (optional) ---
                if self.fetch_micro_level:
                    await self._fetch_micro_data(batch, plant_uid, chunk_start, chunk_end)

                chunk_start = chunk_end

        except RuntimeError as exc:
            batch.errors.append(str(exc))  # daily limit
        except Exception as exc:
            batch.errors.append(f"Enphase fetch error: {exc}")

        return batch.finalize()

    async def _fetch_micro_data(
        self,
        batch: ReadingBatch,
        system_id: str,
        start: datetime,
        end: datetime,
    ) -> None:
        """Fetch per-microinverter telemetry (expensive — high API call count)."""
        try:
            # TODO: Confirm micro-inverter data endpoint
            data = await self._get(
                f"/api/v4/systems/{system_id}/devices/micros",
                params={
                    "start_at": int(start.timestamp()),
                    "end_at": int(end.timestamp()),
                },
            )
            micros = data.get("micro_inverters", data.get("devices", []))
            for micro in (micros if isinstance(micros, list) else []):
                serial = micro.get("serial_number", micro.get("id", "unknown"))
                intervals = micro.get("intervals", [])
                batch.total_raw_records += len(intervals)
                for raw in intervals:
                    reading = self._map_reading(raw, system_id, device_id=serial)
                    if reading:
                        batch.readings.append(reading)
        except Exception as exc:
            batch.warnings.append(f"Micro-inverter fetch failed: {exc}")

    def _map_reading(self, raw: dict, plant_uid: str, device_id: str = "") -> Reading | None:
        # Enphase uses epoch timestamps
        ts = raw.get("end_at") or raw.get("timestamp") or raw.get("powr_date")
        if ts is None:
            return None
        if isinstance(ts, (int, float)):
            ts = datetime.fromtimestamp(ts, tz=timezone.utc)

        mapped = apply_field_mappings(raw, ENPHASE_FIELD_MAPPINGS)
        try:
            return Reading(
                timestamp=ts,
                plant_uid=plant_uid,
                device_id=device_id,
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
            data = await self._get("/api/v4/systems")
            systems = data.get("systems", [])
            return [
                {
                    "uid": str(s.get("system_id", s.get("id"))),
                    "name": s.get("name", ""),
                    "source": self.source_name,
                    "module_count": s.get("modules", 0),
                }
                for s in (systems if isinstance(systems, list) else [])
                if s.get("system_id") or s.get("id")
            ]
        except Exception as exc:
            self.log.error("enphase_list_error", error=str(exc))
            return []

    async def health_check(self) -> HealthStatus:
        t0 = time.monotonic()
        try:
            await self._ensure_token()
            await self._get("/api/v4/systems")
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
        return list(ENPHASE_FIELD_MAPPINGS)
