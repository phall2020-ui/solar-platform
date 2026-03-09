"""Unit tests for OpenMeteoClient and HourlyWeatherRecord."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from solar_platform.weather.open_meteo import (
    HourlyWeatherRecord,
    OpenMeteoArchiveClient,
    OpenMeteoClient,
    WeatherFetchError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NUM_HOURS = 24


def _make_hourly_times(n: int = NUM_HOURS) -> list[str]:
    """Return n ISO-format hourly timestamps starting 2025-06-01T00:00."""
    return [f"2025-06-01T{h:02d}:00" for h in range(n)]


def _make_api_response(
    *,
    n: int = NUM_HOURS,
    shortwave_radiation: list | None = None,
    include_gti: bool = False,
) -> dict:
    if shortwave_radiation is None:
        shortwave_radiation = [float(i * 10) for i in range(n)]

    data: dict = {
        "latitude": 53.875,
        "longitude": -2.5,
        "timezone": "Europe/London",
        "hourly_units": {"time": "iso8601", "shortwave_radiation": "W/m²"},
        "hourly": {
            "time": _make_hourly_times(n),
            "shortwave_radiation": shortwave_radiation,
            "direct_normal_irradiance": [float(i) for i in range(n)],
            "diffuse_radiation": [float(i) for i in range(n)],
            "direct_radiation": [float(i) for i in range(n)],
            "cloud_cover": [50.0] * n,
            "temperature_2m": [10.0] * n,
            "wind_speed_10m": [5.0] * n,
            "snowfall": [0.0] * n,
        },
        "daily": {
            "time": ["2025-06-01"],
            "sunrise": ["2025-06-01T04:30"],
            "sunset": ["2025-06-01T21:10"],
        },
    }
    if include_gti:
        data["hourly"]["global_tilted_irradiance"] = [float(i * 12) for i in range(n)]
    return data


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a mock httpx response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = data
    mock.raise_for_status = MagicMock()  # no-op by default
    return mock


def _mock_async_get(response: MagicMock) -> AsyncMock:
    """Wrap a response mock as an async .get() method."""
    mock_get = AsyncMock(return_value=response)
    return mock_get


def _mock_sync_get(response: MagicMock):
    """Wrap a response mock as a sync .get() method."""
    def _get(*args, **kwargs):  # noqa: ANN002, ANN003
        return response

    return _get


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_hourly_records():
    """24 time slots → 24 HourlyWeatherRecord objects with correct fields."""
    client = OpenMeteoClient()
    api_data = _make_api_response()
    mock_resp = _mock_response(api_data)

    with patch("httpx.AsyncClient.get", new=_mock_async_get(mock_resp)):
        records = await client.fetch_forecast(
            plant_name="SiteA", lat=53.88, lon=-2.54
        )

    assert len(records) == NUM_HOURS
    assert all(isinstance(r, HourlyWeatherRecord) for r in records)
    assert records[0].plant_name == "SiteA"
    assert records[0].ghi_wm2 == 0.0  # index 0: 0 * 10


@pytest.mark.asyncio
async def test_timestamps_are_tz_aware():
    """All returned timestamps must have tzinfo set."""
    client = OpenMeteoClient()
    api_data = _make_api_response()
    mock_resp = _mock_response(api_data)

    with patch("httpx.AsyncClient.get", new=_mock_async_get(mock_resp)):
        records = await client.fetch_forecast(
            plant_name="SiteB", lat=53.88, lon=-2.54, timezone="Europe/London"
        )

    assert all(r.timestamp.tzinfo is not None for r in records)


@pytest.mark.asyncio
async def test_none_values_become_none():
    """API null values in shortwave_radiation → ghi_wm2 = None on affected records."""
    # Put None at positions 3 and 7
    sw = [float(i * 10) for i in range(NUM_HOURS)]
    sw[3] = None  # type: ignore[call-overload]
    sw[7] = None  # type: ignore[call-overload]

    client = OpenMeteoClient()
    api_data = _make_api_response(shortwave_radiation=sw)
    mock_resp = _mock_response(api_data)

    with patch("httpx.AsyncClient.get", new=_mock_async_get(mock_resp)):
        records = await client.fetch_forecast(plant_name="SiteC", lat=53.88, lon=-2.54)

    assert records[3].ghi_wm2 is None
    assert records[7].ghi_wm2 is None
    # Others should be non-None
    assert records[0].ghi_wm2 == 0.0
    assert records[1].ghi_wm2 == 10.0


@pytest.mark.asyncio
async def test_tilt_adds_gti_to_request():
    """When tilt_deg and azimuth_deg are provided, global_tilted_irradiance is
    included in the URL params and gti_wm2 is populated."""
    client = OpenMeteoClient()
    api_data = _make_api_response(include_gti=True)
    mock_resp = _mock_response(api_data)
    captured_params: dict = {}

    async def capturing_get(_self, url: str, **kwargs):
        captured_params.update(kwargs.get("params", {}))
        return mock_resp

    with patch("httpx.AsyncClient.get", new=capturing_get):
        records = await client.fetch_forecast(
            plant_name="SiteD",
            lat=53.88,
            lon=-2.54,
            tilt_deg=30.0,
            azimuth_deg=180.0,
        )

    # GTI param keys present
    hourly_param = captured_params.get("hourly", "")
    assert "global_tilted_irradiance" in hourly_param
    assert captured_params.get("tilt") == 30.0
    assert captured_params.get("azimuth") == 180.0

    # gti_wm2 populated
    assert records[0].gti_wm2 == 0.0  # 0 * 12
    assert records[1].gti_wm2 == 12.0  # 1 * 12


@pytest.mark.asyncio
async def test_http_error_raises_weather_fetch_error():
    """Non-2xx response → WeatherFetchError raised with plant_name set."""
    client = OpenMeteoClient()

    # Build a mock response that raise_for_status() raises HTTPStatusError
    error_response = MagicMock()
    error_response.status_code = 500
    http_status_error = httpx.HTTPStatusError(
        "500 Server Error",
        request=MagicMock(),
        response=error_response,
    )
    raising_resp = MagicMock()
    raising_resp.raise_for_status.side_effect = http_status_error

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=raising_resp)):
        with pytest.raises(WeatherFetchError) as exc_info:
            await client.fetch_forecast(plant_name="SiteE", lat=53.88, lon=-2.54)

    assert exc_info.value.plant_name == "SiteE"
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_batch_forecast_returns_per_site_dict():
    """Two-site batch returns a dict keyed by plant_name with correct record counts."""
    client = OpenMeteoClient()

    api_data_a = _make_api_response()
    api_data_b = _make_api_response()
    resp_a = _mock_response(api_data_a)
    resp_b = _mock_response(api_data_b)

    call_count = 0

    async def multi_response_get(_self, url: str, **kwargs):
        nonlocal call_count
        call_count += 1
        return resp_a if call_count == 1 else resp_b

    sites = [
        {
            "name": "PlantAlpha",
            "latitude": 53.88,
            "longitude": -2.54,
            "timezone": "Europe/London",
        },
        {
            "name": "PlantBeta",
            "latitude": 51.5,
            "longitude": -0.12,
            "timezone": "Europe/London",
        },
    ]

    with patch("httpx.AsyncClient.get", new=multi_response_get):
        result = await client.batch_forecast(sites)

    assert set(result.keys()) == {"PlantAlpha", "PlantBeta"}
    assert len(result["PlantAlpha"]) == NUM_HOURS
    assert len(result["PlantBeta"]) == NUM_HOURS


def test_archive_fetch_includes_gti_and_returns_tz_aware_records():
    """Archive fetch should request GTI and parse timezone-aware hourly records."""
    client = OpenMeteoArchiveClient()
    api_data = _make_api_response(include_gti=True)
    mock_resp = _mock_response(api_data)
    captured_params: dict = {}

    def capturing_get(_self, url: str, **kwargs):
        captured_params.update(kwargs.get("params", {}))
        return mock_resp

    with patch("httpx.Client.get", new=capturing_get):
        records = client.fetch_archive(
            plant_name="SiteArchive",
            target_date=date(2026, 3, 7),
            lat=53.88,
            lon=-2.54,
            timezone="Europe/London",
            tilt_deg=30.0,
            azimuth_deg=180.0,
        )

    assert len(records) == NUM_HOURS
    assert all(isinstance(r, HourlyWeatherRecord) for r in records)
    assert all(r.timestamp.tzinfo is not None for r in records)
    assert captured_params["start_date"] == "2026-03-07"
    assert captured_params["end_date"] == "2026-03-07"
    assert "global_tilted_irradiance" in captured_params["hourly"]
    assert records[1].gti_wm2 == 12.0


def test_archive_fetch_retries_after_timeout_and_succeeds():
    """Archive fetch should retry transient timeout errors before failing."""
    client = OpenMeteoArchiveClient(timeout=1.0)
    api_data = _make_api_response(include_gti=True)
    mock_resp = _mock_response(api_data)
    calls = {"count": 0}

    def flaky_get(_self, url: str, **kwargs):  # noqa: ANN001
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.TimeoutException("handshake timed out")
        return mock_resp

    with patch("httpx.Client.get", new=flaky_get):
        records = client.fetch_archive(
            plant_name="Retry Site",
            target_date=date(2026, 3, 7),
            lat=53.88,
            lon=-2.54,
            timezone="Europe/London",
            tilt_deg=30.0,
            azimuth_deg=180.0,
        )

    assert calls["count"] == 2
    assert len(records) == NUM_HOURS
