"""NASA POWER API client for historical daily solar irradiance and weather data."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import httpx

BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS = "ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,CLOUD_AMT,SNODP,T2M,WS10M"
FILL_VALUE = -999.0


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class HistoricalFetchError(Exception):
    """Raised when NASA POWER historical data cannot be fetched."""

    def __init__(self, plant_name: str, message: str) -> None:
        self.plant_name = plant_name
        self.message = message
        super().__init__(f"[{plant_name}] {message}")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DailyHistoricalRecord:
    """One day of NASA POWER historical data for a single plant."""

    plant_name: str
    date: date
    ghi_kwh_m2: Optional[float]           # ALLSKY_SFC_SW_DWN
    clearsky_ghi_kwh_m2: Optional[float]  # CLRSKY_SFC_SW_DWN
    cloud_amount_pct: Optional[float]     # CLOUD_AMT
    snow_depth_cm: Optional[float]        # SNODP
    temperature_c: Optional[float]        # T2M
    wind_speed_ms: Optional[float]        # WS10M


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean(value: float | None) -> Optional[float]:
    """Return None for NASA fill values (-999), otherwise return the value."""
    if value is None:
        return None
    return None if value == FILL_VALUE else value


def _parse_records(
    plant_name: str,
    params: dict,
) -> list[DailyHistoricalRecord]:
    """Convert the ``properties.parameter`` block from the API response into records."""
    allsky = params.get("ALLSKY_SFC_SW_DWN", {})
    clrsky = params.get("CLRSKY_SFC_SW_DWN", {})
    cloud = params.get("CLOUD_AMT", {})
    snow = params.get("SNODP", {})
    temp = params.get("T2M", {})
    wind = params.get("WS10M", {})

    records: list[DailyHistoricalRecord] = []
    for date_str in allsky:
        from datetime import datetime

        day = datetime.strptime(date_str, "%Y%m%d").date()
        records.append(
            DailyHistoricalRecord(
                plant_name=plant_name,
                date=day,
                ghi_kwh_m2=_clean(allsky.get(date_str)),
                clearsky_ghi_kwh_m2=_clean(clrsky.get(date_str)),
                cloud_amount_pct=_clean(cloud.get(date_str)),
                snow_depth_cm=_clean(snow.get(date_str)),
                temperature_c=_clean(temp.get(date_str)),
                wind_speed_ms=_clean(wind.get(date_str)),
            )
        )

    records.sort(key=lambda r: r.date)
    return records


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class NasaPowerClient:
    """Async client for the NASA POWER daily point API."""

    def __init__(
        self,
        max_concurrent: int = 3,
        timeout: float = 60.0,  # NASA API can be slow
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Core fetch
    # ------------------------------------------------------------------

    async def fetch_historical(
        self,
        plant_name: str,
        lat: float,
        lon: float,
        start_date: date,
        end_date: date,
    ) -> list[DailyHistoricalRecord]:
        """Fetch daily historical records for a single site."""
        params = {
            "parameters": PARAMETERS,
            "community": "RE",
            "longitude": lon,
            "latitude": lat,
            "start": start_date.strftime("%Y%m%d"),
            "end": end_date.strftime("%Y%m%d"),
            "format": "JSON",
        }

        async with self._semaphore:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(BASE_URL, params=params)
                    response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise HistoricalFetchError(
                    plant_name,
                    f"HTTP {exc.response.status_code} from NASA POWER API",
                ) from exc
            except httpx.TimeoutException as exc:
                raise HistoricalFetchError(
                    plant_name,
                    "Request timed out",
                ) from exc
            except httpx.RequestError as exc:
                raise HistoricalFetchError(
                    plant_name,
                    f"Request error: {exc}",
                ) from exc

        data = response.json()
        parameter_block = data["properties"]["parameter"]
        return _parse_records(plant_name, parameter_block)

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    async def fetch_last_n_years(
        self,
        plant_name: str,
        lat: float,
        lon: float,
        years: int = 5,
    ) -> list[DailyHistoricalRecord]:
        """Fetch the last *years* years of daily historical data."""
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=years * 365)
        return await self.fetch_historical(plant_name, lat, lon, start_date, end_date)

    async def batch_historical(
        self,
        sites: list[dict],
        start_date: date,
        end_date: date,
    ) -> dict[str, list[DailyHistoricalRecord]]:
        """Fetch historical data for multiple sites concurrently.

        Args:
            sites: List of dicts, each with keys ``name``, ``latitude``, ``longitude``.
            start_date: Inclusive start date.
            end_date: Inclusive end date.

        Returns:
            Mapping of site name → list of :class:`DailyHistoricalRecord`.
        """
        tasks = [
            self.fetch_historical(
                site["name"],
                site["latitude"],
                site["longitude"],
                start_date,
                end_date,
            )
            for site in sites
        ]
        results = await asyncio.gather(*tasks)
        return {site["name"]: records for site, records in zip(sites, results)}

    def batch_historical_sync(
        self,
        sites: list[dict],
        start_date: date,
        end_date: date,
    ) -> dict[str, list[DailyHistoricalRecord]]:
        """Synchronous wrapper around :meth:`batch_historical`."""
        return asyncio.run(self.batch_historical(sites, start_date, end_date))
