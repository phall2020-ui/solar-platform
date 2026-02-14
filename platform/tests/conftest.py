"""
Pytest configuration and shared fixtures for the Solar Portfolio Manager test suite.

Add project-wide fixtures here. For module-specific fixtures,
create a conftest.py inside the relevant test sub-package.
"""
import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock
import duckdb

from services.database.engine import DuckDBEngine


@pytest.fixture
def sample_dataframe():
    """Sample DataFrame for testing."""
    return pd.DataFrame({
        'Site': ['Plant A', 'Plant B', 'Plant C'],
        'Energy_kWh': [1000, 2000, 3000],
        'PR': [0.8, 0.85, 0.9],
        'Date': ['Jan-24', 'Jan-24', 'Jan-24']
    })


@pytest.fixture
def mock_db_path(tmp_path):
    """Temporary database path for testing."""
    return tmp_path / "test.duckdb"


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    config = MagicMock()
    config.TOOLKIT_DB = Path("/tmp/test_toolkit.duckdb")
    config.REPORTING_DB = Path("/tmp/test_reporting.duckdb")
    config.BRAND_COLORS = {
        'primary': '#5FBFA0',
        'secondary': '#4A9E80',
        'accent': '#8FE0C5',
        'positive': '#5FBFA0',
        'negative': '#E66B6B',
        'warning': '#F2C265',
        'surface': '#1E2538',
        'background': '#0B1120',
        'border': '#2B354E',
        'text': '#FFFFFF',
        'text_secondary': '#E0E0E0',
    }
    return config


@pytest.fixture
def empty_dataframe():
    """Empty DataFrame for edge case testing."""
    return pd.DataFrame()


@pytest.fixture
def tmp_db_path(tmp_path):
    """Temporary DuckDB path for DB abstraction tests."""
    return tmp_path / "test.duckdb"


@pytest.fixture
def test_engine(tmp_db_path):
    """DuckDBEngine with an empty database file."""
    duckdb.connect(str(tmp_db_path)).close()
    return DuckDBEngine(str(tmp_db_path))


@pytest.fixture
def seeded_engine(tmp_db_path):
    """DuckDBEngine with seed data aligned to common production tables."""
    conn = duckdb.connect(str(tmp_db_path))
    conn.execute(
        """
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
        """
    )
    conn.execute(
        """
        CREATE TABLE readings (
            timestamp TIMESTAMP,
            plant_uid VARCHAR,
            device_id VARCHAR,
            apparentPower_value DOUBLE,
            poaIrradiance_value DOUBLE,
            ambientTemperature_value DOUBLE,
            moduleTemperature_value DOUBLE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE solar_data (
            Site VARCHAR,
            Date VARCHAR,
            PR DOUBLE,
            Irradiance DOUBLE,
            Energy DOUBLE,
            Availability DOUBLE
        )
        """
    )
    conn.execute(
        """
        INSERT INTO plants (
            plant_uid, alias, dc_size_kw, ac_size_kw, latitude, longitude, tilt, azimuth
        ) VALUES
            ('uid-001', 'Sunny Acres', 5000, 4500, 51.5, -0.12, 30, 180),
            ('uid-002', 'Green Fields', 8000, 7200, 52.0, -1.5, 25, 190),
            ('uid-003', 'Hilltop Solar', 3000, 2700, 50.8, -2.1, 35, 175)
        """
    )
    conn.execute(
        """
        INSERT INTO readings (
            timestamp, plant_uid, device_id,
            apparentPower_value, poaIrradiance_value,
            ambientTemperature_value, moduleTemperature_value
        ) VALUES
            ('2026-01-01 00:00:00', 'uid-001', 'dev-1', 100.0, 10.0, 5.0, 12.0),
            ('2026-01-01 00:15:00', 'uid-001', 'dev-1', 110.0, 20.0, 6.0, 13.0),
            ('2026-01-01 00:30:00', 'uid-001', 'dev-2', 120.0, 30.0, 7.0, 14.0),
            ('2026-01-01 00:45:00', 'uid-002', 'dev-3', 130.0, 40.0, 8.0, 15.0)
        """
    )
    conn.execute(
        """
        INSERT INTO solar_data (
            Site, Date, PR, Irradiance, Energy, Availability
        ) VALUES
            ('Plant A', 'Jan-24', 0.82, 980.0, 1010.0, 99.5),
            ('Plant B', 'Jan-24', 0.85, 1020.0, 2050.0, 99.0),
            ('Plant C', 'Jan-24', 0.88, 990.0, 3075.0, 98.8)
        """
    )
    conn.close()
    return DuckDBEngine(str(tmp_db_path))
