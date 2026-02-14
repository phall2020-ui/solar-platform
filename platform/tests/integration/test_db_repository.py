"""Integration tests for PlantRepository and ReadingsRepository against real DuckDB."""

from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pandas as pd
import pytest

from services.database.engine import DuckDBEngine
from services.database.repository import PlantRepository, ReadingsRepository, SolarDataRepository


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def db_engine(tmp_path):
    """Create a DuckDB engine with seeded plants and readings tables."""
    db_path = tmp_path / "integration_test.duckdb"
    conn = duckdb.connect(str(db_path))

    conn.execute("""
        CREATE TABLE plants (
            plant_uid VARCHAR PRIMARY KEY,
            alias VARCHAR,
            dc_size_kw DOUBLE,
            ac_size_kw DOUBLE,
            latitude DOUBLE,
            longitude DOUBLE,
            tilt DOUBLE,
            azimuth DOUBLE,
            timezone VARCHAR DEFAULT 'UTC'
        )
    """)
    conn.execute("""
        CREATE TABLE readings (
            timestamp TIMESTAMP,
            plant_uid VARCHAR,
            device_id VARCHAR,
            apparentPower_value DOUBLE,
            poaIrradiance_value DOUBLE,
            ambientTemperature_value DOUBLE,
            moduleTemperature_value DOUBLE
        )
    """)
    conn.execute("""
        CREATE TABLE solar_data (
            Site VARCHAR,
            Date VARCHAR,
            PR DOUBLE,
            Irradiance DOUBLE,
            Energy DOUBLE,
            Availability DOUBLE
        )
    """)

    # Seed plants
    conn.execute("""
        INSERT INTO plants (plant_uid, alias, dc_size_kw, ac_size_kw, latitude, longitude, tilt, azimuth)
        VALUES
            ('uid-001', 'Sunny Acres', 5000, 4500, 51.5, -0.12, 30, 180),
            ('uid-002', 'Green Fields', 8000, 7200, 52.0, -1.5, 25, 190),
            ('uid-003', 'Hilltop Solar', 3000, 2700, 50.8, -2.1, 35, 175)
    """)

    # Seed readings
    conn.execute("""
        INSERT INTO readings VALUES
            ('2026-01-01 00:00:00', 'uid-001', 'dev-1', 100.0, 10.0, 5.0, 12.0),
            ('2026-01-01 00:15:00', 'uid-001', 'dev-1', 110.0, 20.0, 6.0, 13.0),
            ('2026-01-01 00:30:00', 'uid-001', 'dev-2', 120.0, 30.0, 7.0, 14.0),
            ('2026-01-01 00:45:00', 'uid-002', 'dev-3', 130.0, 40.0, 8.0, 15.0),
            ('2026-01-01 01:00:00', 'uid-001', 'dev-1', 140.0, 50.0, 9.0, 16.0),
            ('2026-01-01 01:15:00', 'uid-001', 'dev-1', 150.0, 60.0, 10.0, 17.0)
    """)

    # Seed solar_data
    conn.execute("""
        INSERT INTO solar_data VALUES
            ('Plant A', 'Jan-24', 0.82, 980.0, 1010.0, 99.5),
            ('Plant B', 'Jan-24', 0.85, 1020.0, 2050.0, 99.0),
            ('Plant A', 'Feb-24', 0.84, 1000.0, 1100.0, 99.2)
    """)

    conn.close()
    return DuckDBEngine(str(db_path))


# ── PlantRepository Tests ────────────────────────────────────────────────


@pytest.mark.integration
class TestPlantRepository:
    """Integration tests for PlantRepository against real DuckDB."""

    def test_list_all_returns_all_plants(self, db_engine):
        repo = PlantRepository(engine=db_engine)
        df = repo.list_all()
        assert len(df) == 3
        assert "plant_uid" in df.columns

    def test_get_all_is_ordered_by_alias(self, db_engine):
        repo = PlantRepository(engine=db_engine)
        df = repo.get_all()
        aliases = df["alias"].tolist()
        assert aliases == sorted(aliases)

    def test_get_by_uid_returns_dict(self, db_engine):
        repo = PlantRepository(engine=db_engine)
        plant = repo.get_by_uid("uid-001")
        assert plant is not None
        assert plant["alias"] == "Sunny Acres"
        assert plant["dc_size_kw"] == 5000

    def test_get_by_uid_returns_none_for_missing(self, db_engine):
        repo = PlantRepository(engine=db_engine)
        result = repo.get_by_uid("uid-nonexistent")
        assert result is None

    def test_get_by_alias(self, db_engine):
        repo = PlantRepository(engine=db_engine)
        plant = repo.get_by_alias("Green Fields")
        assert plant is not None
        assert plant["plant_uid"] == "uid-002"

    def test_list_aliases(self, db_engine):
        repo = PlantRepository(engine=db_engine)
        aliases = repo.list_aliases()
        assert len(aliases) == 3
        assert "Sunny Acres" in aliases

    def test_list_uids(self, db_engine):
        repo = PlantRepository(engine=db_engine)
        uids = repo.list_uids()
        assert len(uids) == 3
        assert "uid-001" in uids

    def test_upsert_inserts_new_plant(self, db_engine):
        repo = PlantRepository(engine=db_engine)
        repo.upsert({
            "plant_uid": "uid-004",
            "alias": "New Plant",
            "dc_size_kw": 10000,
            "ac_size_kw": 9000,
            "latitude": 48.0,
            "longitude": 2.0,
            "tilt": 20,
            "azimuth": 200,
        })
        plant = repo.get_by_uid("uid-004")
        assert plant is not None
        assert plant["alias"] == "New Plant"

    def test_upsert_updates_existing_plant(self, db_engine):
        repo = PlantRepository(engine=db_engine)
        repo.upsert({
            "plant_uid": "uid-001",
            "alias": "Sunny Acres Updated",
            "dc_size_kw": 6000,
            "ac_size_kw": 5400,
            "latitude": 51.5,
            "longitude": -0.12,
            "tilt": 30,
            "azimuth": 180,
        })
        plant = repo.get_by_uid("uid-001")
        assert plant["alias"] == "Sunny Acres Updated"
        assert plant["dc_size_kw"] == 6000


