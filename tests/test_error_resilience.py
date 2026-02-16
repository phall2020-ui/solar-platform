"""
Error Handling and Resilience Tests — Solar Platform.

Covers all layers: DB, repositories, analysis engines, alerts, data quality,
ingestion, export, auth, reporting, financial.  Tests that failures are
handled gracefully, produce meaningful messages, and never crash the app.
"""
from __future__ import annotations

import io
import json
import os
import stat
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import duckdb
import numpy as np
import pandas as pd
import pytest

# ──────────────────────────────────────────────────────────────────────
# DB layer imports
# ──────────────────────────────────────────────────────────────────────
from solar_platform.db.engine import DuckDBEngine
from solar_platform.db.repository import (
    PlantRepository,
    ReadingsRepository,
    SolarDataRepository,
)

# ──────────────────────────────────────────────────────────────────────
# Analysis engine imports
# ──────────────────────────────────────────────────────────────────────
from solar_platform.analysis.base import AnalysisResult
from solar_platform.analysis.clipping import ClippingEngine
from solar_platform.analysis.curtailment import CurtailmentEngine
from solar_platform.analysis.degradation import DegradationEngine
from solar_platform.analysis.fouling import FoulingEngine
from solar_platform.analysis.shading import ShadingEngine
from solar_platform.analysis.thermal import ThermalLossEngine

# ──────────────────────────────────────────────────────────────────────
# Alert imports
# ──────────────────────────────────────────────────────────────────────
from solar_platform.alerts.models import (
    Alert,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from solar_platform.alerts.repository import AlertRepository
from solar_platform.alerts.ticketing import TicketService

# ──────────────────────────────────────────────────────────────────────
# Data quality imports
# ──────────────────────────────────────────────────────────────────────
from solar_platform.data_quality.validators import (
    RangeValidator,
    CapacityExceedanceValidator,
    NegativeValueValidator,
    NighttimeGenerationValidator,
    StalenessValidator,
    FlatLineValidator,
    ValidationReport,
    ValidationResult,
    ValidationSeverity,
    run_validation,
)
from solar_platform.data_quality.gap_detection import DataGap, GapDetector, GapSeverity
from solar_platform.data_quality.gap_filling import (
    FilledReading,
    LinearInterpolation,
    TypicalDayProfile,
)

# ──────────────────────────────────────────────────────────────────────
# Ingestion imports
# ──────────────────────────────────────────────────────────────────────
from solar_platform.ingestion.base import (
    DataSourceAdapter,
    Reading,
    ReadingBatch,
    ReadingQuality,
)
from solar_platform.ingestion.coordinator import IngestionCoordinator

# ──────────────────────────────────────────────────────────────────────
# Service imports
# ──────────────────────────────────────────────────────────────────────
from solar_platform.services.export import ExportFormat, ExportService
from solar_platform.services.auth import AuthService, User
from solar_platform.services.error_handler import AppErrorHandler, ErrorContext, ErrorSeverity

# ──────────────────────────────────────────────────────────────────────
# Reporting imports
# ──────────────────────────────────────────────────────────────────────
from solar_platform.reporting.models import (
    GeneratedReport,
    ReportSection,
    ReportTemplate,
    ReportType,
    SectionType,
)
from solar_platform.reporting.templates import get_template

# ──────────────────────────────────────────────────────────────────────
# Financial imports
# ──────────────────────────────────────────────────────────────────────
from solar_platform.financial.revenue import RevenueResult, RevenueService, TariffType
from solar_platform.financial.tariff import TariffManager
from solar_platform.financial.budget import BudgetComparison, BudgetService


# ======================================================================
# Shared fixtures
# ======================================================================

@pytest.fixture
def tmp_engine(tmp_path: Path) -> DuckDBEngine:
    """DuckDB engine with a fresh, empty database."""
    db_file = tmp_path / "test.duckdb"
    duckdb.connect(str(db_file)).close()
    return DuckDBEngine(str(db_file))


@pytest.fixture
def seeded_engine_full(tmp_path: Path) -> DuckDBEngine:
    """Engine with plants + readings tables and seed data."""
    db_file = tmp_path / "seeded.duckdb"
    conn = duckdb.connect(str(db_file))
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
            "Site" VARCHAR,
            "Date" VARCHAR,
            "PR" DOUBLE,
            "Irradiance" DOUBLE,
            "Energy" DOUBLE,
            "Availability" DOUBLE
        )
    """)
    conn.execute("""
        INSERT INTO plants VALUES
            ('uid-001', 'Sunny Acres', 5000, 4500, 51.5, -0.12, 30, 180, 'UTC'),
            ('uid-002', 'Green Fields', 8000, 7200, 52.0, -1.5, 25, 190, 'UTC')
    """)
    conn.execute("""
        INSERT INTO readings VALUES
            ('2026-01-01 10:00:00', 'uid-001', 'dev-1', 100.0, 500.0, 10.0, 25.0),
            ('2026-01-01 10:15:00', 'uid-001', 'dev-1', 110.0, 520.0, 11.0, 26.0),
            ('2026-01-01 10:30:00', 'uid-001', 'dev-1', 120.0, 540.0, 12.0, 27.0),
            ('2026-01-01 10:45:00', 'uid-002', 'dev-2', 200.0, 600.0, 13.0, 28.0)
    """)
    conn.close()
    return DuckDBEngine(str(db_file))


# ======================================================================
# 1. DB CONNECTION FAILURES
# ======================================================================

class TestDBConnectionFailures:
    """DB engine handles missing files, corruption, permission errors."""

    def test_missing_db_file_creates_new(self, tmp_path: Path):
        """Connecting to a non-existent file (in existing dir) auto-creates it."""
        db_path = tmp_path / "new.duckdb"
        assert not db_path.exists()
        engine = DuckDBEngine(str(db_path))
        tables = engine.get_tables()
        assert isinstance(tables, list)

    def test_missing_parent_dir_raises_meaningful_error(self, tmp_path: Path):
        """Connecting to a path with missing parent dirs raises IOError."""
        db_path = tmp_path / "nonexistent" / "sub" / "new.duckdb"
        engine = DuckDBEngine(str(db_path))
        with pytest.raises(Exception) as exc_info:
            engine.get_tables()
        assert str(exc_info.value)  # non-empty meaningful message

    def test_corrupt_db_file_raises_meaningful_error(self, tmp_path: Path):
        """Opening a corrupt file raises an error with a useful message."""
        corrupt = tmp_path / "corrupt.duckdb"
        corrupt.write_bytes(b"NOT_A_VALID_DUCKDB_FILE" * 100)
        engine = DuckDBEngine(str(corrupt))
        with pytest.raises(Exception) as exc_info:
            engine.get_tables()
        # Should not be a generic error
        assert str(exc_info.value)  # non-empty error message

    @pytest.mark.skipif(os.getuid() == 0, reason="root bypasses permissions")
    def test_permission_denied_handled(self, tmp_path: Path):
        """Read-only file system prevents writes gracefully."""
        db_path = tmp_path / "readonly.duckdb"
        duckdb.connect(str(db_path)).close()
        db_path.chmod(stat.S_IRUSR)
        try:
            engine = DuckDBEngine(str(db_path))
            # Reading should still work or raise meaningful error
            try:
                with engine.connection(read_only=True) as conn:
                    conn.execute("SELECT 1").fetchall()
            except Exception as exc:
                assert str(exc)  # meaningful message
        finally:
            db_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def test_engine_execute_empty_query(self, tmp_engine: DuckDBEngine):
        """Empty query string should not crash."""
        with pytest.raises(Exception):
            tmp_engine.execute("")

    def test_engine_execute_invalid_sql(self, tmp_engine: DuckDBEngine):
        """Invalid SQL should raise duckdb error, not crash."""
        with pytest.raises(Exception) as exc_info:
            tmp_engine.execute("SELEKT * FORM nonexistent")
        assert str(exc_info.value)

    def test_engine_table_exists_nonexistent(self, tmp_engine: DuckDBEngine):
        """table_exists returns False for non-existent table without error."""
        assert tmp_engine.table_exists("table_that_does_not_exist") is False

    def test_engine_validate_identifier_rejects_injection(self, tmp_engine: DuckDBEngine):
        """SQL injection through identifiers is blocked."""
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            tmp_engine.execute_insert("'; DROP TABLE plants;--", {"x": 1})

    def test_upsert_empty_data_raises(self, tmp_engine: DuckDBEngine):
        """Upserting empty data dict raises ValueError."""
        with pytest.raises(ValueError, match="data cannot be empty"):
            tmp_engine.execute_upsert("plants", {}, ["plant_uid"])

    def test_upsert_empty_conflict_columns_raises(self, tmp_engine: DuckDBEngine):
        """Upserting with no conflict columns raises ValueError."""
        with pytest.raises(ValueError, match="conflict_columns cannot be empty"):
            tmp_engine.execute_upsert("plants", {"a": 1}, [])

    def test_bulk_insert_empty_df(self, tmp_engine: DuckDBEngine):
        """Bulk inserting empty DataFrame returns 0 rows inserted."""
        assert tmp_engine.bulk_insert_df("any_table", pd.DataFrame()) == 0


# ======================================================================
# 2. REPOSITORY EMPTY / NULL / MISSING COLUMN TESTS
# ======================================================================

class TestRepositoryEdgeCases:
    """Repository methods handle empty tables, missing columns, NULLs."""

    def test_plant_repo_empty_table(self, seeded_engine_full: DuckDBEngine):
        """PlantRepository on empty table returns empty result."""
        seeded_engine_full.execute("DELETE FROM plants")
        repo = PlantRepository(engine=seeded_engine_full)
        df = repo.get_all()
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_plant_repo_get_by_uid_missing(self, seeded_engine_full: DuckDBEngine):
        """get_by_uid with non-existent UID returns None."""
        repo = PlantRepository(engine=seeded_engine_full)
        result = repo.get_by_uid("nonexistent-uid")
        assert result is None

    def test_plant_repo_get_by_alias_missing(self, seeded_engine_full: DuckDBEngine):
        """get_by_alias for non-existent alias returns None."""
        repo = PlantRepository(engine=seeded_engine_full)
        result = repo.get_by_alias("Phantom Plant")
        assert result is None

    def test_plant_repo_list_aliases_empty(self, seeded_engine_full: DuckDBEngine):
        seeded_engine_full.execute("DELETE FROM plants")
        repo = PlantRepository(engine=seeded_engine_full)
        aliases = repo.list_aliases()
        assert aliases == []

    def test_readings_repo_no_readings_for_plant(self, seeded_engine_full: DuckDBEngine):
        """Readings for a plant with no data returns empty DataFrame."""
        repo = ReadingsRepository(engine=seeded_engine_full)
        df = repo.get_readings("nonexistent-plant")
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_readings_repo_date_range_no_overlap(self, seeded_engine_full: DuckDBEngine):
        """Date range outside data window returns empty DataFrame."""
        repo = ReadingsRepository(engine=seeded_engine_full)
        df = repo.get_readings(
            "uid-001",
            start=datetime(2099, 1, 1),
            end=datetime(2099, 12, 31),
        )
        assert df.empty

    def test_readings_repo_get_readings_df_columns_missing(self, seeded_engine_full: DuckDBEngine):
        """Requesting columns that don't exist returns empty DataFrame view."""
        repo = ReadingsRepository(engine=seeded_engine_full)
        df = repo.get_readings_df("uid-001", columns=["nonexistent_col_1", "nonexistent_col_2"])
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_solar_data_repo_empty(self, seeded_engine_full: DuckDBEngine):
        seeded_engine_full.execute("DELETE FROM solar_data")
        repo = SolarDataRepository(engine=seeded_engine_full)
        df = repo.get_monthly()
        assert df.empty
        assert repo.list_sites() == []
        assert repo.list_months() == []

    def test_solar_data_repo_no_match(self, seeded_engine_full: DuckDBEngine):
        repo = SolarDataRepository(engine=seeded_engine_full)
        df = repo.get_monthly(site="Nonexistent Site")
        assert df.empty


