"""Integration tests for data quality pipeline: insert readings → validate → score → detect gaps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import duckdb
import pandas as pd
import pytest

from solar_platform.data_quality.validators import (
    CapacityExceedanceValidator,
    FlatLineValidator,
    NegativeValueValidator,
    NighttimeGenerationValidator,
    RangeValidator,
    StalenessValidator,
    ValidationReport,
    ValidationSeverity,
    run_validation,
)
from solar_platform.data_quality.quality_scorer import QualityScorer
from solar_platform.data_quality.gap_detection import DataGap, GapDetector, GapSeverity
from solar_platform.db.engine import DuckDBEngine


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def dq_engine(tmp_path):
    """DuckDB engine with readings data for data quality tests."""
    db_path = tmp_path / "dq_test.duckdb"
    conn = duckdb.connect(str(db_path))

    conn.execute("""
        CREATE TABLE readings (
            timestamp TIMESTAMP,
            plant_uid VARCHAR,
            device_id VARCHAR,
            power_kw DOUBLE,
            energy_kwh DOUBLE,
            poa_wm2 DOUBLE,
            ambient_temp_c DOUBLE,
            module_temp_c DOUBLE
        )
    """)

    # Insert readings with a gap (missing data between 01:00 and 03:00)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(5):  # 00:00 to 01:00 every 15 min
        ts = base + timedelta(minutes=i * 15)
        rows.append((ts, "uid-001", "dev-1", 100.0 + i * 10, 25.0 + i, 500.0 + i * 20, 15.0, 30.0))

    # Gap from 01:00 to 03:00

    for i in range(5):  # 03:00 to 04:00 every 15 min
        ts = base + timedelta(hours=3, minutes=i * 15)
        rows.append((ts, "uid-001", "dev-1", 200.0 + i * 10, 50.0 + i, 600.0 + i * 20, 18.0, 35.0))

    for r in rows:
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?, ?, ?, ?)", list(r))

    conn.close()
    return DuckDBEngine(str(db_path))


# ── Validator Tests ──────────────────────────────────────────────────────


@pytest.mark.integration
class TestValidators:
    """Test individual validators against realistic readings."""

    def test_range_validator_passes_valid(self):
        v = RangeValidator()
        reading = {"power_kw": 1000.0, "poa_wm2": 800.0, "ambient_temp_c": 25.0}
        results = v.validate(reading, {})
        assert len(results) == 0

    def test_range_validator_flags_out_of_range(self):
        v = RangeValidator()
        reading = {"power_kw": -100.0, "ambient_temp_c": 100.0}
        results = v.validate(reading, {})
        assert len(results) == 2
        assert all(r.severity == ValidationSeverity.ERROR for r in results)

    def test_capacity_exceedance_warns(self):
        v = CapacityExceedanceValidator(tolerance_pct=1.10)
        reading = {"power_kw": 6000.0}
        plant = {"capacity_kw": 5000.0}
        results = v.validate(reading, plant)
        assert len(results) == 1
        assert results[0].severity == ValidationSeverity.WARNING

    def test_capacity_exceedance_passes_within_limit(self):
        v = CapacityExceedanceValidator(tolerance_pct=1.10)
        reading = {"power_kw": 5400.0}
        plant = {"capacity_kw": 5000.0}
        results = v.validate(reading, plant)
        assert len(results) == 0

    def test_negative_value_flags(self):
        v = NegativeValueValidator()
        reading = {"power_kw": -50.0, "energy_kwh": -10.0}
        results = v.validate(reading, {})
        assert len(results) == 2

    def test_nighttime_generation_flags(self):
        v = NighttimeGenerationValidator()
        reading = {"power_kw": 100.0, "poa_wm2": 0.0}
        results = v.validate(reading, {})
        assert len(results) == 1
        assert "irradiance" in results[0].message.lower()

    def test_staleness_validator_flags_old_reading(self):
        v = StalenessValidator(max_age_hours=1.0)
        old_ts = datetime.now(timezone.utc) - timedelta(hours=5)
        reading = {"timestamp": old_ts}
        results = v.validate(reading, {})
        assert len(results) == 1

    def test_staleness_validator_passes_recent(self):
        v = StalenessValidator(max_age_hours=24.0)
        recent_ts = datetime.now(timezone.utc) - timedelta(minutes=30)
        reading = {"timestamp": recent_ts}
        results = v.validate(reading, {})
        assert len(results) == 0

    def test_flatline_validator_detects_stuck_values(self):
        v = FlatLineValidator(fields=["power_kw"], min_repeat=3)
        readings = [{"power_kw": 100.0} for _ in range(5)]
        results = v.validate_series(readings, {})
        assert len(results) == 1
        assert "stuck" in results[0].message.lower()


@pytest.mark.integration
class TestRunValidation:
    """Test the run_validation pipeline function."""

    def test_run_validation_clean_reading(self):
        reading = {
            "power_kw": 500.0,
            "energy_kwh": 125.0,
            "poa_wm2": 800.0,
            "ambient_temp_c": 25.0,
            "timestamp": datetime.now(timezone.utc),
        }
        report = run_validation(reading, {"capacity_kw": 5000.0})
        assert isinstance(report, ValidationReport)
        assert report.error_count == 0
        assert report.quality_score > 80.0

    def test_run_validation_bad_reading(self):
        reading = {
            "power_kw": -100.0,
            "ambient_temp_c": 200.0,  # out of range
        }
        report = run_validation(reading, {})
        assert report.error_count >= 2
        assert report.quality_score < 100.0


# ── Quality Scorer Tests ─────────────────────────────────────────────────


@pytest.mark.integration
class TestQualityScorer:
    """Test QualityScorer with real validation pipeline."""

    def test_score_good_reading(self):
        scorer = QualityScorer()
        reading = {
            "power_kw": 500.0,
            "energy_kwh": 125.0,
            "poa_wm2": 800.0,
            "ambient_temp_c": 25.0,
            "source": "emig",
            "timestamp": datetime.now(timezone.utc),
        }
        score = scorer.score_reading(reading, {"capacity_kw": 5000.0})
        assert 50.0 <= score <= 100.0

    def test_score_bad_reading_lower(self):
        scorer = QualityScorer()
        reading = {
            "power_kw": -100.0,
            "source": "unknown",
        }
        score = scorer.score_reading(reading, {})
        good_reading = {
            "power_kw": 500.0,
            "energy_kwh": 125.0,
            "poa_wm2": 800.0,
            "ambient_temp_c": 25.0,
            "source": "emig",
            "timestamp": datetime.now(timezone.utc),
        }
        good_score = scorer.score_reading(good_reading, {"capacity_kw": 5000.0})
        assert score < good_score

    def test_score_batch(self):
        scorer = QualityScorer()
        df = pd.DataFrame({
            "power_kw": [100.0, 200.0, 300.0],
            "energy_kwh": [25.0, 50.0, 75.0],
            "poa_wm2": [400.0, 500.0, 600.0],
            "ambient_temp_c": [20.0, 22.0, 24.0],
            "source": ["emig", "emig", "emig"],
        })
        result = scorer.score_batch(df, {"capacity_kw": 5000.0})
        assert "quality_score" in result.columns
        assert len(result) == 3
        assert all(0 <= s <= 100 for s in result["quality_score"])


# ── Gap Detection Tests ──────────────────────────────────────────────────


@pytest.mark.integration
class TestGapDetection:
    """Test GapDetector against DuckDB with readings containing gaps."""

    def test_detect_gaps_finds_gap(self, dq_engine):
        with patch("services.data_quality.gap_detection.get_engine", return_value=dq_engine):
            detector = GapDetector()
            # Use naive datetimes to match DuckDB TIMESTAMP (tz-naive)
            gaps = detector.detect_gaps(
                plant_uid="uid-001",
                start=datetime(2026, 1, 1),
                end=datetime(2026, 1, 1, 5),
                expected_freq_minutes=15,
            )
        assert len(gaps) >= 1
        # The gap between 01:00 and 03:00 should be detected
        medium_gaps = [g for g in gaps if g.severity == GapSeverity.MEDIUM]
        assert len(medium_gaps) >= 1
        assert any(g.duration_minutes >= 60 for g in medium_gaps)

    def test_detect_gaps_empty_plant(self, dq_engine):
        with patch("services.data_quality.gap_detection.get_engine", return_value=dq_engine):
            detector = GapDetector()
            gaps = detector.detect_gaps(
                plant_uid="uid-nonexistent",
                start=datetime(2026, 1, 1),
                end=datetime(2026, 1, 2),
                expected_freq_minutes=15,
            )
        # Entire window should be flagged as a single gap
        assert len(gaps) == 1
        assert gaps[0].severity == GapSeverity.LONG

    def test_daily_completeness(self, dq_engine):
        with patch("services.data_quality.gap_detection.get_engine", return_value=dq_engine):
            detector = GapDetector()
            df = detector.daily_completeness(
                plant_uid="uid-001",
                start=datetime(2026, 1, 1),
                end=datetime(2026, 1, 1, 23, 59),
                expected_freq_minutes=15,
            )
        assert not df.empty
        assert "completeness_pct" in df.columns
        # Should be well below 100% since we only have ~10 readings for a full day
        assert df["completeness_pct"].iloc[0] < 100.0

    def test_gap_dataclass_properties(self):
        gap = DataGap(
            plant_uid="uid-001",
            start=datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc),
            severity=GapSeverity.MEDIUM,
            duration_minutes=120.0,
            expected_readings=8,
        )
        assert gap.duration == timedelta(hours=2)
        assert gap.severity == GapSeverity.MEDIUM