# ── ReadingsRepository Tests ────────────────────────────────────────────


@pytest.mark.integration
class TestReadingsRepository:
    """Integration tests for ReadingsRepository against real DuckDB."""

    def test_get_readings_by_plant(self, db_engine):
        repo = ReadingsRepository(engine=db_engine)
        df = repo.get_readings("uid-001")
        assert len(df) == 5  # 5 readings for uid-001
        assert "timestamp" in df.columns

    def test_get_readings_with_time_filter(self, db_engine):
        repo = ReadingsRepository(engine=db_engine)
        start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc)
        df = repo.get_readings("uid-001", start=start, end=end)
        assert len(df) == 3  # rows at 00:00, 00:15, 00:30

    def test_get_readings_with_device_filter(self, db_engine):
        repo = ReadingsRepository(engine=db_engine)
        df = repo.get_readings("uid-001", device_id="dev-2")
        assert len(df) == 1

    def test_get_readings_with_limit(self, db_engine):
        repo = ReadingsRepository(engine=db_engine)
        df = repo.get_readings("uid-001", limit=2)
        assert len(df) == 2

    def test_get_readings_empty_for_missing_plant(self, db_engine):
        repo = ReadingsRepository(engine=db_engine)
        df = repo.get_readings("uid-nonexistent")
        assert df.empty

    def test_get_readings_df_with_column_selection(self, db_engine):
        repo = ReadingsRepository(engine=db_engine)
        df = repo.get_readings_df(
            "uid-001",
            columns=["timestamp", "apparentPower_value"],
        )
        assert "timestamp" in df.columns
        assert "apparentPower_value" in df.columns

    def test_get_readings_df_unknown_columns_returns_empty(self, db_engine):
        repo = ReadingsRepository(engine=db_engine)
        df = repo.get_readings_df(
            "uid-001",
            columns=["nonexistent_col"],
        )
        assert df.empty

    def test_insert_readings_via_bulk(self, db_engine):
        """Test inserting readings via the engine's bulk_insert_df."""
        new_readings = pd.DataFrame({
            "timestamp": pd.to_datetime(["2026-02-01 00:00:00", "2026-02-01 00:15:00"]),
            "plant_uid": ["uid-003", "uid-003"],
            "device_id": ["dev-10", "dev-10"],
            "apparentPower_value": [200.0, 210.0],
            "poaIrradiance_value": [100.0, 110.0],
            "ambientTemperature_value": [15.0, 16.0],
            "moduleTemperature_value": [25.0, 26.0],
        })
        count = db_engine.bulk_insert_df("readings", new_readings)
        assert count == 2

        repo = ReadingsRepository(engine=db_engine)
        df = repo.get_readings("uid-003")
        assert len(df) == 2


# ── SolarDataRepository Tests ───────────────────────────────────────────


@pytest.mark.integration
class TestSolarDataRepository:
    """Integration tests for SolarDataRepository."""

    def test_get_monthly_all(self, db_engine):
        repo = SolarDataRepository(engine=db_engine)
        df = repo.get_monthly()
        assert len(df) == 3

    def test_get_monthly_by_site(self, db_engine):
        repo = SolarDataRepository(engine=db_engine)
        df = repo.get_monthly(site="Plant A")
        assert len(df) == 2

    def test_get_monthly_by_month(self, db_engine):
        repo = SolarDataRepository(engine=db_engine)
        df = repo.get_monthly(month="Jan-24")
        assert len(df) == 2

    def test_list_sites(self, db_engine):
        repo = SolarDataRepository(engine=db_engine)
        sites = repo.list_sites()
        assert set(sites) == {"Plant A", "Plant B"}

    def test_list_months(self, db_engine):
        repo = SolarDataRepository(engine=db_engine)
        months = repo.list_months()
        assert "Jan-24" in months
        assert "Feb-24" in months
