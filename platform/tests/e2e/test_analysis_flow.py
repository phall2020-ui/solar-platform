"""E2E test for a complete analysis flow: create engine → run → verify result format."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import duckdb
import pandas as pd
import pytest

from services.analysis.base import AnalysisResult
from services.database.engine import DuckDBEngine


# ── Fixture ──────────────────────────────────────────────────────────────


@pytest.fixture
def analysis_db(tmp_path):
    """DuckDB engine with realistic readings for running analysis engines."""
    db_path = tmp_path / "analysis_e2e.duckdb"
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
        INSERT INTO plants VALUES
            ('uid-001', 'Test Plant', 5000, 4500, 51.5, -0.12, 30, 180, 'UTC')
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

    # Generate 30 days of hourly readings
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for day in range(30):
        for hour in range(24):
            ts = base + timedelta(days=day, hours=hour)
            # Simulate daytime power: higher during sun hours (6-18)
            if 6 <= hour <= 18:
                power = 3000.0 + (hour - 6) * 200.0
                irr = 400.0 + (hour - 6) * 50.0
            else:
                power = 0.0
                irr = 0.0
            conn.execute(
                "INSERT INTO readings VALUES (?, ?, ?, ?, ?, ?, ?)",
                [ts, "uid-001", "dev-1", power, irr, 20.0 + hour * 0.5, 25.0 + hour * 0.8],
            )

    conn.close()
    return DuckDBEngine(str(db_path))


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.e2e
class TestClippingAnalysisFlow:
    """E2E: run ClippingEngine and verify result structure."""

    def test_clipping_engine_produces_result(self, analysis_db):
        from services.analysis.clipping import ClippingEngine

        engine = ClippingEngine(engine=analysis_db)
        result = engine.run(
            "uid-001",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 31, tzinfo=timezone.utc),
        )
        assert isinstance(result, AnalysisResult)
        assert result.analysis_type == "clipping"
        assert result.plant_uid == "uid-001"
        assert result.has_data
        assert "clipping_rate_pct" in result.summary
        assert "records" in result.summary
        assert result.summary["records"] > 0
        assert result.calculation_seconds >= 0

    def test_clipping_with_no_readings(self, analysis_db):
        from services.analysis.clipping import ClippingEngine

        engine = ClippingEngine(engine=analysis_db)
        result = engine.run(
            "uid-nonexistent",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 31, tzinfo=timezone.utc),
        )
        assert len(result.warnings) > 0


@pytest.mark.e2e
class TestThermalAnalysisFlow:
    """E2E: run ThermalLossEngine and verify result structure."""

    def test_thermal_engine_produces_result(self, analysis_db):
        from services.analysis.thermal import ThermalLossEngine

        engine = ThermalLossEngine(engine=analysis_db)
        result = engine.run(
            "uid-001",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 31, tzinfo=timezone.utc),
        )
        assert isinstance(result, AnalysisResult)
        assert result.analysis_type == "thermal"
        assert result.plant_uid == "uid-001"


@pytest.mark.e2e
class TestAnalysisResultModel:
    """E2E: verify AnalysisResult model properties."""

    def test_result_has_data_with_summary(self):
        result = AnalysisResult(
            analysis_type="test",
            plant_uid="uid-001",
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end=datetime(2026, 1, 31, tzinfo=timezone.utc),
            summary={"records": 100},
        )
        assert result.has_data is True

    def test_result_has_data_with_timeseries(self):
        result = AnalysisResult(
            analysis_type="test",
            plant_uid="uid-001",
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end=datetime(2026, 1, 31, tzinfo=timezone.utc),
            timeseries=pd.DataFrame({"a": [1, 2, 3]}),
        )
        assert result.has_data is True

    def test_result_no_data_empty(self):
        result = AnalysisResult(
            analysis_type="test",
            plant_uid="uid-001",
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )
        assert result.has_data is False