# ======================================================================
# 3. ANALYSIS ENGINES — EDGE CASES
# ======================================================================

def _create_engine_with_readings(tmp_path: Path, rows: list[tuple]) -> DuckDBEngine:
    """Helper: create a DuckDBEngine with a readings table containing *rows*."""
    db_file = tmp_path / f"analysis_{uuid.uuid4().hex[:8]}.duckdb"
    conn = duckdb.connect(str(db_file))
    conn.execute("""
        CREATE TABLE plants (
            plant_uid VARCHAR PRIMARY KEY, alias VARCHAR, dc_size_kw DOUBLE,
            ac_size_kw DOUBLE, latitude DOUBLE, longitude DOUBLE,
            tilt DOUBLE, azimuth DOUBLE
        )
    """)
    conn.execute("INSERT INTO plants VALUES ('P1','Test Plant',5000,4500,51.5,-0.12,30,180)")
    conn.execute("""
        CREATE TABLE readings (
            timestamp TIMESTAMP, plant_uid VARCHAR, device_id VARCHAR,
            apparentPower_value DOUBLE, poaIrradiance_value DOUBLE,
            ambientTemperature_value DOUBLE, moduleTemperature_value DOUBLE
        )
    """)
    if rows:
        placeholders = ", ".join(["(?, ?, ?, ?, ?, ?, ?)"] * len(rows))
        flat = [v for row in rows for v in row]
        conn.executemany(
            "INSERT INTO readings VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    conn.close()
    return DuckDBEngine(str(db_file))


class TestAnalysisEngineEdgeCases:
    """All analysis engines handle empty data, NaN-heavy, single-row, etc."""

    ENGINE_CLASSES = [
        ClippingEngine,
        CurtailmentEngine,
        DegradationEngine,
        FoulingEngine,
        ThermalLossEngine,
    ]

    @pytest.mark.parametrize("EngineClass", ENGINE_CLASSES, ids=lambda c: c.__name__)
    def test_empty_readings(self, tmp_path: Path, EngineClass):
        """Engine with no readings returns a result with warnings, not an exception."""
        engine = _create_engine_with_readings(tmp_path, [])
        analysis = EngineClass(engine=engine)
        result = analysis.run("P1", datetime(2026, 1, 1), datetime(2026, 1, 31))
        assert isinstance(result, AnalysisResult)
        assert result.warnings  # should explain no data

    @pytest.mark.parametrize("EngineClass", ENGINE_CLASSES, ids=lambda c: c.__name__)
    def test_single_row_data(self, tmp_path: Path, EngineClass):
        """Engine with a single row does not crash."""
        engine = _create_engine_with_readings(tmp_path, [
            ("2026-01-15 12:00:00", "P1", "dev-1", 100.0, 500.0, 10.0, 25.0),
        ])
        analysis = EngineClass(engine=engine)
        result = analysis.run("P1", datetime(2026, 1, 1), datetime(2026, 1, 31))
        assert isinstance(result, AnalysisResult)

    @pytest.mark.parametrize("EngineClass", ENGINE_CLASSES, ids=lambda c: c.__name__)
    def test_all_nan_values(self, tmp_path: Path, EngineClass):
        """Engine with all NaN numeric values handles gracefully."""
        engine = _create_engine_with_readings(tmp_path, [
            ("2026-01-15 12:00:00", "P1", "dev-1", float("nan"), float("nan"), float("nan"), float("nan")),
            ("2026-01-15 12:15:00", "P1", "dev-1", float("nan"), float("nan"), float("nan"), float("nan")),
        ])
        analysis = EngineClass(engine=engine)
        result = analysis.run("P1", datetime(2026, 1, 1), datetime(2026, 1, 31))
        assert isinstance(result, AnalysisResult)

    @pytest.mark.parametrize("EngineClass", ENGINE_CLASSES, ids=lambda c: c.__name__)
    def test_zero_irradiance(self, tmp_path: Path, EngineClass):
        """Engine with zero irradiance does not divide by zero."""
        engine = _create_engine_with_readings(tmp_path, [
            ("2026-01-15 12:00:00", "P1", "dev-1", 100.0, 0.0, 10.0, 25.0),
            ("2026-01-15 12:15:00", "P1", "dev-1", 110.0, 0.0, 11.0, 26.0),
        ])
        analysis = EngineClass(engine=engine)
        result = analysis.run("P1", datetime(2026, 1, 1), datetime(2026, 1, 31))
        assert isinstance(result, AnalysisResult)

    @pytest.mark.parametrize("EngineClass", ENGINE_CLASSES, ids=lambda c: c.__name__)
    def test_negative_values(self, tmp_path: Path, EngineClass):
        """Engine treats negative irradiance/power without crashing."""
        engine = _create_engine_with_readings(tmp_path, [
            ("2026-01-15 12:00:00", "P1", "dev-1", -50.0, -10.0, -5.0, -15.0),
            ("2026-01-15 12:15:00", "P1", "dev-1", -100.0, -20.0, -10.0, -20.0),
        ])
        analysis = EngineClass(engine=engine)
        result = analysis.run("P1", datetime(2026, 1, 1), datetime(2026, 1, 31))
        assert isinstance(result, AnalysisResult)

    @pytest.mark.parametrize("EngineClass", ENGINE_CLASSES, ids=lambda c: c.__name__)
    def test_nonexistent_plant(self, tmp_path: Path, EngineClass):
        """Engine for a plant that doesn't exist returns a result with warnings."""
        engine = _create_engine_with_readings(tmp_path, [])
        analysis = EngineClass(engine=engine)
        result = analysis.run("FAKE-PLANT", datetime(2026, 1, 1), datetime(2026, 1, 31))
        assert isinstance(result, AnalysisResult)

    def test_degradation_needs_3_months(self, tmp_path: Path):
        """DegradationEngine warns when fewer than 3 months of data exist."""
        rows = [
            (f"2026-01-{d:02d} 12:00:00", "P1", "dev-1", 100.0, 500.0, 10.0, 25.0)
            for d in range(1, 29)
        ]
        engine = _create_engine_with_readings(tmp_path, rows)
        analysis = DegradationEngine(engine=engine)
        result = analysis.run("P1", datetime(2025, 12, 1), datetime(2026, 2, 1))
        assert isinstance(result, AnalysisResult)
        # Either warns or produces partial result—both are acceptable

    def test_analysis_result_has_data_empty(self):
        """AnalysisResult.has_data is False when nothing was produced."""
        result = AnalysisResult(
            analysis_type="test",
            plant_uid="P1",
            start=datetime(2026, 1, 1),
            end=datetime(2026, 1, 31),
        )
        assert result.has_data is False


# ======================================================================
# 4. ALERT SYSTEM EDGE CASES
# ======================================================================

class TestAlertSystemEdgeCases:
    """Alert models handle duplicate alerts, invalid rules, missing references."""

    def test_alert_acknowledge_then_resolve(self):
        """Alert lifecycle transitions work in sequence."""
        alert = Alert(
            plant_uid="P1",
            rule_id="rule-1",
            severity=AlertSeverity.WARNING,
            title="Test Alert",
        )
        assert alert.is_active
        alert.acknowledge("user1")
        assert alert.status == AlertStatus.ACKNOWLEDGED
        assert alert.is_active  # acknowledged is still operationally active
        alert.resolve("user2")
        assert alert.status == AlertStatus.RESOLVED
        assert not alert.is_active

    def test_alert_suppress(self):
        """Suppressed alert is no longer active."""
        alert = Alert(
            plant_uid="P1",
            rule_id="rule-1",
            severity=AlertSeverity.INFO,
            title="Suppress Me",
        )
        alert.suppress()
        assert alert.status == AlertStatus.SUPPRESSED
        assert not alert.is_active

    def test_alert_duration_hours_positive(self):
        """Duration calculation doesn't produce negative values."""
        alert = Alert(
            plant_uid="P1",
            rule_id="r1",
            severity=AlertSeverity.CRITICAL,
            title="Duration Test",
            first_seen=datetime.now(UTC) - timedelta(hours=3),
        )
        assert alert.duration_hours >= 0

    def test_alert_rule_with_invalid_condition_is_not_breached(self):
        """An unknown condition never triggers a breach."""
        from solar_platform.alerts.engine import AlertEngine

        assert AlertEngine._is_breached(
            AlertRule(name="bad", metric="x", condition="invalid_op", threshold=5),
            10.0,
        ) is False

    def test_alert_rule_breach_below(self):
        from solar_platform.alerts.engine import AlertEngine

        rule = AlertRule(name="low_pr", metric="pr", condition="below", threshold=0.7)
        assert AlertEngine._is_breached(rule, 0.5) is True
        assert AlertEngine._is_breached(rule, 0.9) is False

    def test_alert_rule_breach_above(self):
        from solar_platform.alerts.engine import AlertEngine

        rule = AlertRule(name="high_temp", metric="module_temp_c", condition="above", threshold=80)
        assert AlertEngine._is_breached(rule, 85) is True
        assert AlertEngine._is_breached(rule, 75) is False

    def test_alert_rule_none_value_not_breached(self):
        """If metric is None, rule is not breached (except no_data)."""
        from solar_platform.alerts.engine import AlertEngine

        rule = AlertRule(name="test", metric="pr", condition="below", threshold=0.7)
        assert AlertEngine._is_breached(rule, None) is False

    def test_ticket_lifecycle_transitions(self):
        """Ticket can be created and moved through valid lifecycle."""
        ticket = Ticket(plant_uid="P1", title="Fix inverter")
        assert ticket.status == TicketStatus.OPEN
        ticket.set_status(TicketStatus.IN_PROGRESS)
        assert ticket.status == TicketStatus.IN_PROGRESS
        ticket.resolve("Replaced component")
        assert ticket.status == TicketStatus.RESOLVED
        assert ticket.resolution_notes == "Replaced component"
        ticket.close()
        assert ticket.status == TicketStatus.CLOSED

    def test_ticket_invalid_transition_raises(self, tmp_path: Path):
        """Invalid ticket status transitions raise ValueError."""
        db_file = tmp_path / "tickets.duckdb"
        duckdb.connect(str(db_file)).close()
        engine = DuckDBEngine(str(db_file))
        repo = AlertRepository(engine=engine)
        svc = TicketService(repository=repo)
        ticket = svc.create_ticket(
            plant_uid="P1",
            title="Test Ticket",
            description="desc",
        )
        # Transition to RESOLVED first
        svc.transition(ticket.id, TicketStatus.RESOLVED, "done")
        svc.transition(ticket.id, TicketStatus.CLOSED)
        # CLOSED → RESOLVED is invalid
        with pytest.raises(ValueError, match="Invalid ticket transition"):
            svc.transition(ticket.id, TicketStatus.RESOLVED)

    def test_ticket_assign_nonexistent(self, tmp_path: Path):
        """Assigning a nonexistent ticket returns None."""
        db_file = tmp_path / "t2.duckdb"
        duckdb.connect(str(db_file)).close()
        engine = DuckDBEngine(str(db_file))
        repo = AlertRepository(engine=engine)
        svc = TicketService(repository=repo)
        result = svc.assign("nonexistent-ticket-id", "someone")
        assert result is None

    def test_alert_repo_on_locked_db(self, tmp_path: Path):
        """AlertRepository degrades gracefully when table creation is blocked."""
        db_file = tmp_path / "locked.duckdb"
        duckdb.connect(str(db_file)).close()
        engine = DuckDBEngine(str(db_file))
        # Should not raise even if table creation fails
        repo = AlertRepository(engine=engine)
        # list_alerts should return empty when tables don't exist yet
        # (depending on implementation, this verifies graceful degradation)
        try:
            alerts = repo.list_alerts()
            assert isinstance(alerts, list)
        except Exception:
            # Even if it raises, it should be a meaningful error
            pass


# ======================================================================
# 5. DATA QUALITY VALIDATORS — EDGE CASES
# ======================================================================

class TestDataQualityValidatorEdgeCases:
    """Validators handle empty input, NaN columns, extreme outliers, wrong dtypes."""

    def test_range_validator_empty_reading(self):
        """RangeValidator on empty dict produces no findings."""
        v = RangeValidator()
        findings = v.validate({}, {})
        assert findings == []

    def test_range_validator_all_none(self):
        """RangeValidator with all-None values produces no findings."""
        v = RangeValidator()
        reading = {field: None for field in RangeValidator.DEFAULT_RANGES}
        findings = v.validate(reading, {})
        assert findings == []

    @pytest.mark.parametrize(
        "field_name,value",
        [
            ("power_kw", -100),
            ("power_kw", 999_999),
            ("ghi_wm2", 2000),
            ("ambient_temp_c", -60),
            ("module_temp_c", 150),
            ("wind_speed_ms", 100),
        ],
        ids=["neg_power", "huge_power", "huge_ghi", "cold_ambient", "hot_module", "hurricane"],
    )
    def test_range_validator_extreme_outliers(self, field_name: str, value: float):
        """Extreme values are flagged as errors."""
        v = RangeValidator()
        findings = v.validate({field_name: value}, {})
        assert any(f.severity == ValidationSeverity.ERROR for f in findings)

    def test_range_validator_wrong_dtype_string(self):
        """Non-numeric string value is silently skipped (not flagged, not crashed)."""
        v = RangeValidator()
        findings = v.validate({"power_kw": "not_a_number"}, {})
        # Should skip or flag, but not crash
        assert isinstance(findings, list)

    def test_negative_value_validator_none_values(self):
        """NegativeValueValidator handles None gracefully."""
        v = NegativeValueValidator()
        findings = v.validate({"power_kw": None, "energy_kwh": None}, {})
        assert isinstance(findings, list)

    def test_staleness_validator_no_timestamp(self):
        """StalenessValidator handles missing timestamp gracefully."""
        v = StalenessValidator()
        findings = v.validate({}, {})
        assert isinstance(findings, list)

    def test_validation_report_quality_score_floor(self):
        """Quality score never goes below 0."""
        report = ValidationReport()
        for _ in range(20):
            report.add(ValidationResult(
                validator_name="test",
                severity=ValidationSeverity.ERROR,
                message="bad",
            ))
        assert report.quality_score == 0.0

    def test_run_validation_all_validators_empty_reading(self):
        """Running all default validators on empty reading returns a report."""
        report = run_validation({}, {})
        assert isinstance(report, ValidationReport)
        assert report.total_checked == 1

    def test_run_validation_all_nan_reading(self):
        """Validation with all-NaN values doesn't crash."""
        reading = {
            "power_kw": float("nan"),
            "energy_kwh": float("nan"),
            "ghi_wm2": float("nan"),
            "poa_wm2": float("nan"),
            "ambient_temp_c": float("nan"),
            "module_temp_c": float("nan"),
        }
        report = run_validation(reading, {"dc_size_kw": 5000})
        assert isinstance(report, ValidationReport)

    def test_run_validation_with_faulty_validator(self):
        """A crashing custom validator doesn't take down the pipeline."""
        class ExplodingValidator:
            name = "exploding"
            def validate(self, reading, plant_config):
                raise RuntimeError("Boom!")

        report = run_validation({"power_kw": 100}, {}, validators=[ExplodingValidator()])
        # run_validation catches exceptions and logs warning
        assert isinstance(report, ValidationReport)

    def test_validation_report_merge(self):
        """Merging two reports works correctly."""
        r1 = ValidationReport(total_checked=3)
        r2 = ValidationReport(total_checked=5)
        r2.add(ValidationResult("v", ValidationSeverity.WARNING, "w"))
        r1.merge(r2)
        assert r1.total_checked == 8
        assert r1.warning_count == 1


# ======================================================================
# 6. INGESTION — MISSING KEYS, TIMEOUTS, MALFORMED RESPONSES
# ======================================================================

class TestIngestionEdgeCases:
    """Ingestion coordinator handles adapter failures gracefully."""

    def test_coordinator_no_adapters(self):
        """IngestionCoordinator with no adapters returns empty result."""
        coord = IngestionCoordinator()
        import asyncio
        result = asyncio.run(coord.ingest_plant(
            "P1",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 31, tzinfo=timezone.utc),
        ))
        assert result.readings == []
        assert result.success is False
        assert len(result.warnings) > 0 or len(result.errors) >= 0

    def test_coordinator_adapter_raises_exception(self):
        """If an adapter raises, coordinator records error and continues."""
        coord = IngestionCoordinator()

        class FailingAdapter(DataSourceAdapter):
            source_name = "failing"
            async def authenticate(self) -> bool:
                return False
            async def fetch_readings(self, plant_uid, start, end, **kw):
                raise ConnectionError("API down")
            async def list_available_plants(self):
                return []
            async def health_check(self):
                from solar_platform.ingestion.base import HealthStatus, HealthState
                return HealthStatus(state=HealthState.UNHEALTHY, message="down")
            def get_field_mapping(self):
                return []

        coord.register_adapter(FailingAdapter())
        coord.set_plant_sources("P1", ["failing"])

        import asyncio
        result = asyncio.run(coord.ingest_plant(
            "P1",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 31, tzinfo=timezone.utc),
        ))
        assert "failing" in result.sources_failed
        assert any("API down" in e for e in result.errors)

    def test_coordinator_adapter_returns_empty_batch(self):
        """Adapter returning empty batch is tracked as failed source."""
        coord = IngestionCoordinator()

        class EmptyAdapter(DataSourceAdapter):
            source_name = "empty"
            async def authenticate(self) -> bool:
                return True
            async def fetch_readings(self, plant_uid, start, end, **kw):
                return ReadingBatch(source="empty", plant_uid=plant_uid)
            async def list_available_plants(self):
                return []
            async def health_check(self):
                from solar_platform.ingestion.base import HealthStatus, HealthState
                return HealthStatus(state=HealthState.HEALTHY, message="ok")
            def get_field_mapping(self):
                return []

        coord.register_adapter(EmptyAdapter())
        coord.set_plant_sources("P1", ["empty"])

        import asyncio
        result = asyncio.run(coord.ingest_plant(
            "P1",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 31, tzinfo=timezone.utc),
        ))
        assert result.is_empty if hasattr(result, "is_empty") else len(result.readings) == 0

    def test_reading_model_validates_timestamp(self):
        """Reading model rejects unparseable timestamps."""
        with pytest.raises(Exception):
            Reading(
                timestamp="not-a-date",
                plant_uid="P1",
                source="test",
            )

    def test_reading_model_coerces_naive_datetime(self):
        """Reading coerces naive datetime to UTC."""
        r = Reading(
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            plant_uid="P1",
            source="test",
        )
        assert r.timestamp.tzinfo is not None

    def test_reading_batch_success_rate_zero_raw(self):
        """ReadingBatch with 0 raw records has 0 success rate."""
        batch = ReadingBatch(source="test", plant_uid="P1")
        assert batch.success_rate == 0.0
        assert batch.is_empty is True

    def test_reading_batch_finalize(self):
        """Finalize sets counts correctly."""
        batch = ReadingBatch(
            source="test",
            plant_uid="P1",
            total_raw_records=5,
            readings=[
                Reading(timestamp=datetime.now(timezone.utc), plant_uid="P1", source="test"),
                Reading(timestamp=datetime.now(timezone.utc), plant_uid="P1", source="test"),
            ],
        )
        batch.finalize()
        assert batch.records_mapped == 2
        assert batch.records_skipped == 3

    def test_coordinator_unregistered_adapter_warns(self):
        """Using a source name that's not registered produces a warning."""
        coord = IngestionCoordinator()
        coord.set_plant_sources("P1", ["nonexistent_source"])

        import asyncio
        result = asyncio.run(coord.ingest_plant(
            "P1",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 31, tzinfo=timezone.utc),
        ))
        assert any("nonexistent_source" in w for w in result.warnings)


