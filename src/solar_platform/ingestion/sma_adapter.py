"""
SMA Sunny Portal / ennexOS API adapter.

SMA inverters expose monitoring data through the Sunny Portal and the newer
ennexOS platform. Both use **OAuth 2.0** authentication.

Endpoints modelled (ennexOS):
    POST /oauth/token                        – obtain access token
    GET  /v1/plants                          – list plants
    GET  /v1/plants/{id}/measurements        – time-series data

Environment variables:
    SMA_CLIENT_ID     – OAuth2 client ID
    SMA_CLIENT_SECRET – OAuth2 client secret
    SMA_API_URL       – override base URL (optional)
    SMA_USERNAME      – optional (for password grant)
    SMA_PASSWORD      – optional (for password grant)

Resolution: 5-minute data
Rate limit: 300 requests / 15 minutes
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

DEFAULT_BASE_URL = os.getenv("SMA_API_URL", "https://ennexos.sunnyportal.com/api")
RATE_LIMIT_PER_15MIN = 300
INTERVAL_SECONDS = 300          # 5-minute resolution
MAX_DAYS_PER_CHUNK = 31         # conservative chunk size

# ---------------------------------------------------------------------------
# Field mapping: SMA → Reading
# ---------------------------------------------------------------------------

SMA_FIELD_MAPPINGS: list[FieldMapping] = [
    # Power & energy
    FieldMapping(vendor_field="GridMs.TotW",         reading_field="power_kw", transform="to_kw"),
    FieldMapping(vendor_field="Metering.GridMs.TotWhOut", reading_field="energy_kwh", transform="to_kwh"),
    FieldMapping(vendor_field="PvPower",             reading_field="power_kw", transform="to_kw"),
    FieldMapping(vendor_field="TotalYield",          reading_field="energy_kwh", transform="to_kwh"),
    # Voltage / current
    FieldMapping(vendor_field="GridMs.PhV.phsA",     reading_field="voltage_v"),
    FieldMapping(vendor_field="GridMs.A.phsA",       reading_field="current_a"),
    FieldMapping(vendor_field="GridMs.Hz",           reading_field="frequency_hz"),
    # Irradiance (weather station)
    FieldMapping(vendor_field="Wsd.S0.Irr.GHI",     reading_field="ghi_wm2"),
    FieldMapping(vendor_field="Wsd.S0.Irr.POA",     reading_field="poa_wm2"),
    # Temperature
    FieldMapping(vendor_field="Wsd.S0.TmpAmb",      reading_field="ambient_temp_c"),
    FieldMapping(vendor_field="Wsd.S0.TmpMdl",      reading_field="module_temp_c"),
    # Wind
    FieldMapping(vendor_field="Wsd.S0.Wnd",         reading_field="wind_speed_ms"),
    # Reactive / apparent
    FieldMapping(vendor_field="GridMs.TotVAr",       reading_field="reactive_power_kvar", transform="to_kw"),
    FieldMapping(vendor_field="GridMs.TotVA",        reading_field="apparent_power_kva", transform="to_kw"),
    FieldMapping(vendor_field="GridMs.TotPF",        reading_field="power_factor"),
]


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class _SlidingWindowLimiter:
    """Rate limiter with a 15-minute sliding window."""

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
                logger.debug("sma_rate_limit_wait", seconds=round(wait, 1))
                await asyncio.sleep(wait)
        self._calls.append(time.monotonic())


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class SMAAdapter(DataSourceAdapter):
    """
    Adapter for SMA Sunny Portal / ennexOS monitoring API.

    Uses OAuth 2.0 client-credentials or resource-owner-password grant
    for authentication.  Data is available at 5-minute resolution.

    Usage::

        adapter = SMAAdapter(client_id="...", client_secret="...")
        ok = adapter.sync_authenticate()
        batch = adapter.sync_fetch_readings("PLANT123", start, end)
    """

    source_name: ClassVar[str] = "sma"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        username: str | None = None,
        password: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = 60.0,
    ) -> None:
        super().__init__()
        self.client_id = client_id or os.getenv("SMA_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("SMA_CLIENT_SECRET", "")
        self.username = username or os.getenv("SMA_USERNAME", "")
        self.password = password or os.getenv("SMA_PASSWORD", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_s, connect=15.0)
        self._limiter = _SlidingWindowLimiter()
        self._client: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------
    # OAuth 2.0
    # ------------------------------------------------------------------

    async def _ensure_token(self) -> str:
        """Obtain or refresh the OAuth access token."""
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token

        client = await self._get_client()

        # Try client-credentials first, fall back to password grant
        if self.client_id and self.client_secret:
            data: dict[str, str] = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        elif self.username and self.password:
            data = {
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
                "client_id": self.client_id,
            }
        else:
            raise RuntimeError("SMA: neither client_secret nor username/password configured")

        # TODO: Confirm correct token URL for ennexOS
        resp = await client.post("/oauth/token", data=data)
        resp.raise_for_status()
        body = resp.json()
        self._access_token = body["access_token"]
        expires_in = body.get("expires_in", 3600)
        self._token_expires_at = time.monotonic() + expires_in - 60  # refresh 60s early
        self.log.info("sma_token_obtained", expires_in=expires_in)
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
        resp = await client.get(
            path,
            params=params or {},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # DataSourceAdapter interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        try:
            await self._ensure_token()
            return True
        except Exception as exc:
            self.log.warning("sma_auth_failed", error=str(exc))
            return False

    async def fetch_readings(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
    ) -> ReadingBatch:
        batch = ReadingBatch(source=self.source_name, plant_uid=plant_uid,
                             requested_start=start, requested_end=end)
        try:
            chunk_start = start
            while chunk_start < end:
                chunk_end = min(chunk_start + timedelta(days=MAX_DAYS_PER_CHUNK), end)
                # TODO: Confirm exact measurements endpoint path
                data = await self._get(
                    f"/v1/plants/{plant_uid}/measurements",
                    params={
                        "start": chunk_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "end": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "resolution": INTERVAL_SECONDS,
                    },
                )
                items = data.get("measurements", data.get("data", []))
                batch.total_raw_records += len(items)

                for raw in (items if isinstance(items, list) else []):
                    reading = self._map_reading(raw, plant_uid)
                    if reading:
                        batch.readings.append(reading)

                chunk_start = chunk_end

        except Exception as exc:
            batch.errors.append(f"SMA fetch error: {exc}")

        return batch.finalize()

    def _map_reading(self, raw: dict, plant_uid: str) -> Reading | None:
        ts = raw.get("timestamp") or raw.get("time") or raw.get("t")
        if not ts:
            return None
        mapped = apply_field_mappings(raw, SMA_FIELD_MAPPINGS)
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
            data = await self._get("/v1/plants")
            plants = data.get("plants", data.get("data", []))
            return [
                {
                    "uid": p.get("plantId") or p.get("id"),
                    "name": p.get("name", ""),
                    "source": self.source_name,
                }
                for p in (plants if isinstance(plants, list) else [])
                if p.get("plantId") or p.get("id")
            ]
        except Exception as exc:
            self.log.error("sma_list_error", error=str(exc))
            return []

    async def health_check(self) -> HealthStatus:
        t0 = time.monotonic()
        try:
            await self._ensure_token()
            await self._get("/v1/plants")
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
        return list(SMA_FIELD_MAPPINGS)
