"""Unit tests for WeatherBasedForecaster.

No real HTTP calls are made — all weather records are constructed inline.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import pytest

from solar_platform.weather.forecast import (
    GHI_MIN_WM2,
    SNOW_PENALTY,
    METHOD_NAME,
    WeatherBasedForecaster,
    WeatherForecastPoint,
)
from solar_platform.weather.open_meteo import HourlyWeatherRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    hour: int,
    ghi: Optional[float] = 400.0,
    snowfall_cm: float = 0.0,
    cloud_cover_pct: float = 0.0,
    date: datetime = None,
) -> HourlyWeatherRecord:
    """Build a minimal HourlyWeatherRecord for a given hour."""
    if date is None:
        date = datetime(2026, 3, 10, tzinfo=timezone.utc)
    ts = date.replace(hour=hour)
    return HourlyWeatherRecord(
        plant_name="test-plant",
        timestamp=ts,
        ghi_wm2=ghi,
        dni_wm2=None,
        dhi_wm2=None,
        direct_radiation_wm2=None,
        gti_wm2=None,
        cloud_cover_pct=cloud_cover_pct,
        temperature_c=None,
        wind_speed_kmh=None,
        snowfall_cm=snowfall_cm,
    )


def _make_historical_df(n_days: int = 14) -> pd.DataFrame:
    """Generate synthetic hourly data: 500 W/m² GHI → 10 kWh gen during daylight (8–17h)."""
    rows = []
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for d in range(n_days):
        for h in range(24):
            ts = base.replace(day=1 + d, hour=h)
            if 8 <= h <= 17:
                rows.append({"timestamp": ts, "generation_kwh": 10.0, "ghi_wm2": 500.0})
            else:
                rows.append({"timestamp": ts, "generation_kwh": 0.0, "ghi_wm2": 0.0})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWeatherBasedForecaster:
    """Tests for WeatherBasedForecaster.forecast()."""

    def test_forecast_returns_correct_count(self):
        """24 weather records → 24 forecast points."""
        forecaster = WeatherBasedForecaster()
        records = [_make_record(h) for h in range(24)]
        hist = _make_historical_df()
        results = forecaster.forecast("plant-1", hist, records)
        assert len(results) == 24

    def test_night_hours_return_zero(self):
        """Records with ghi_wm2=0.0 (or below GHI_MIN_WM2) → generation_kwh == 0."""
        forecaster = WeatherBasedForecaster()
        # Build purely-night records
        records = [_make_record(h, ghi=0.0) for h in range(6)]
        hist = _make_historical_df()
        results = forecaster.forecast("plant-1", hist, records)
        for pt in results:
            assert pt.generation_kwh == 0.0

    def test_efficiency_scaling(self):
        """Historical: 10 kWh at 500 W/m² → efficiency 0.02 kWh/(W/m²).
        Forecast with GHI=400 → expected 8 kWh."""
        forecaster = WeatherBasedForecaster()
        hist = _make_historical_df(n_days=14)
        # Single midday record with GHI=400
        record = _make_record(hour=12, ghi=400.0)
        results = forecaster.forecast("plant-1", hist, [record])
        assert len(results) == 1
        pt = results[0]
        # efficiency = 10/500 = 0.02; forecast = 400 * 0.02 = 8.0
        assert abs(pt.generation_kwh - 8.0) < 1e-6

    def test_snow_reduces_generation(self):
        """Same efficiency setup but snowfall_cm=2 → generation reduced by snow factor."""
        forecaster = WeatherBasedForecaster()
        hist = _make_historical_df(n_days=14)
        record_no_snow = _make_record(hour=12, ghi=400.0, snowfall_cm=0.0)
        record_snow = _make_record(hour=12, ghi=400.0, snowfall_cm=2.0)
        results_no_snow = forecaster.forecast("plant-1", hist, [record_no_snow])
        results_snow = forecaster.forecast("plant-1", hist, [record_snow])
        gen_no_snow = results_no_snow[0].generation_kwh
        gen_snow = results_snow[0].generation_kwh
        expected_snow_factor = max(0.0, 1.0 - SNOW_PENALTY * 2.0)
        assert gen_snow < gen_no_snow
        assert abs(gen_snow - gen_no_snow * expected_snow_factor) < 1e-6

    def test_missing_ghi_in_history_falls_back(self):
        """historical_gen_df without 'ghi_wm2' → graceful fallback, all generation = 0."""
        forecaster = WeatherBasedForecaster()
        # History has no ghi_wm2 column
        hist_no_ghi = _make_historical_df().drop(columns=["ghi_wm2"])
        records = [_make_record(h, ghi=400.0) for h in range(8, 18)]
        # Should not raise
        results = forecaster.forecast("plant-1", hist_no_ghi, records)
        for pt in results:
            # global_mean_eff = 0 → all generation 0
            assert pt.generation_kwh == 0.0

    def test_forecast_timestamps_match_weather_records(self):
        """Timestamps in output match input weather record timestamps exactly."""
        forecaster = WeatherBasedForecaster()
        hist = _make_historical_df()
        records = [_make_record(h) for h in range(24)]
        results = forecaster.forecast("plant-1", hist, records)
        for rec, pt in zip(records, results):
            assert pt.timestamp == rec.timestamp

    def test_confidence_interval_is_non_negative(self):
        """All confidence_low values must be >= 0."""
        forecaster = WeatherBasedForecaster()
        hist = _make_historical_df()
        records = [_make_record(h) for h in range(24)]
        results = forecaster.forecast("plant-1", hist, records)
        for pt in results:
            assert pt.confidence_low >= 0.0
            assert pt.confidence_high >= pt.confidence_low

    def test_empty_weather_records_returns_empty_list(self):
        """Edge case: empty weather_records → empty result."""
        forecaster = WeatherBasedForecaster()
        hist = _make_historical_df()
        results = forecaster.forecast("plant-1", hist, [])
        assert results == []

    def test_plant_uid_propagated(self):
        """plant_uid passed to forecast() appears on every WeatherForecastPoint."""
        forecaster = WeatherBasedForecaster()
        hist = _make_historical_df()
        records = [_make_record(12, ghi=400.0)]
        results = forecaster.forecast("my-plant-uid", hist, records)
        assert results[0].plant_uid == "my-plant-uid"

    def test_method_name_is_correct(self):
        """method field on every forecast point equals METHOD_NAME constant."""
        forecaster = WeatherBasedForecaster()
        hist = _make_historical_df()
        records = [_make_record(12, ghi=400.0)]
        results = forecaster.forecast("plant-1", hist, records)
        assert results[0].method == METHOD_NAME

    def test_none_ghi_record_gives_zero(self):
        """HourlyWeatherRecord with ghi_wm2=None → generation_kwh == 0."""
        forecaster = WeatherBasedForecaster()
        hist = _make_historical_df()
        record = _make_record(12, ghi=None)
        results = forecaster.forecast("plant-1", hist, [record])
        assert results[0].generation_kwh == 0.0

    def test_snow_factor_stored_on_point(self):
        """snow_factor is correctly stored on the WeatherForecastPoint."""
        forecaster = WeatherBasedForecaster()
        hist = _make_historical_df()
        record = _make_record(12, ghi=400.0, snowfall_cm=3.0)
        results = forecaster.forecast("plant-1", hist, [record])
        expected = max(0.0, 1.0 - SNOW_PENALTY * 3.0)
        assert abs(results[0].snow_factor - expected) < 1e-9
