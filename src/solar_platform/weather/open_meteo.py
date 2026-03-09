from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime
import time
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

BASE_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DEFAULT_MODEL = "ukmo_seamless"
DEFAULT_DAYS = 7

HOURLY_VARS = [
    "shortwave_radiation",       # GHI W/m²
    "direct_normal_irradiance",  # DNI W/m²
    "diffuse_radiation",         # DHI W/m²
    "direct_radiation",          # beam horizontal W/m²
    "cloud_cover",               # %
    "temperature_2m",            # °C
    "wind_speed_10m",            # km/h
    "snowfall",                  # cm
]


class WeatherFetchError(Exception):
    """Raised when an HTTP or timeout error occurs fetching weather data."""

    def __init__(
        self,
        plant_name: str,
        status_code: Optional[int],
        message: str,
    ) -> None:
        self.plant_name = plant_name
        self.status_code = status_code
        self.message = message
        super().__init__(
            f"WeatherFetchError for '{plant_name}' "
            f"(status={status_code}): {message}"
        )


@dataclass(frozen=True)
class HourlyWeatherRecord:
    plant_name: str
    timestamp: datetime
    ghi_wm2: Optional[float]        # shortwave_radiation
    dni_wm2: Optional[float]        # direct_normal_irradiance
    dhi_wm2: Optional[float]        # diffuse_radiation
    direct_radiation_wm2: Optional[float]  # direct_radiation (beam horizontal)
    gti_wm2: Optional[float]        # global_tilted_irradiance (None if not requested)
    cloud_cover_pct: Optional[float]
    temperature_c: Optional[float]
    wind_speed_kmh: Optional[float]
    snowfall_cm: Optional[float]


class OpenMeteoClient:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        forecast_days: int = DEFAULT_DAYS,
        max_concurrent: int = 5,
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self.forecast_days = forecast_days
        self.max_concurrent = max_concurrent
        self.timeout = timeout

    async def fetch_forecast(
        self,
        plant_name: str,
        lat: float,
        lon: float,
        timezone: str = "Europe/London",
        tilt_deg: Optional[float] = None,
        azimuth_deg: Optional[float] = None,
    ) -> list[HourlyWeatherRecord]:
        """Fetch hourly forecast for a single site."""
        include_gti = tilt_deg is not None and azimuth_deg is not None
        hourly_vars = list(HOURLY_VARS)
        if include_gti:
            hourly_vars.append("global_tilted_irradiance")

        params: dict = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(hourly_vars),
            "daily": "sunrise,sunset",
            "forecast_days": self.forecast_days,
            "timezone": timezone,
            "models": self.model,
        }
        if include_gti:
            params["tilt"] = tilt_deg
            params["azimuth"] = azimuth_deg

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(BASE_URL, params=params)
                response.raise_for_status()
            except httpx.TimeoutException as exc:
                raise WeatherFetchError(
                    plant_name, None, f"Request timed out: {exc}"
                ) from exc
            except httpx.HTTPStatusError as exc:
                raise WeatherFetchError(
                    plant_name,
                    exc.response.status_code,
                    f"HTTP error: {exc}",
                ) from exc

        data = response.json()
        return self._parse_records(
            plant_name=plant_name,
            data=data,
            timezone=timezone,
            include_gti=include_gti,
        )

    def _parse_records(
        self,
        plant_name: str,
        data: dict,
        timezone: str,
        include_gti: bool,
    ) -> list[HourlyWeatherRecord]:
        tz = ZoneInfo(timezone)
        hourly = data["hourly"]
        times: list[str] = hourly["time"]

        def _get(key: str, index: int) -> Optional[float]:
            col = hourly.get(key, [])
            if index >= len(col):
                return None
            return col[index]  # may already be None from API

        records: list[HourlyWeatherRecord] = []
        for i, ts_str in enumerate(times):
            timestamp = datetime.fromisoformat(ts_str).replace(tzinfo=tz)
            records.append(
                HourlyWeatherRecord(
                    plant_name=plant_name,
                    timestamp=timestamp,
                    ghi_wm2=_get("shortwave_radiation", i),
                    dni_wm2=_get("direct_normal_irradiance", i),
                    dhi_wm2=_get("diffuse_radiation", i),
                    direct_radiation_wm2=_get("direct_radiation", i),
                    gti_wm2=_get("global_tilted_irradiance", i) if include_gti else None,
                    cloud_cover_pct=_get("cloud_cover", i),
                    temperature_c=_get("temperature_2m", i),
                    wind_speed_kmh=_get("wind_speed_10m", i),
                    snowfall_cm=_get("snowfall", i),
                )
            )
        return records

    async def batch_forecast(
        self,
        sites: list[dict],
    ) -> dict[str, list[HourlyWeatherRecord]]:
        """Fetch forecasts for multiple sites concurrently, respecting max_concurrent."""
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def _fetch_with_sem(site: dict) -> tuple[str, list[HourlyWeatherRecord]]:
            async with semaphore:
                records = await self.fetch_forecast(
                    plant_name=site["name"],
                    lat=site["latitude"],
                    lon=site["longitude"],
                    timezone=site.get("timezone", "Europe/London"),
                    tilt_deg=site.get("tilt_deg"),
                    azimuth_deg=site.get("azimuth_deg"),
                )
            return site["name"], records

        results = await asyncio.gather(*[_fetch_with_sem(s) for s in sites])
        return dict(results)

    def batch_forecast_sync(
        self,
        sites: list[dict],
    ) -> dict[str, list[HourlyWeatherRecord]]:
        """Synchronous wrapper around batch_forecast."""
        return asyncio.run(self.batch_forecast(sites))


