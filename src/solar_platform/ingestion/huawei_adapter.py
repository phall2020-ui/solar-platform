"""
Huawei FusionSolar northbound API adapter.

Huawei exposes monitoring data through the iMaster NetEco / FusionSolar
northbound interface using **OAuth 2.0** authentication.

Key endpoints:
    POST /thirdData/login                      – obtain XSRF token
    POST /thirdData/getStationList             – list stations
    POST /thirdData/getDevList                 – list devices for station
    POST /thirdData/getKpiStationHour          – hourly KPIs
    POST /thirdData/getKpiStationDay           – daily KPIs
    POST /thirdData/getDevRealKpi              – real-time device KPIs
    POST /thirdData/getDevHistoryKpi           – historical device KPIs

Environment variables:
    HUAWEI_USERNAME – FusionSolar account
    HUAWEI_PASSWORD – system code (not user password)
    HUAWEI_API_URL  – override (default: https://intl.fusionsolar.huawei.com)

Resolution: 5-minute (real-time) / hourly (historical KPIs)
Rate limit: ~300 req/15min (undocumented; conservative)
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
    "HUAWEI_API_URL",
    "https://intl.fusionsolar.huawei.com/thirdData",
)
RATE_LIMIT_PER_15MIN = 300
INTERVAL_SECONDS = 300          # 5-minute resolution
MAX_DAYS_PER_CHUNK = 30

# ---------------------------------------------------------------------------
# Field mapping: Huawei KPIs → Reading
# ---------------------------------------------------------------------------

HUAWEI_FIELD_MAPPINGS: list[FieldMapping] = [
    # Real-time / historical KPIs (device-level)
    FieldMapping(vendor_field="active_power",        reading_field="power_kw"),
    FieldMapping(vendor_field="power_profit",        reading_field="energy_kwh"),
    FieldMapping(vendor_field="day_cap",             reading_field="energy_kwh"),
    FieldMapping(vendor_field="mppt_power",          reading_field="power_kw"),
    # DC string data
    FieldMapping(vendor_field="pv_u",                reading_field="voltage_v"),
    FieldMapping(vendor_field="pv_i",                reading_field="current_a"),
    # AC side
    FieldMapping(vendor_field="a_u",                 reading_field="voltage_v"),
    FieldMapping(vendor_field="a_i",                 reading_field="current_a"),
    FieldMapping(vendor_field="elec_freq",           reading_field="frequency_hz"),
    FieldMapping(vendor_field="reactive_power",      reading_field="reactive_power_kvar"),
    FieldMapping(vendor_field="power_factor",        reading_field="power_factor"),
    # Environmental (weather station / logger)
    FieldMapping(vendor_field="radiation_intensity",  reading_field="poa_wm2"),
    FieldMapping(vendor_field="theory_power",         reading_field="power_kw"),
    FieldMapping(vendor_field="temperature",          reading_field="ambient_temp_c"),
    FieldMapping(vendor_field="wind_speed",           reading_field="wind_speed_ms"),
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

class HuaweiAdapter(DataSourceAdapter):
    """
    Adapter for the Huawei FusionSolar northbound API.

    FusionSolar uses a **POST-based** API where every request (including
    reads) is a POST with a JSON body.  Authentication returns an XSRF
    token that must be sent as a cookie on subsequent requests.

    Usage::

        adapter = HuaweiAdapter(username="...", password="<system_code>")
        ok = adapter.sync_authenticate()
        batch = adapter.sync_fetch_readings("STATION_123", start, end)
    """

    source_name: ClassVar[str] = "huawei"

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = 60.0,
    ) -> None:
        super().__init__()
        self.username = username or os.getenv("HUAWEI_USERNAME", "")
        self.password = password or os.getenv("HUAWEI_PASSWORD", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_s, connect=15.0)
        self._limiter = _SlidingLimiter()
        self._client: httpx.AsyncClient | None = None
        self._xsrf_token: str | None = None
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------
    # Auth – Huawei uses XSRF token via login endpoint
    # ------------------------------------------------------------------

    async def _login(self) -> str:
        """Obtain XSRF token from FusionSolar login endpoint."""
        client = await self._get_client()
        resp = await client.post(
            f"{self.base_url}/login",
            json={
                "userName": self.username,
                "systemCode": self.password,
            },
        )
        resp.raise_for_status()
        body = resp.json()

        if body.get("failCode") == 305:
            raise RuntimeError("Huawei: Invalid credentials (failCode 305)")
        if body.get("failCode"):
            raise RuntimeError(f"Huawei login failed: {body}")

        # XSRF token comes in Set-Cookie header
        xsrf = resp.cookies.get("XSRF-TOKEN") or resp.headers.get("xsrf-token")
        if not xsrf:
            # Some deployments return it in the body
            xsrf = body.get("data", {}).get("token") if isinstance(body.get("data"), dict) else None

        if not xsrf:
            raise RuntimeError("Huawei: No XSRF token in login response")

        self._xsrf_token = xsrf
        self._token_expires_at = time.monotonic() + 1800  # 30-min session
        self.log.info("huawei_login_ok")
        return xsrf

    async def _ensure_token(self) -> str:
        if self._xsrf_token and time.monotonic() < self._token_expires_at:
            return self._xsrf_token
        return await self._login()

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
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
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _post(self, endpoint: str, body: dict[str, Any] | None = None) -> Any:
        """Make an authenticated POST request."""
        await self._limiter.acquire()
        token = await self._ensure_token()
        client = await self._get_client()
        resp = await client.post(
            f"{self.base_url}/{endpoint.lstrip('/')}",
            json=body or {},
            headers={"XSRF-TOKEN": token},
            cookies={"XSRF-TOKEN": token},
        )
        resp.raise_for_status()
        data = resp.json()

        # Huawei wraps responses: {"success": true, "failCode": 0, "data": ...}
        if not data.get("success", True):
            code = data.get("failCode", "unknown")
            raise RuntimeError(f"Huawei API error (failCode={code}): {data.get('message', '')}")

        return data.get("data", data)

    # ------------------------------------------------------------------
    # DataSourceAdapter interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        if not self.username or not self.password:
            self.log.warning("huawei_auth_failed", reason="missing_credentials")
            return False
        try:
            await self._login()
            return True
        except Exception as exc:
            self.log.warning("huawei_auth_failed", error=str(exc))
            return False

    async def fetch_readings(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
    ) -> ReadingBatch:
        """
        Fetch device KPIs for a Huawei FusionSolar station.

        Uses ``getDevHistoryKpi`` for historical data chunked by day,
        falling back to ``getKpiStationHour`` for station-level data.
        """
        batch = ReadingBatch(source=self.source_name, plant_uid=plant_uid,
                             requested_start=start, requested_end=end)
        try:
            # 1. Get devices for this station
            devices = await self._get_devices(plant_uid)
            inverter_ids = [
                d.get("devId") or d.get("id")
                for d in devices
                if d.get("devTypeId") in (1, 38, 39)  # 1=inverter, 38=optimizer, 39=logger
                and (d.get("devId") or d.get("id"))
            ]

            if not inverter_ids:
                batch.warnings.append(f"No inverters found for station {plant_uid}")
                # Fall back to station-level hourly KPIs
                await self._fetch_station_hourly(batch, plant_uid, start, end)
                return batch.finalize()

            # 2. Fetch per-device historical KPIs
            for dev_id in inverter_ids:
                await self._fetch_device_kpi(batch, plant_uid, str(dev_id), start, end)

        except Exception as exc:
            batch.errors.append(f"Huawei fetch error: {exc}")

        return batch.finalize()

    async def _get_devices(self, station_code: str) -> list[dict]:
        """List devices for a station."""
        try:
            result = await self._post("getDevList", {"stationCodes": station_code})
            return result if isinstance(result, list) else result.get("data", []) if isinstance(result, dict) else []
        except Exception:
            return []

    async def _fetch_device_kpi(
        self,
        batch: ReadingBatch,
        station_code: str,
        dev_id: str,
        start: datetime,
        end: datetime,
    ) -> None:
        """Fetch historical KPIs for a single device, day by day."""
        current = start
        while current < end:
            day_end = min(current + timedelta(days=1), end)
            collect_time = int(current.timestamp()) * 1000  # Huawei uses epoch ms
            try:
                # TODO: Confirm endpoint name and parameter format
                data = await self._post(
                    "getDevHistoryKpi",
                    {
                        "devIds": dev_id,
                        "devTypeId": 1,
                        "collectTime": collect_time,
                    },
                )
                items = data if isinstance(data, list) else []
                batch.total_raw_records += len(items)

                for raw in items:
                    reading = self._map_reading(raw, station_code, dev_id)
                    if reading:
                        batch.readings.append(reading)

            except Exception as exc:
                batch.warnings.append(f"Device {dev_id} KPI error: {exc}")

            current = day_end

    async def _fetch_station_hourly(
        self,
        batch: ReadingBatch,
        station_code: str,
        start: datetime,
        end: datetime,
    ) -> None:
        """Fallback: fetch station-level hourly KPIs."""
        collect_time = int(start.timestamp()) * 1000
        try:
            data = await self._post(
                "getKpiStationHour",
                {"stationCodes": station_code, "collectTime": collect_time},
            )
            items = data if isinstance(data, list) else []
            batch.total_raw_records += len(items)
            for raw in items:
                reading = self._map_reading(raw, station_code, "station")
                if reading:
                    batch.readings.append(reading)
        except Exception as exc:
            batch.errors.append(f"Station hourly KPI error: {exc}")

    def _map_reading(self, raw: dict, station_code: str, dev_id: str) -> Reading | None:
        # Huawei uses collectTime (epoch ms) as timestamp
        ts_ms = raw.get("collectTime")
        if ts_ms is None:
            return None
        ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc) if isinstance(ts_ms, (int, float)) else ts_ms

        # Flatten dataItemMap into top-level keys for mapping
        data_items = raw.get("dataItemMap", {})
        flat = {**data_items, **{k: v for k, v in raw.items() if k != "dataItemMap"}}

        mapped = apply_field_mappings(flat, HUAWEI_FIELD_MAPPINGS)
        try:
            return Reading(
                timestamp=ts,
                plant_uid=station_code,
                device_id=dev_id,
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
            data = await self._post("getStationList", {"pageNo": 1, "pageSize": 100})
            stations = data.get("list", data) if isinstance(data, dict) else data
            return [
                {
                    "uid": s.get("stationCode") or s.get("plantCode"),
                    "name": s.get("stationName", ""),
                    "source": self.source_name,
                    "capacity_kw": s.get("capacity"),
                }
                for s in (stations if isinstance(stations, list) else [])
                if s.get("stationCode") or s.get("plantCode")
            ]
        except Exception as exc:
            self.log.error("huawei_list_error", error=str(exc))
            return []

    async def health_check(self) -> HealthStatus:
        t0 = time.monotonic()
        try:
            await self._login()
            data = await self._post("getStationList", {"pageNo": 1, "pageSize": 1})
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
        return list(HUAWEI_FIELD_MAPPINGS)
