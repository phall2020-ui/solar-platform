"""Unit tests for NasaPowerClient and DailyHistoricalRecord."""
from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from solar_platform.weather.nasa_power import (
    DailyHistoricalRecord,
    HistoricalFetchError,
    NasaPowerClient,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PLANT = "TestPlant"
LAT = 53.88
LON = -2.54
START = date(2024, 1, 1)
END = date(2024, 1, 3)


def _make_api_response(
    allsky: dict | None = None,
    clrsky: dict | None = None,
    cloud: dict | None = None,
    snow: dict | None = None,
    temp: dict | None = None,
    wind: dict | None = None,
) -> dict:
    """Build a minimal NASA POWER API response."""
    default_allsky = {"20240101": 1.23, "20240102": 2.45, "20240103": 3.67}
    default_clrsky = {"20240101": 5.67, "20240102": 6.78, "20240103": 7.89}
    default_cloud = {"20240101": 78.0, "20240102": 60.0, "20240103": 45.0}
    default_snow = {"20240101": 0.0, "20240102": 0.0, "20240103": 0.0}
    default_temp = {"20240101": 8.5, "20240102": 9.0, "20240103": 7.2}
    default_wind = {"20240101": 3.2, "20240102": 4.1, "20240103": 2.8}

    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [LON, LAT, 0]},
        "properties": {
            "parameter": {
                "ALLSKY_SFC_SW_DWN": allsky if allsky is not None else default_allsky,
                "CLRSKY_SFC_SW_DWN": clrsky if clrsky is not None else default_clrsky,
                "CLOUD_AMT": cloud if cloud is not None else default_cloud,
                "SNODP": snow if snow is not None else default_snow,
                "T2M": temp if temp is not None else default_temp,
                "WS10M": wind if wind is not None else default_wind,
            }
        },
    }


def _mock_httpx_response(payload: dict, status_code: int = 200) -> MagicMock:
    """Return a MagicMock that mimics an httpx.Response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status = MagicMock()  # no-op by default
    return response


def _patch_client(mock_response: MagicMock):
    """Context-manager patch for httpx.AsyncClient.get."""
    async_get = AsyncMock(return_value=mock_response)
    return patch("httpx.AsyncClient.get", async_get)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_daily_records():
    """Three-day response → three DailyHistoricalRecord objects with correct values."""
    payload = _make_api_response()
    mock_resp = _mock_httpx_response(payload)

    with _patch_client(mock_resp):
        client = NasaPowerClient()
        records = await client.fetch_historical(PLANT, LAT, LON, START, END)

    assert len(records) == 3

    first = records[0]
    assert isinstance(first, DailyHistoricalRecord)
    assert first.plant_name == PLANT
    assert first.date == date(2024, 1, 1)
    assert first.ghi_kwh_m2 == pytest.approx(1.23)
    assert first.clearsky_ghi_kwh_m2 == pytest.approx(5.67)
    assert first.cloud_amount_pct == pytest.approx(78.0)
    assert first.temperature_c == pytest.approx(8.5)
    assert first.wind_speed_ms == pytest.approx(3.2)

    # Records are sorted by date
    assert records[0].date < records[1].date < records[2].date


@pytest.mark.asyncio
async def test_fill_value_becomes_none():
    """A -999 fill value in ALLSKY_SFC_SW_DWN should produce ghi_kwh_m2=None."""
    allsky_with_fill = {"20240101": -999.0, "20240102": 2.45, "20240103": 3.67}
    payload = _make_api_response(allsky=allsky_with_fill)
    mock_resp = _mock_httpx_response(payload)

    with _patch_client(mock_resp):
        client = NasaPowerClient()
        records = await client.fetch_historical(PLANT, LAT, LON, START, END)

    assert records[0].date == date(2024, 1, 1)
    assert records[0].ghi_kwh_m2 is None

    # Other records are unaffected
    assert records[1].ghi_kwh_m2 == pytest.approx(2.45)
    assert records[2].ghi_kwh_m2 == pytest.approx(3.67)


@pytest.mark.asyncio
async def test_date_range_in_request():
    """start= and end= query params must be formatted as YYYYMMDD (no hyphens)."""
    payload = _make_api_response()
    mock_resp = _mock_httpx_response(payload)
    async_get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient.get", async_get):
        client = NasaPowerClient()
        await client.fetch_historical(PLANT, LAT, LON, START, END)

    _, kwargs = async_get.call_args
    sent_params: dict = kwargs.get("params", {})

    assert sent_params["start"] == "20240101"
    assert sent_params["end"] == "20240103"


@pytest.mark.asyncio
async def test_http_error_raises_historical_fetch_error():
    """An HTTP 4xx/5xx response should raise HistoricalFetchError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server Error",
        request=MagicMock(),
        response=mock_resp,
    )

    with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
        client = NasaPowerClient()
        with pytest.raises(HistoricalFetchError) as exc_info:
            await client.fetch_historical(PLANT, LAT, LON, START, END)

    assert exc_info.value.plant_name == PLANT
    assert "HTTP 500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_batch_returns_per_site_dict():
    """batch_historical with two sites returns a dict with two keys and correct record counts."""
    sites = [
        {"name": "SiteA", "latitude": 53.88, "longitude": -2.54},
        {"name": "SiteB", "latitude": 51.50, "longitude": -0.12},
    ]

    payload_a = _make_api_response()
    payload_b = _make_api_response(
        allsky={"20240101": 4.0, "20240102": 5.0, "20240103": 6.0},
    )

    call_count = 0

    async def mock_get(url, *, params, **kwargs):
        nonlocal call_count
        name = params["latitude"]
        resp = MagicMock(spec=httpx.Response)
        resp.raise_for_status = MagicMock()
        # Return payload_a for SiteA latitude, payload_b for SiteB latitude
        resp.json.return_value = payload_a if params["latitude"] == 53.88 else payload_b
        call_count += 1
        return resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        client = NasaPowerClient()
        result = await client.batch_historical(sites, START, END)

    assert set(result.keys()) == {"SiteA", "SiteB"}
    assert len(result["SiteA"]) == 3
    assert len(result["SiteB"]) == 3
    assert call_count == 2

    # Verify plant_name is set correctly on records
    assert all(r.plant_name == "SiteA" for r in result["SiteA"])
    assert all(r.plant_name == "SiteB" for r in result["SiteB"])
