"""
SolarGIS API adapter — satellite-derived irradiance data.

SolarGIS provides high-resolution (15-min / hourly) irradiance and
meteorological data derived from satellite imagery.  This is the **critical
fallback source** for gap-filling when inverter telemetry is unavailable.

Endpoints modelled:
    POST /datadelivery/request   – submit a data request
    GET  /datadelivery/request/{id}/status
    GET  /datadelivery/request/{id}/data

Environment variables:
    SOLARGIS_API_KEY – API key for SolarGIS Data Delivery API
    SOLARGIS_API_URL – base URL (default: https://solargis.info/api/v2)

Quality score: 0.85 (satellite-derived, not measured)
Rate limit: 1 000 requests/day (standard plan)
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

DEFAULT_BASE_URL = os.getenv("SOLARGIS_API_URL", "https://solargis.info/api/v2")
RATE_LIMIT_DAILY = 1_000       # standard-plan daily limit
RATE_LIMIT_RPM = 15            # conservative per-minute ceiling
INTERVAL_SECONDS = 900         # 15-min default resolution

# ---------------------------------------------------------------------------
# Field mapping: SolarGIS columns → Reading
# ---------------------------------------------------------------------------

SOLARGIS_FIELD_MAPPINGS: list[FieldMapping] = [
    FieldMapping(vendor_field="GHI",  reading_field="ghi_wm2"),
    FieldMapping(vendor_field="DNI",  reading_field="dni_wm2"),
    FieldMapping(vendor_field="DHI",  reading_field="dhi_wm2"),
    FieldMapping(vendor_field="GTI",  reading_field="gti_wm2"),
    FieldMapping(vendor_field="PVOUT", reading_field="power_kw"),   # modelled PV output
    FieldMapping(vendor_field="TEMP", reading_field="ambient_temp_c"),
    FieldMapping(vendor_field="WS",   reading_field="wind_speed_ms"),
    FieldMapping(vendor_field="RH",   reading_field="ambient_temp_c"),  # humidity? fallback
    # POA irradiance: SolarGIS sometimes uses POAI or GTI
    FieldMapping(vendor_field="POAI", reading_field="poa_wm2"),
]


# ---------------------------------------------------------------------------
# Rate limiter — daily + per-minute dual bucket
# ---------------------------------------------------------------------------

class _DualRateLimiter:
    """Enforces both a per-minute and a daily request ceiling."""

    def __init__(self, rpm: int = RATE_LIMIT_RPM, daily: int = RATE_LIMIT_DAILY) -> None:
        self._rpm = rpm
        self._daily = daily
        self._minute_calls: list[float] = []
        self._day_counter: int = 0
        self._day_reset: float = time.monotonic() + 86_400

    async def acquire(self) -> None:
        now = time.monotonic()

        # Daily reset
        if now >= self._day_reset:
            self._day_counter = 0
            self._day_reset = now + 86_400

        if self._day_counter >= self._daily:
            raise RuntimeError(
                f"SolarGIS daily rate limit reached ({self._daily} req/day). "
                "Try again tomorrow or upgrade your plan."
            )

        # Per-minute window
        self._minute_calls = [t for t in self._minute_calls if now - t < 60.0]
        if len(self._minute_calls) >= self._rpm:
            wait = 60.0 - (now - self._minute_calls[0])
            if wait > 0:
                await asyncio.sleep(wait)

        self._minute_calls.append(time.monotonic())
        self._day_counter += 1


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class SolarGISAdapter(DataSourceAdapter):
    """
    Adapter for the SolarGIS Data Delivery API.

    Fetches satellite-derived irradiance (GHI, DNI, DHI, GTI) and
    meteorological data for a given lat/lon.  Primarily used as a
    **gap-filling fallback** when inverter telemetry is missing.

    Usage::

        adapter = SolarGISAdapter(api_key="...", latitude=51.5, longitude=-0.1)
        ok = adapter.sync_authenticate()
        batch = adapter.sync_fetch_readings("SITE:001", start, end)

    Note:
        SolarGIS is location-based, not plant-UID-based.  The adapter
        requires latitude/longitude configuration per plant.  A mapping
        dict ``plant_locations`` can be passed to the constructor.
    """

    source_name: ClassVar[str] = "solargis"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        plant_locations: dict[str, tuple[float, float]] | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        """
        Args:
            api_key: SolarGIS API key.
            base_url: API root URL.
            plant_locations: Mapping of ``plant_uid → (latitude, longitude)``.
            timeout_s: HTTP timeout in seconds (SolarGIS can be slow).
        """
        super().__init__()
        self.api_key = api_key or os.getenv("SOLARGIS_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.plant_locations: dict[str, tuple[float, float]] = plant_locations or {}
        self.timeout = httpx.Timeout(timeout_s, connect=20.0)
        self._limiter = _DualRateLimiter()
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Location helpers
    # ------------------------------------------------------------------

    def set_plant_location(self, plant_uid: str, lat: float, lon: float) -> None:
        """Register a plant's coordinates for satellite lookups."""
        self.plant_locations[plant_uid] = (lat, lon)

    # ------------------------------------------------------------------
    # HTTP
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
        wait=wait_exponential(multiplier=2, min=3, max=60),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        await self._limiter.acquire()
        client = await self._get_client()
        resp = await client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # DataSourceAdapter interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        """Validate API key with a lightweight info request."""
        if not self.api_key:
            self.log.warning("solargis_auth_failed", reason="no_api_key")
            return False
        try:
            # TODO: Confirm actual SolarGIS auth/health endpoint
            await self._request("GET", "/user/info")
            self.log.info("solargis_auth_ok")
            return True
        except httpx.HTTPStatusError as exc:
            self.log.warning("solargis_auth_failed", status=exc.response.status_code)
            return False
        except Exception as exc:
            self.log.error("solargis_auth_error", error=str(exc))
            return False

    async def fetch_readings(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
    ) -> ReadingBatch:
        """
        Fetch satellite-derived irradiance data for a plant location.

        The plant must have coordinates registered via
        :meth:`set_plant_location` or the ``plant_locations`` init kwarg.
        """
        batch = ReadingBatch(source=self.source_name, plant_uid=plant_uid,
                             requested_start=start, requested_end=end)

        loc = self.plant_locations.get(plant_uid)
        if not loc:
            batch.errors.append(
                f"No coordinates registered for {plant_uid}. "
                "Call set_plant_location(uid, lat, lon) first."
            )
            return batch.finalize()

        lat, lon = loc

        try:
            # TODO: Replace with actual SolarGIS Data Delivery request flow
            # Step 1: Submit data request
            request_body = {
                "location": {"latitude": lat, "longitude": lon},
                "timeRange": {
                    "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "to": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                "columns": ["GHI", "DNI", "DHI", "GTI", "TEMP", "WS", "POAI"],
                "timeResolution": "PT15M",
            }
            submit_resp = await self._request(
                "POST", "/datadelivery/request", json=request_body
            )
            request_id = submit_resp.get("requestId") or submit_resp.get("id")

            if not request_id:
                batch.errors.append("SolarGIS did not return a request ID")
                return batch.finalize()

            # Step 2: Poll for completion (max ~5 min)
            data_rows = await self._poll_for_data(request_id, timeout_s=300)
            batch.total_raw_records = len(data_rows)

            # Step 3: Map rows to readings
            for row in data_rows:
                reading = self._map_reading(row, plant_uid)
                if reading:
                    batch.readings.append(reading)

        except RuntimeError as exc:
            # Daily rate limit
            batch.errors.append(str(exc))
        except Exception as exc:
            batch.errors.append(f"SolarGIS fetch error: {exc}")

        return batch.finalize()

    async def _poll_for_data(
        self,
        request_id: str,
        timeout_s: float = 300,
        poll_interval_s: float = 5.0,
    ) -> list[dict]:
        """Poll the status endpoint until data is ready or timeout."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            status = await self._request("GET", f"/datadelivery/request/{request_id}/status")
            state = status.get("status", "").lower()
            if state == "completed":
                data_resp = await self._request("GET", f"/datadelivery/request/{request_id}/data")
                return data_resp.get("rows", data_resp.get("data", []))
            if state in ("failed", "error"):
                raise RuntimeError(f"SolarGIS request {request_id} failed: {status}")
            await asyncio.sleep(poll_interval_s)

        raise TimeoutError(f"SolarGIS request {request_id} did not complete within {timeout_s}s")

    def _map_reading(self, raw: dict, plant_uid: str) -> Reading | None:
        ts = raw.get("timestamp") or raw.get("dateTime") or raw.get("time")
        if not ts:
            return None
        mapped = apply_field_mappings(raw, SOLARGIS_FIELD_MAPPINGS)
        try:
            return Reading(
                timestamp=ts,
                plant_uid=plant_uid,
                device_id="satellite",
                source=self.source_name,
                quality=ReadingQuality.SATELLITE,
                quality_score=self.reliability,
                interval_seconds=INTERVAL_SECONDS,
                raw_payload=raw,
                **mapped,
            )
        except Exception:
            return None

    async def list_available_plants(self) -> list[dict[str, Any]]:
        """
        SolarGIS is location-based — returns plants that have registered coordinates.
        """
        return [
            {"uid": uid, "name": uid, "source": self.source_name,
             "latitude": loc[0], "longitude": loc[1]}
            for uid, loc in self.plant_locations.items()
        ]

    async def health_check(self) -> HealthStatus:
        t0 = time.monotonic()
        try:
            await self._request("GET", "/user/info")
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
        return list(SOLARGIS_FIELD_MAPPINGS)