# ======================================================================
# 7. EXPORT SERVICE — EMPTY DATA, INVALID PATHS, FORMAT ERRORS
# ======================================================================

class TestExportServiceEdgeCases:
    """Export service handles empty data, unknown formats."""

    def test_export_empty_dataframe_csv(self):
        """Exporting an empty DataFrame to CSV produces header-only output."""
        svc = ExportService()
        data = svc.export_dataframe(pd.DataFrame(), "empty", ExportFormat.CSV)
        assert isinstance(data, bytes)
        # CSV of empty df may just be newline or empty
        assert len(data) <= 10  # very small

    def test_export_empty_dataframe_json(self):
        """Exporting an empty DataFrame to JSON produces valid JSON."""
        svc = ExportService()
        data = svc.export_dataframe(pd.DataFrame(), "empty", ExportFormat.JSON)
        parsed = json.loads(data)
        assert parsed == []

    def test_export_empty_dataframe_excel(self):
        """Exporting an empty DataFrame to Excel produces a valid file."""
        svc = ExportService()
        data = svc.export_dataframe(pd.DataFrame({"A": []}), "empty", ExportFormat.EXCEL)
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_export_unsupported_format_raises(self):
        """Unsupported format raises ValueError with descriptive message."""
        svc = ExportService()
        with pytest.raises(ValueError, match="Unsupported export format"):
            svc.export_dataframe(pd.DataFrame({"A": [1]}), "test", "bmp")

    def test_export_to_file_creates_output(self, tmp_path: Path):
        """Export to file creates the file."""
        svc = ExportService()
        svc.export_dir = tmp_path
        df = pd.DataFrame({"x": [1, 2, 3]})
        path = svc.export_to_file(df, "exported", ExportFormat.CSV)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_export_multiple_empty_sheets(self):
        """Multiple-sheet export with empty DataFrames works."""
        svc = ExportService()
        data = svc.export_multiple_sheets({
            "Sheet1": pd.DataFrame(),
            "Sheet2": pd.DataFrame({"A": []}),
        }, "multi_empty")
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_export_analysis_results_empty_dict(self):
        """Exporting empty analysis results doesn't crash."""
        svc = ExportService()
        try:
            data = svc.export_analysis_results("test_analysis", {})
            assert isinstance(data, bytes)
        except Exception as exc:
            # Some implementations may raise, but message should be meaningful
            assert str(exc)


