"""Unit tests for WeatherRepository (DuckDB storage)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import duckdb
import pytest

from solar_platform.weather.nasa_power import DailyHistoricalRecord
from solar_platform.weather.open_meteo import HourlyWeatherRecord
from solar_platform.weather.storage import WeatherRepository


# ---------------------------------------------------------------------------
# Helpers: build mock records inline (no separate fixtures file)
# ---------------------------------------------------------------------------

_LONDON = ZoneInfo("Europe/London")

FETCHED_AT = datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc)


def _make_hourly(plant: str, hour: int, offset_days: int = 1) -> HourlyWeatherRecord:
    """Return a minimal HourlyWeatherRecord with a London-timezone timestamp."""
    ts = datetime(2026, 3, 4 + offset_days, hour, 0, 0, tzinfo=_LONDON)
    return HourlyWeatherRecord(
        plant_name=plant,
        timestamp=ts,
        ghi_wm2=200.0 + hour,
        dni_wm2=150.0,
        dhi_wm2=50.0,
        direct_radiation_wm2=140.0,
        gti_wm2=None,
        cloud_cover_pct=20.0,
        temperature_c=10.5,
        wind_speed_kmh=5.0,
        snowfall_cm=0.0,
    )


def _make_historical(plant: str, day_offset: int = 0) -> DailyHistoricalRecord:
    """Return a minimal DailyHistoricalRecord."""
    return DailyHistoricalRecord(
        plant_name=plant,
        date=date(2026, 2, 1 + day_offset),
        ghi_kwh_m2=4.5,
        clearsky_ghi_kwh_m2=5.0,
        cloud_amount_pct=30.0,
        snow_depth_cm=0.0,
        temperature_c=8.0,
        wind_speed_ms=3.0,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path):
    """Fresh WeatherRepository backed by a temp DuckDB file."""
    return WeatherRepository(db_path=tmp_path / "test.duckdb")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    def test_schema_created_on_init(self, tmp_path):
        """Both weather tables exist after WeatherRepository is constructed."""
        db_file = str(tmp_path / "test.duckdb")
        WeatherRepository(db_path=db_file)

        conn = duckdb.connect(db_file)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
        conn.close()

        assert "weather_forecasts" in tables
        assert "weather_historical" in tables


class TestUpsertForecasts:
    def test_upsert_forecasts_returns_count(self, repo):
        """upsert_forecasts returns the number of records passed in."""
        records = [_make_hourly("PlantA", h) for h in range(3)]
        count = repo.upsert_forecasts(records, fetched_at=FETCHED_AT)
        assert count == 3

    def test_upsert_forecasts_persists_data(self, repo):
        """Rows land in the DB after upsert."""
        records = [_make_hourly("PlantA", h) for h in range(3)]
        repo.upsert_forecasts(records, fetched_at=FETCHED_AT)

        conn = duckdb.connect(repo.db_path)
        rows = conn.execute(
            "SELECT COUNT(*) FROM weather_forecasts WHERE plant_name = 'PlantA'"
        ).fetchone()
        conn.close()
        assert rows[0] == 3

    def test_upsert_forecasts_converts_to_utc(self, repo):
        """Timestamps stored as UTC regardless of input timezone."""
        record = _make_hourly("PlantB", 12)
        repo.upsert_forecasts([record], fetched_at=FETCHED_AT)

        conn = duckdb.connect(repo.db_path)
        rows = conn.execute(
            "SELECT timestamp FROM weather_forecasts WHERE plant_name = 'PlantB'"
        ).fetchall()
        conn.close()

        assert len(rows) == 1
        # The stored timestamp should equal the UTC conversion of the London ts
        expected_utc = record.timestamp.astimezone(timezone.utc)
        stored = rows[0][0]
        # DuckDB may return timezone-aware or timezone-naive; compare in UTC
        if hasattr(stored, "tzinfo") and stored.tzinfo is None:
            from datetime import timezone as _tz
            stored = stored.replace(tzinfo=_tz.utc)
        assert stored == expected_utc


class TestUpsertHistorical:
    def test_upsert_historical_returns_count(self, repo):
        """upsert_historical returns the number of records passed in."""
        records = [_make_historical("PlantA", i) for i in range(2)]
        count = repo.upsert_historical(records)
        assert count == 2

    def test_upsert_historical_is_idempotent(self, repo):
        """Inserting the same records twice keeps only one copy (ON CONFLICT DO NOTHING)."""
        records = [_make_historical("PlantA", i) for i in range(2)]
        repo.upsert_historical(records)
        repo.upsert_historical(records)  # second call should be silently ignored

        conn = duckdb.connect(repo.db_path)
        row = conn.execute(
            "SELECT COUNT(*) FROM weather_historical WHERE plant_name = 'PlantA'"
        ).fetchone()
        conn.close()
        assert row[0] == 2


class TestGetForecasts:
    def test_get_forecasts_returns_dataframe(self, repo):
        """get_forecasts returns a non-empty DataFrame after insert."""
        import pandas as pd

        records = [_make_hourly("PlantX", h) for h in range(4)]
        repo.upsert_forecasts(records, fetched_at=FETCHED_AT)

        from_ts = datetime(2026, 3, 4, tzinfo=timezone.utc)
        to_ts = datetime(2026, 3, 10, tzinfo=timezone.utc)
        df = repo.get_forecasts("PlantX", from_ts, to_ts, latest_only=True)

        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_get_forecasts_latest_only(self, repo):
        """latest_only=True returns only rows from the most recent fetch batch."""
        records = [_make_hourly("PlantY", h) for h in range(2)]

        fetched_old = datetime(2026, 3, 3, 6, 0, tzinfo=timezone.utc)
        fetched_new = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)

        repo.upsert_forecasts(records, fetched_at=fetched_old)
        repo.upsert_forecasts(records, fetched_at=fetched_new)

        from_ts = datetime(2026, 3, 4, tzinfo=timezone.utc)
        to_ts = datetime(2026, 3, 10, tzinfo=timezone.utc)
        df = repo.get_forecasts("PlantY", from_ts, to_ts, latest_only=True)

        # Should only see rows from the newer batch
        assert len(df) == len(records)


class TestGetAvailablePlants:
    def test_get_available_plants(self, repo):
        """get_available_plants returns all distinct plant names."""
        repo.upsert_forecasts([_make_hourly("Alpha", 0)], fetched_at=FETCHED_AT)
        repo.upsert_forecasts([_make_hourly("Beta", 0)], fetched_at=FETCHED_AT)

        plants = repo.get_available_plants("weather_forecasts")

        assert sorted(plants) == ["Alpha", "Beta"]

    def test_get_available_plants_historical(self, repo):
        """get_available_plants works for weather_historical too."""
        repo.upsert_historical([_make_historical("SiteA", 0)])
        repo.upsert_historical([_make_historical("SiteB", 1)])

        plants = repo.get_available_plants("weather_historical")

        assert sorted(plants) == ["SiteA", "SiteB"]

    def test_get_available_plants_rejects_unknown_table(self, repo):
        """Passing an unknown table name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown table"):
            repo.get_available_plants("injected_table; DROP TABLE plants")
