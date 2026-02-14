"""Unit tests for gap filling strategies."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pandas as pd


@pytest.mark.unit
class TestFilledReading:
    def test_defaults(self):
        from services.data_quality.gap_filling import FilledReading
        fr = FilledReading(
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            plant_uid="p1",
        )
        assert fr.source == "estimated"
        assert fr.values == {}
        assert fr.strategy_used == ""
        assert fr.device_id == ""


@pytest.mark.unit
class TestLinearInterpolation:
    def _make_gap(self):
        from services.data_quality.gap_detection import DataGap, GapSeverity
        return DataGap(
            plant_uid="p1",
            start=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            end=datetime(2025, 1, 1, 0, 45, tzinfo=timezone.utc),
            severity=GapSeverity.SHORT,
            duration_minutes=45,
            expected_readings=2,
        )

    def test_name(self):
        from services.data_quality.gap_filling import LinearInterpolation
        assert LinearInterpolation().name == "linear_interpolation"

    def test_fill_empty_surrounding(self):
        from services.data_quality.gap_filling import LinearInterpolation
        strategy = LinearInterpolation()
        gap = self._make_gap()
        result = strategy.fill(gap, pd.DataFrame(), freq_minutes=15)
        assert result == []

    def test_fill_single_row_surrounding(self):
        from services.data_quality.gap_filling import LinearInterpolation
        strategy = LinearInterpolation()
        gap = self._make_gap()
        df = pd.DataFrame({
            "timestamp": [datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)],
            "power_kw": [100.0],
        })
        result = strategy.fill(gap, df, freq_minutes=15)
        assert result == []

    def test_fill_generates_readings(self):
        from services.data_quality.gap_filling import LinearInterpolation
        strategy = LinearInterpolation()
        gap = self._make_gap()
        df = pd.DataFrame({
            "timestamp": [
                datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc),
            ],
            "power_kw": [100.0, 200.0],
        })
        result = strategy.fill(gap, df, freq_minutes=15)
        assert len(result) == 2  # ts at :15 and :30
        assert all(r.source == "estimated" for r in result)
        assert all(r.strategy_used == "linear_interpolation" for r in result)

    def test_fill_interpolated_values(self):
        from services.data_quality.gap_filling import LinearInterpolation
        strategy = LinearInterpolation()
        gap = self._make_gap()
        df = pd.DataFrame({
            "timestamp": [
                datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc),
            ],
            "power_kw": [0.0, 100.0],
        })
        result = strategy.fill(gap, df, freq_minutes=15)
        # At :15, fraction = 15/60 = 0.25, so value ≈ 25
        assert result[0].values["power_kw"] == pytest.approx(25.0, rel=0.01)


@pytest.mark.unit
class TestTypicalDayProfile:
    def _make_gap(self):
        from services.data_quality.gap_detection import DataGap, GapSeverity
        return DataGap(
            plant_uid="p1",
            start=datetime(2025, 1, 1, 6, 0, tzinfo=timezone.utc),
            end=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
            severity=GapSeverity.MEDIUM,
            duration_minutes=180,
            expected_readings=12,
        )

    def test_name(self):
        from services.data_quality.gap_filling import TypicalDayProfile
        assert TypicalDayProfile().name == "typical_day_profile"

    def test_fill_empty_surrounding(self):
        from services.data_quality.gap_filling import TypicalDayProfile
        strategy = TypicalDayProfile()
        gap = self._make_gap()
        result = strategy.fill(gap, pd.DataFrame(), freq_minutes=15)
        assert result == []

    def test_fill_generates_readings(self):
        from services.data_quality.gap_filling import TypicalDayProfile
        strategy = TypicalDayProfile()
        gap = self._make_gap()
        # Create surrounding data matching the gap time-of-day window
        timestamps = [
            datetime(2025, 1, 1, h, m, tzinfo=timezone.utc)
            for h in range(0, 24)
            for m in range(0, 60, 15)
        ]
        df = pd.DataFrame({
            "timestamp": timestamps,
            "power_kw": [float(i) for i in range(len(timestamps))],
        })
        result = strategy.fill(gap, df, freq_minutes=15)
        assert len(result) > 0
        assert all(r.source == "estimated" for r in result)
        assert all(r.strategy_used == "typical_day_profile" for r in result)


@pytest.mark.unit
class TestAutoFillGap:
    def test_short_gap_uses_linear(self):
        from services.data_quality.gap_filling import auto_fill_gap
        from services.data_quality.gap_detection import DataGap, GapSeverity

        gap = DataGap(
            plant_uid="p1",
            start=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            end=datetime(2025, 1, 1, 0, 45, tzinfo=timezone.utc),
            severity=GapSeverity.SHORT,
            duration_minutes=45,
            expected_readings=2,
        )
        df = pd.DataFrame({
            "timestamp": [
                datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc),
            ],
            "power_kw": [100.0, 200.0],
        })
        result = auto_fill_gap(gap, df, freq_minutes=15)
        assert all(r.strategy_used == "linear_interpolation" for r in result)

    def test_long_gap_returns_empty(self):
        from services.data_quality.gap_filling import auto_fill_gap
        from services.data_quality.gap_detection import DataGap, GapSeverity

        gap = DataGap(
            plant_uid="p1",
            start=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            end=datetime(2025, 1, 3, 0, 0, tzinfo=timezone.utc),
            severity=GapSeverity.LONG,
            duration_minutes=48 * 60,
            expected_readings=192,
        )
        result = auto_fill_gap(gap, pd.DataFrame(), freq_minutes=15)
        assert result == []