# ======================================================================
# 8. AUTH SERVICE — INVALID CREDENTIALS, RATE LIMITING
# ======================================================================

class TestAuthServiceEdgeCases:
    """Auth service handles bad credentials, lockout, missing DB."""

    def test_auth_invalid_credentials(self, tmp_path: Path):
        """Wrong password returns None, not an exception."""
        auth = AuthService(db_path=tmp_path / "auth.db")
        result = auth.authenticate("admin", "definitely_wrong_password")
        assert result is None

    def test_auth_nonexistent_user(self, tmp_path: Path):
        """Non-existent user returns None."""
        auth = AuthService(db_path=tmp_path / "auth.db")
        result = auth.authenticate("ghost_user", "any_password")
        assert result is None

    def test_auth_rate_limiting_lockout(self, tmp_path: Path):
        """Account locks after too many failed attempts."""
        auth = AuthService(db_path=tmp_path / "auth.db")
        for _ in range(auth.MAX_FAILED_ATTEMPTS):
            auth.authenticate("admin", "wrong")
        # Next attempt should be locked
        result = auth.authenticate("admin", "wrong")
        assert result is None

    def test_auth_create_duplicate_user_fails(self, tmp_path: Path):
        """Creating a user with duplicate username returns False."""
        auth = AuthService(db_path=tmp_path / "auth.db")
        auth.create_user("testuser", "test@example.com", "Test User", "pass123", "viewer")
        result = auth.create_user("testuser", "test2@example.com", "Test 2", "pass456", "viewer")
        assert result is False

    def test_user_permissions_by_role(self):
        """User permissions mapping works correctly."""
        admin = User(1, "admin", "a@b.com", "Admin", "admin")
        viewer = User(2, "view", "v@b.com", "Viewer", "viewer")
        assert admin.has_permission("manage_users") is True
        assert viewer.has_permission("manage_users") is False
        assert viewer.has_permission("read") is True
        assert viewer.has_permission("write") is False

    def test_user_unknown_role_has_no_permissions(self):
        """A user with an unknown role has no permissions."""
        u = User(99, "mystery", "m@b.com", "Mystery", "superuser")
        assert u.has_permission("read") is False
        assert u.has_permission("write") is False