class OpenMeteoArchiveClient:
    def __init__(
        self,
        timeout: float = 30.0,
        max_attempts: int = 2,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self.timeout = timeout
        self.max_attempts = max(1, int(max_attempts))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))

    def fetch_archive(
        self,
        *,
        plant_name: str,
        target_date: date,
        lat: float,
        lon: float,
        timezone: str = "Europe/London",
        tilt_deg: Optional[float] = None,
        azimuth_deg: Optional[float] = None,
    ) -> list[HourlyWeatherRecord]:
        """Fetch hourly archive weather for a single site/day."""
        include_gti = tilt_deg is not None and azimuth_deg is not None
        hourly_vars = list(HOURLY_VARS)
        if include_gti:
            hourly_vars.append("global_tilted_irradiance")

        params: dict = {
            "latitude": lat,
            "longitude": lon,
            "start_date": target_date.isoformat(),
            "end_date": target_date.isoformat(),
            "hourly": ",".join(hourly_vars),
            "timezone": timezone,
        }
        if include_gti:
            params["tilt"] = tilt_deg
            params["azimuth"] = azimuth_deg

        last_timeout: httpx.TimeoutException | None = None
        with httpx.Client(timeout=self.timeout) as client:
            for attempt in range(1, self.max_attempts + 1):
                try:
                    response = client.get(ARCHIVE_URL, params=params)
                    response.raise_for_status()
                    break
                except httpx.TimeoutException as exc:
                    last_timeout = exc
                    if attempt >= self.max_attempts:
                        raise WeatherFetchError(
                            plant_name, None, f"Request timed out: {exc}"
                        ) from exc
                    if self.retry_backoff_seconds > 0:
                        time.sleep(self.retry_backoff_seconds)
                except httpx.HTTPStatusError as exc:
                    raise WeatherFetchError(
                        plant_name,
                        exc.response.status_code,
                        f"HTTP error: {exc}",
                    ) from exc
            else:
                if last_timeout is not None:
                    raise WeatherFetchError(
                        plant_name,
                        None,
                        f"Request timed out: {last_timeout}",
                    ) from last_timeout
                raise WeatherFetchError(plant_name, None, "Archive fetch failed")

        data = response.json()
        return OpenMeteoClient()._parse_records(
            plant_name=plant_name,
            data=data,
            timezone=timezone,
            include_gti=include_gti,
        )