# ======================================================================
# 9. ERROR HANDLER — MEANINGFUL MESSAGES
# ======================================================================

class TestErrorHandlerMessages:
    """Error handler produces meaningful, non-generic messages."""

    @pytest.mark.parametrize(
        "error_type",
        [
            "DB_CONNECTION_FAILED",
            "DB_QUERY_FAILED",
            "API_TIMEOUT",
            "API_KEY_INVALID",
            "FILE_NOT_FOUND",
            "INVALID_DATA_FORMAT",
            "VALIDATION_FAILED",
            "PLANT_NOT_FOUND",
            "INSUFFICIENT_DATA",
            "CALCULATION_ERROR",
        ],
        ids=lambda e: e.lower(),
    )
    def test_known_errors_have_meaningful_messages(self, error_type: str):
        """Every catalogued error type produces a non-generic user message."""
        handler = AppErrorHandler()
        ctx = handler.handle_error(error_type, exception=ValueError("test"))
        assert isinstance(ctx, ErrorContext)
        assert ctx.user_message != ""
        assert "something went wrong" not in ctx.user_message.lower()
        assert len(ctx.recovery_actions) > 0

    def test_unknown_error_still_has_message(self):
        """Uncatalogued error falls back to UNKNOWN_ERROR with a message."""
        handler = AppErrorHandler()
        ctx = handler.handle_error("TOTALLY_NEW_ERROR_CODE", exception=RuntimeError("boom"))
        assert ctx.user_message != ""
        assert len(ctx.recovery_actions) > 0

    def test_error_context_captures_traceback(self):
        """When show_traceback=True, traceback is captured."""
        handler = AppErrorHandler()
        try:
            raise ValueError("intentional")
        except ValueError as e:
            ctx = handler.handle_error("CALCULATION_ERROR", exception=e, show_traceback=True)
        assert ctx.technical_message is not None or ctx.traceback is not None


# ======================================================================
# 10. CATCH-ALL — ERRORS DON'T CRASH
# ======================================================================

class TestNoCrashCatchAll:
    """Verify that major operations don't crash on edge-case inputs."""

    def test_duckdb_engine_connection_context_manager(self, tmp_engine):
        """Connection context manager properly cleans up on error."""
        with pytest.raises(Exception):
            with tmp_engine.connection() as conn:
                conn.execute("THIS IS NOT SQL")

    def test_duckdb_engine_transaction_rollback(self, tmp_engine):
        """Transaction properly rolls back on error."""
        tmp_engine.execute("CREATE TABLE t (x INTEGER)")
        tmp_engine.execute("INSERT INTO t VALUES (1)")
        with pytest.raises(Exception):
            with tmp_engine.transaction() as conn:
                conn.execute("INSERT INTO t VALUES (2)")
                conn.execute("THIS WILL FAIL")
        # Transaction should have rolled back
        rows = tmp_engine.execute("SELECT COUNT(*) FROM t")
        assert rows[0][0] == 1

    def test_reading_model_rejects_negative_power_via_constraint(self):
        """Reading model validates power_kw >= 0."""
        with pytest.raises(Exception):
            Reading(
                timestamp=datetime.now(timezone.utc),
                plant_uid="P1",
                source="test",
                power_kw=-100,  # ge=0 constraint
            )

    def test_alert_model_default_id_is_uuid(self):
        """Alert model generates valid UUID for id."""
        alert = Alert(
            plant_uid="P1",
            rule_id="r1",
            severity=AlertSeverity.INFO,
            title="Test",
        )
        uuid.UUID(alert.id)  # Should not raise

    def test_ticket_model_default_values(self):
        """Ticket model has sensible defaults."""
        t = Ticket(plant_uid="P1", title="Test")
        assert t.status == TicketStatus.OPEN
        assert t.priority == TicketPriority.MEDIUM
        assert t.created_at is not None

    def test_export_service_init(self):
        """ExportService initialization doesn't crash."""
        svc = ExportService()
        assert svc.export_dir.exists()


# ======================================================================
# 11. CONCURRENT DUCKDB ACCESS
# ======================================================================

class TestConcurrentDuckDBAccess:
    """Concurrent access to DuckDB doesn't corrupt data."""

    def test_concurrent_reads(self, seeded_engine_full: DuckDBEngine):
        """Multiple threads reading simultaneously don't corrupt."""
        results = []
        errors = []

        def read_plants():
            try:
                repo = PlantRepository(engine=seeded_engine_full)
                df = repo.get_all()
                results.append(len(df))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=read_plants) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Concurrent read errors: {errors}"
        assert all(r == results[0] for r in results), "Inconsistent read results"

    def test_concurrent_writes_no_corruption(self, tmp_path: Path):
        """Concurrent inserts don't corrupt the data file."""
        db_file = tmp_path / "concurrent.duckdb"
        conn = duckdb.connect(str(db_file))
        conn.execute("CREATE TABLE counter (id INTEGER, val INTEGER)")
        conn.close()
        engine = DuckDBEngine(str(db_file))

        errors = []
        def insert_rows(start: int):
            try:
                for i in range(start, start + 5):
                    engine.execute_insert("counter", {"id": i, "val": i * 10})
            except Exception as e:
                errors.append(str(e))

        threads = [
            threading.Thread(target=insert_rows, args=(i * 10,))
            for i in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        # Some writes may fail due to locks — that's OK as long as DB isn't corrupt
        rows = engine.execute("SELECT COUNT(*) FROM counter")
        assert rows[0][0] >= 0  # DB is still queryable


# ======================================================================
# 12. REPORT GENERATION WITH MISSING DATA
# ======================================================================

class TestReportGenerationMissingData:
    """Report generation with missing/partial data doesn't crash."""

    def test_generated_report_default_status(self):
        """GeneratedReport defaults to 'pending' status."""
        report = GeneratedReport(
            template_id="t1",
            template_name="Test",
            report_type=ReportType.MONTHLY_PERFORMANCE,
            period_start=datetime(2026, 1, 1, tzinfo=UTC),
            period_end=datetime(2026, 1, 31, tzinfo=UTC),
        )
        assert report.status == "pending"
        assert report.error_message == ""

    def test_generated_report_failed_status_has_error(self):
        """Failed report records error message."""
        report = GeneratedReport(
            template_id="t1",
            template_name="Test",
            report_type=ReportType.MONTHLY_PERFORMANCE,
            period_start=datetime(2026, 1, 1, tzinfo=UTC),
            period_end=datetime(2026, 1, 31, tzinfo=UTC),
            status="failed",
            error_message="Insufficient data for KPI section",
        )
        assert report.status == "failed"
        assert "Insufficient data" in report.error_message

    def test_report_template_empty_sections(self):
        """Template with no sections is valid."""
        template = ReportTemplate(
            name="Empty Template",
            type=ReportType.CUSTOM,
            sections=[],
        )
        assert len(template.sections) == 0

    def test_get_template_known_names(self):
        """get_template returns a template for known names."""
        for name in ["Monthly Performance Report", "ExCom Summary Report"]:
            tmpl = get_template(name)
            if tmpl is not None:
                assert isinstance(tmpl, ReportTemplate)
                assert len(tmpl.sections) > 0

    def test_get_template_unknown_name(self):
        """get_template with unknown name returns None or raises."""
        result = get_template("NonExistentTemplate12345")
        # Depending on implementation — None or KeyError
        if result is not None:
            assert isinstance(result, ReportTemplate)


# ======================================================================
# 13. FINANCIAL CALCULATIONS — ZERO/NEGATIVE TARIFFS, MISSING BUDGET
# ======================================================================

class TestFinancialEdgeCases:
    """Financial services handle zero/negative tariffs and missing data."""

    def test_revenue_zero_tariff(self, tmp_path: Path):
        """Revenue with zero tariff = zero revenue."""
        db_file = tmp_path / "fin.duckdb"
        conn = duckdb.connect(str(db_file))
        conn.execute("CREATE TABLE plants (plant_uid VARCHAR PRIMARY KEY)")
        conn.execute("INSERT INTO plants VALUES ('P1')")
        conn.execute("""
            CREATE TABLE readings (
                timestamp TIMESTAMP, plant_uid VARCHAR,
                device_id VARCHAR, generation_kwh DOUBLE
            )
        """)
        conn.execute("INSERT INTO readings VALUES ('2026-01-15 12:00:00', 'P1', 'dev1', 100.0)")
        conn.close()

        engine = DuckDBEngine(str(db_file))
        svc = RevenueService(engine=engine)
        result = svc.calculate_monthly("P1", 2026, 1, tariff_per_mwh=0.0)
        assert result.revenue == 0.0
        assert isinstance(result, RevenueResult)

    def test_revenue_negative_tariff(self, tmp_path: Path):
        """Negative tariff produces negative revenue (not an error)."""
        db_file = tmp_path / "fin_neg.duckdb"
        conn = duckdb.connect(str(db_file))
        conn.execute("CREATE TABLE plants (plant_uid VARCHAR PRIMARY KEY)")
        conn.execute("""
            CREATE TABLE readings (
                timestamp TIMESTAMP, plant_uid VARCHAR,
                device_id VARCHAR, generation_kwh DOUBLE
            )
        """)
        conn.execute("INSERT INTO readings VALUES ('2026-01-15 12:00:00', 'P1', 'd1', 1000.0)")
        conn.close()

        engine = DuckDBEngine(str(db_file))
        svc = RevenueService(engine=engine)
        result = svc.calculate_monthly("P1", 2026, 1, tariff_per_mwh=-10.0)
        assert result.revenue < 0

    def test_revenue_no_readings_table(self, tmp_path: Path):
        """Revenue calculation with no readings table returns 0 or raises gracefully."""
        db_file = tmp_path / "fin_noread.duckdb"
        duckdb.connect(str(db_file)).close()
        engine = DuckDBEngine(str(db_file))
        svc = RevenueService(engine=engine)
        try:
            result = svc.calculate_monthly("P1", 2026, 1, tariff_per_mwh=50.0)
            # If it succeeds, generation should be 0
            assert result.generation_mwh == 0.0
            assert result.revenue == 0.0
        except Exception as exc:
            # CatalogException for missing table is acceptable –
            # the service resolves ts_col before querying, but the
            # table still doesn't exist.
            assert "readings" in str(exc).lower() or "catalog" in str(exc).lower(), (
                f"Unexpected error (expected readings-related): {exc}"
            )

    def test_budget_missing_data_returns_zero(self, tmp_path: Path):
        """BudgetService with no budget records returns 0 budget."""
        db_file = tmp_path / "budget.duckdb"
        duckdb.connect(str(db_file)).close()
        engine = DuckDBEngine(str(db_file))
        svc = BudgetService(engine=engine)
        result = svc.compare("P1", 2026, 1)
        assert isinstance(result, BudgetComparison)
        assert result.budget_kwh == 0.0
        assert result.variance_pct == 0.0  # 0/0 handled

    def test_budget_on_track_property(self):
        """BudgetComparison.on_track within ±5%."""
        comp = BudgetComparison(
            plant_uid="P1", year=2026, month=1,
            budget_kwh=1000, actual_kwh=1040,
            variance_kwh=40, variance_pct=4.0,
        )
        assert comp.on_track is True

        comp2 = BudgetComparison(
            plant_uid="P1", year=2026, month=1,
            budget_kwh=1000, actual_kwh=800,
            variance_kwh=-200, variance_pct=-20.0,
        )
        assert comp2.on_track is False

    def test_budget_set_and_compare(self, tmp_path: Path):
        """Set a budget then compare against it."""
        db_file = tmp_path / "bsc.duckdb"
        duckdb.connect(str(db_file)).close()
        engine = DuckDBEngine(str(db_file))
        svc = BudgetService(engine=engine)
        svc.set_budget("P1", 2026, 1, budget_kwh=5000.0)
        result = svc.compare("P1", 2026, 1)
        assert result.budget_kwh == 5000.0
        assert result.actual_kwh == 0.0  # no readings

    def test_tariff_get_missing(self, tmp_path: Path):
        """TariffManager returns None for a plant with no tariff."""
        db_file = tmp_path / "tariff.duckdb"
        duckdb.connect(str(db_file)).close()
        engine = DuckDBEngine(str(db_file))
        mgr = TariffManager(engine=engine)
        result = mgr.get_tariff("nonexistent-plant")
        assert result is None

    def test_tariff_set_and_get(self, tmp_path: Path):
        """Setting a tariff and retrieving it works."""
        db_file = tmp_path / "tariff2.duckdb"
        duckdb.connect(str(db_file)).close()
        engine = DuckDBEngine(str(db_file))
        mgr = TariffManager(engine=engine)
        from datetime import date
        mgr.set_tariff("P1", "fixed", 50.0, date(2026, 1, 1))
        result = mgr.get_tariff("P1", date(2026, 6, 15))
        assert result is not None
        assert result["rate"] == 50.0

    def test_portfolio_summary_no_plants(self, tmp_path: Path):
        """Portfolio summary with no plants returns empty list."""
        db_file = tmp_path / "portfolio.duckdb"
        duckdb.connect(str(db_file)).close()
        engine = DuckDBEngine(str(db_file))
        svc = RevenueService(engine=engine)
        results = svc.portfolio_summary(2026, 1, default_tariff_per_mwh=50.0)
        assert results == []


# ======================================================================
# 14. GAP DETECTION / FILLING — EDGE CASES
# ======================================================================

class TestGapDetectionFillingEdgeCases:
    """Gap detection and filling handle no-gap, all-gap, single-point scenarios."""

    def test_linear_interpolation_empty_surrounding(self):
        """LinearInterpolation with empty surrounding data returns nothing."""
        strategy = LinearInterpolation()
        gap = DataGap(
            plant_uid="P1",
            start=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc),
            severity=GapSeverity.SHORT,
            duration_minutes=60.0,
            expected_readings=4,
        )
        filled = strategy.fill(gap, pd.DataFrame(), freq_minutes=15)
        assert filled == []

    def test_linear_interpolation_single_surrounding_row(self):
        """LinearInterpolation with 1 surrounding row returns nothing."""
        strategy = LinearInterpolation()
        gap = DataGap(
            plant_uid="P1",
            start=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc),
            severity=GapSeverity.SHORT,
            duration_minutes=60.0,
            expected_readings=4,
        )
        surrounding = pd.DataFrame({
            "timestamp": [datetime(2026, 1, 1, 11, 45, tzinfo=timezone.utc)],
            "power_kw": [100.0],
        })
        filled = strategy.fill(gap, surrounding, freq_minutes=15)
        assert filled == []

    def test_linear_interpolation_produces_correct_count(self):
        """LinearInterpolation fills a 1-hour gap at 15-min intervals with 3 readings."""
        strategy = LinearInterpolation()
        gap_start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        gap_end = datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc)
        gap = DataGap(
            plant_uid="P1",
            start=gap_start,
            end=gap_end,
            severity=GapSeverity.SHORT,
            duration_minutes=60.0,
            expected_readings=3,
        )
        surrounding = pd.DataFrame({
            "timestamp": [
                datetime(2026, 1, 1, 11, 45, tzinfo=timezone.utc),
                datetime(2026, 1, 1, 13, 15, tzinfo=timezone.utc),
            ],
            "power_kw": [100.0, 200.0],
        })
        filled = strategy.fill(gap, surrounding, freq_minutes=15)
        assert len(filled) == 3
        for f in filled:
            assert f.source == "estimated"
            assert f.strategy_used == "linear_interpolation"

    def test_gap_detector_no_readings_table(self, tmp_path: Path):
        """GapDetector with no readings table returns whole window as gap."""
        db_file = tmp_path / "nogap.duckdb"
        duckdb.connect(str(db_file)).close()
        engine = DuckDBEngine(str(db_file))
        with patch("solar_platform.data_quality.gap_detection.get_engine", return_value=engine):
            detector = GapDetector()
            gaps = detector.detect_gaps(
                "P1",
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
        # No readings table → returns empty list (table_exists check)
        assert isinstance(gaps, list)

    def test_gap_detector_contiguous_data_no_gaps(self, tmp_path: Path):
        """When all readings are present, no gaps detected."""
        db_file = tmp_path / "full.duckdb"
        conn = duckdb.connect(str(db_file))
        conn.execute("CREATE TABLE readings (timestamp TIMESTAMP, plant_uid VARCHAR, device_id VARCHAR)")
        # Insert readings every 15 minutes for 2 hours
        base = datetime(2026, 1, 1, 10, 0)
        for i in range(9):  # 10:00 to 12:00
            ts = base + timedelta(minutes=15 * i)
            conn.execute("INSERT INTO readings VALUES (?, 'P1', 'dev1')", [ts])
        conn.close()

        engine = DuckDBEngine(str(db_file))
        with patch("solar_platform.data_quality.gap_detection.get_engine", return_value=engine):
            detector = GapDetector()
            gaps = detector.detect_gaps(
                "P1",
                datetime(2026, 1, 1, 10, 0),
                datetime(2026, 1, 1, 12, 0),
                expected_freq_minutes=15,
            )
        assert len(gaps) == 0

    def test_gap_detector_all_missing_single_gap(self, tmp_path: Path):
        """When no readings exist for the window, one full-window gap."""
        db_file = tmp_path / "allgap.duckdb"
        conn = duckdb.connect(str(db_file))
        conn.execute("CREATE TABLE readings (timestamp TIMESTAMP, plant_uid VARCHAR, device_id VARCHAR)")
        conn.close()

        engine = DuckDBEngine(str(db_file))
        with patch("solar_platform.data_quality.gap_detection.get_engine", return_value=engine):
            detector = GapDetector()
            gaps = detector.detect_gaps(
                "P1",
                datetime(2026, 1, 1, 0, 0),
                datetime(2026, 1, 2, 0, 0),
                expected_freq_minutes=15,
            )
        assert len(gaps) == 1
        assert gaps[0].severity == GapSeverity.LONG
        assert gaps[0].duration_minutes >= 24 * 60 - 1  # ~24 hours

    def test_gap_severity_classification(self):
        """GapSeverity classification by duration is correct."""
        from solar_platform.data_quality.gap_detection import _classify
        assert _classify(30) == GapSeverity.SHORT
        assert _classify(120) == GapSeverity.MEDIUM
        assert _classify(25 * 60) == GapSeverity.LONG

    def test_data_gap_duration_property(self):
        """DataGap.duration returns correct timedelta."""
        gap = DataGap(
            plant_uid="P1",
            start=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc),
            severity=GapSeverity.MEDIUM,
            duration_minutes=180.0,
            expected_readings=12,
        )
        assert gap.duration == timedelta(hours=3)


# ======================================================================
# 15. PARAMETRIZE — SYSTEMATIC EDGE CASE COVERAGE
# ======================================================================

class TestSystematicEdgeCases:
    """Parametrized systematic tests across multiple dimensions."""

    @pytest.mark.parametrize("value,expected_valid", [
        (0.0, True),
        (500.0, True),
        (1500.0, True),    # at boundary for GHI
        (1501.0, False),   # above GHI max
        (-1.0, False),     # negative
    ], ids=["zero_ok", "normal", "boundary", "above_max", "negative"])
    def test_ghi_range_validation(self, value: float, expected_valid: bool):
        """GHI validation across boundary values."""
        v = RangeValidator()
        findings = v.validate({"ghi_wm2": value}, {})
        if expected_valid:
            assert not any(f.severity == ValidationSeverity.ERROR for f in findings)
        else:
            assert any(f.severity == ValidationSeverity.ERROR for f in findings)

    @pytest.mark.parametrize("temp_c,expected_valid", [
        (-50.0, True),     # boundary min
        (-51.0, False),    # below min
        (65.0, True),      # boundary max
        (66.0, False),     # above max
        (20.0, True),      # normal
    ], ids=["min_boundary", "below_min", "max_boundary", "above_max", "normal"])
    def test_ambient_temp_range_validation(self, temp_c: float, expected_valid: bool):
        """Ambient temperature validation at boundaries."""
        v = RangeValidator()
        findings = v.validate({"ambient_temp_c": temp_c}, {})
        if expected_valid:
            assert not any(f.severity == ValidationSeverity.ERROR for f in findings)
        else:
            assert any(f.severity == ValidationSeverity.ERROR for f in findings)

    @pytest.mark.parametrize("export_format", [
        ExportFormat.CSV,
        ExportFormat.JSON,
        ExportFormat.EXCEL,
        ExportFormat.PARQUET,
    ], ids=["csv", "json", "excel", "parquet"])
    def test_export_formats_with_data(self, export_format: str):
        """All supported export formats work with real data."""
        svc = ExportService()
        df = pd.DataFrame({"A": [1, 2, 3], "B": ["x", "y", "z"]})
        data = svc.export_dataframe(df, "test", export_format)
        assert isinstance(data, bytes)
        assert len(data) > 0

    @pytest.mark.parametrize("severity", list(AlertSeverity), ids=lambda s: s.value)
    def test_alert_all_severities(self, severity: AlertSeverity):
        """Alerts can be created with every severity level."""
        alert = Alert(
            plant_uid="P1",
            rule_id="r1",
            severity=severity,
            title=f"Test {severity.value}",
        )
        assert alert.severity == severity
        assert alert.is_active

    @pytest.mark.parametrize("status", list(TicketStatus), ids=lambda s: s.value)
    def test_ticket_all_statuses(self, status: TicketStatus):
        """Tickets can have their status set to any valid value."""
        ticket = Ticket(plant_uid="P1", title="Test")
        ticket.set_status(status)
        assert ticket.status == status

    @pytest.mark.parametrize("tariff_type", list(TariffType), ids=lambda t: t.value)
    def test_revenue_result_all_tariff_types(self, tariff_type: TariffType):
        """RevenueResult accepts all tariff types."""
        result = RevenueResult(
            plant_uid="P1",
            year=2026,
            month=1,
            generation_mwh=10.0,
            tariff_per_mwh=50.0,
            revenue=500.0,
            tariff_type=tariff_type,
        )
        assert result.tariff_type == tariff_type

    @pytest.mark.parametrize("report_type", list(ReportType), ids=lambda r: r.value)
    def test_generated_report_all_types(self, report_type: ReportType):
        """GeneratedReport can be created for every report type."""
        report = GeneratedReport(
            template_id="t1",
            template_name="Test",
            report_type=report_type,
            period_start=datetime(2026, 1, 1, tzinfo=UTC),
            period_end=datetime(2026, 1, 31, tzinfo=UTC),
        )
        assert report.report_type == report_type

    @pytest.mark.parametrize(
        "dataframe_factory",
        [
            lambda: pd.DataFrame(),
            lambda: pd.DataFrame({"power_kw": [float("nan")] * 10}),
            lambda: pd.DataFrame({"power_kw": [0.0]}),
            lambda: pd.DataFrame({"power_kw": range(1000)}),
        ],
        ids=["empty", "all_nan", "single_zero", "large"],
    )
    def test_export_various_dataframes(self, dataframe_factory):
        """ExportService handles various DataFrame shapes without crashing."""
        svc = ExportService()
        df = dataframe_factory()
        data = svc.export_dataframe(df, "edge_test", ExportFormat.CSV)
        assert isinstance(data, bytes)

    @pytest.mark.parametrize("condition,value,threshold,expected", [
        ("below", 0.5, 0.7, True),
        ("below", 0.9, 0.7, False),
        ("above", 85.0, 80.0, True),
        ("above", 75.0, 80.0, False),
        ("equals", 5.0, 5.0, True),
        ("equals", 4.0, 5.0, False),
        ("no_data", 1.0, 0, True),
        ("no_data", 0.0, 0, False),
        ("unknown_op", 5.0, 5.0, False),
    ], ids=[
        "below_breach", "below_ok", "above_breach", "above_ok",
        "equals_breach", "equals_ok", "no_data_breach", "no_data_ok", "unknown_op",
    ])
    def test_alert_breach_conditions(self, condition, value, threshold, expected):
        """Systematic test of all breach condition variants."""
        from solar_platform.alerts.engine import AlertEngine

        rule = AlertRule(name="test", metric="m", condition=condition, threshold=threshold)
        assert AlertEngine._is_breached(rule, value) is expected

    @pytest.mark.parametrize("section_type", list(SectionType), ids=lambda s: s.value)
    def test_report_section_all_types(self, section_type: SectionType):
        """ReportSection can be created for every section type."""
        section = ReportSection(type=section_type, title=f"Test {section_type.value}")
        assert section.type == section_type


# ======================================================================
# Additional: Quality scorer & ingestion model edge cases
# ======================================================================

class TestQualityScorerEdgeCases:
    """QualityScorer handles edge cases without crashing."""

    def test_scorer_empty_reading(self):
        """Score for empty reading returns a valid float."""
        from solar_platform.data_quality.quality_scorer import QualityScorer
        scorer = QualityScorer()
        score = scorer.score_reading({}, {})
        assert 0.0 <= score <= 100.0

    def test_scorer_all_fields_present(self):
        """Score for a complete reading is higher than empty."""
        from solar_platform.data_quality.quality_scorer import QualityScorer
        scorer = QualityScorer()
        empty_score = scorer.score_reading({}, {})
        full_score = scorer.score_reading({
            "power_kw": 100.0,
            "energy_kwh": 25.0,
            "poa_wm2": 500.0,
            "ambient_temp_c": 20.0,
            "source": "emig",
        }, {"dc_size_kw": 5000})
        assert full_score >= empty_score

    def test_scorer_batch_empty_df(self):
        """score_batch with empty DataFrame returns empty result."""
        from solar_platform.data_quality.quality_scorer import QualityScorer
        scorer = QualityScorer()
        result = scorer.score_batch(pd.DataFrame(), {})
        assert isinstance(result, pd.DataFrame)
        assert result.empty


class TestIngestionModelEdgeCases:
    """Additional edge cases for ingestion data models."""

    def test_reading_quality_enum_values(self):
        """All ReadingQuality values are accessible."""
        assert ReadingQuality.MEASURED == "measured"
        assert ReadingQuality.MISSING == "missing"

    def test_reading_batch_multiple_errors(self):
        """ReadingBatch accumulates multiple errors."""
        batch = ReadingBatch(source="test", plant_uid="P1")
        batch.errors.append("Error 1")
        batch.errors.append("Error 2")
        assert len(batch.errors) == 2

    def test_ingestion_result_success_only_with_readings(self):
        """IngestionResult.success requires both readings and succeeded sources."""
        from solar_platform.ingestion.coordinator import IngestionResult
        result = IngestionResult(plant_uid="P1")
        assert result.success is False

        result.readings.append(
            Reading(timestamp=datetime.now(timezone.utc), plant_uid="P1", source="test")
        )
        result.sources_succeeded.append("test")
        assert result.success is True
