"""Unit tests for CurtailmentEngine.

Tests use a mock ReadingsRepository so no database is required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from solar_platform.analysis.curtailment import CurtailmentEngine


def _ts(offset_minutes: int = 0) -> datetime:
    return datetime(2025, 6, 15, 10, offset_minutes, 0, tzinfo=timezone.utc)


def _make_engine(df: pd.DataFrame) -> CurtailmentEngine:
    """Return a CurtailmentEngine whose repository returns *df*."""
    engine = CurtailmentEngine.__new__(CurtailmentEngine)
    repo = MagicMock()
    repo.get_readings.return_value = df
    engine._readings = repo
    return engine


# ---------------------------------------------------------------------------
# Method 1: export-limit telemetry
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExportLimitTelemetry:
    def _build_df(self, n: int = 48) -> pd.DataFrame:
        """48 half-hourly intervals with irradiance and exportLimit_value.

        Curtailed intervals (10:20) have export limit set to 50 % and actual
        power capped at 50 % of the irradiance-derived expected value, so that
        the regression-based loss estimate produces a non-zero result.
        """
        timestamps = pd.date_range("2025-06-15 08:00", periods=n, freq="30min", tz="UTC")
        irr = np.linspace(200, 900, n)
        power = irr * 0.05  # ~50 kW at peak (uncurtailed relationship)
        export_limit = np.full(n, 100.0)
        # Mark 10 intervals as curtailed: limit 50 %, actual power also halved
        export_limit[10:20] = 50.0
        power[10:20] *= 0.5
        return pd.DataFrame({
            "timestamp": timestamps,
            "activepower_value": power,
            "exportLimit_value": export_limit,
            "poaIrradiance_value": irr,
        })

    def test_detects_curtailed_intervals(self):
        df = self._build_df()
        engine = _make_engine(df)
        result = engine.run("uid-001", _ts(), _ts(30))
        assert result.summary["curtailed_records"] == 10
        assert result.summary["detection_method"] == "export_limit"

    def test_curtailment_rate_correct(self):
        df = self._build_df(n=40)
        # All intervals curtailed
        df["exportLimit_value"] = 60.0
        engine = _make_engine(df)
        result = engine.run("uid-001", _ts(), _ts(30))
        assert result.summary["curtailment_rate_pct"] == 100.0

    def test_no_curtailment_when_all_at_100(self):
        df = self._build_df()
        df["exportLimit_value"] = 100.0
        engine = _make_engine(df)
        result = engine.run("uid-001", _ts(), _ts(30))
        assert result.summary["curtailed_records"] == 0
        assert result.summary["curtailment_rate_pct"] == 0.0

    def test_energy_loss_estimated(self):
        df = self._build_df()
        engine = _make_engine(df)
        result = engine.run("uid-001", _ts(), _ts(30))
        # With 10 curtailed intervals under reasonable irradiance, loss > 0
        assert result.summary["curtailed_energy_kwh"] > 0.0

    def test_result_includes_is_curtailed_column(self):
        df = self._build_df()
        engine = _make_engine(df)
        result = engine.run("uid-001", _ts(), _ts(30))
        assert result.timeseries is not None
        assert "is_curtailed" in result.timeseries.columns

    def test_custom_threshold_honoured(self):
        df = self._build_df()
        # Limit is 50 — only curtailed if threshold > 50; at threshold=40, nothing curtailed
        engine = _make_engine(df)
        result = engine.run("uid-001", _ts(), _ts(30), limit_threshold_pct=40)
        assert result.summary["curtailed_records"] == 0

    def test_watt_unit_conversion(self):
        """Power in Watts should be converted to kW before loss estimation."""
        df = self._build_df()
        df["activepower_value"] = df["activepower_value"] * 1000  # convert to W
        df["activepower_unit"] = "W"
        engine = _make_engine(df)
        result_w = engine.run("uid-001", _ts(), _ts(30))

        df2 = self._build_df()  # power already in kW, no unit column
        engine2 = _make_engine(df2)
        result_kw = engine2.run("uid-001", _ts(), _ts(30))

        # Loss estimates should be within 5 % of each other despite unit difference
        loss_w = result_w.summary["curtailed_energy_kwh"]
        loss_kw = result_kw.summary["curtailed_energy_kwh"]
        assert loss_w == pytest.approx(loss_kw, rel=0.05)


# ---------------------------------------------------------------------------
# Method 2: power-plateau fallback
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPowerPlateauFallback:
    def _build_plateau_df(self) -> pd.DataFrame:
        """Build a DataFrame with a clear flat-top plateau under high irradiance."""
        n = 60
        timestamps = pd.date_range("2025-06-15 07:00", periods=n, freq="15min", tz="UTC")
        irr = np.concatenate([
            np.linspace(100, 800, 20),   # rising
            np.full(20, 850),            # plateau conditions
            np.linspace(800, 100, 20),   # falling
        ])
        power = irr * 0.04
        # Force 15 intervals to a flat cap of 24 kW (plateau)
        power[20:35] = 24.0
        return pd.DataFrame({
            "timestamp": timestamps,
            "activepower_value": power,
            "poaIrradiance_value": irr,
        })

    def test_plateau_method_used_when_no_limit_col(self):
        df = self._build_plateau_df()
        engine = _make_engine(df)
        result = engine.run("uid-001", _ts(), _ts(30))
        assert result.summary["detection_method"] == "power_plateau"

    def test_plateau_detects_curtailed_intervals(self):
        df = self._build_plateau_df()
        engine = _make_engine(df)
        result = engine.run("uid-001", _ts(), _ts(30))
        assert result.summary["curtailed_records"] > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEdgeCases:
    def test_empty_dataframe_returns_warning(self):
        engine = _make_engine(pd.DataFrame())
        result = engine.run("uid-001", _ts(), _ts(30))
        assert result.warnings
        assert result.summary == {}

    def test_no_power_or_limit_col_returns_warning(self):
        df = pd.DataFrame({
            "timestamp": [_ts()],
            "some_other_col": [1.0],
        })
        engine = _make_engine(df)
        result = engine.run("uid-001", _ts(), _ts(30))
        assert result.warnings

    def test_all_nan_power_returns_warning(self):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-06-15", periods=5, freq="30min", tz="UTC"),
            "activepower_value": [float("nan")] * 5,
        })
        engine = _make_engine(df)
        result = engine.run("uid-001", _ts(), _ts(30))
        assert result.warnings

    def test_single_row_no_crash(self):
        df = pd.DataFrame({
            "timestamp": [_ts()],
            "activepower_value": [100.0],
            "exportLimit_value": [50.0],
            "poaIrradiance_value": [600.0],
        })
        engine = _make_engine(df)
        result = engine.run("uid-001", _ts(), _ts(30))
        assert result.summary.get("curtailed_records", 0) >= 0

    def test_analysis_type(self):
        engine = CurtailmentEngine.__new__(CurtailmentEngine)
        assert engine.analysis_type == "curtailment"
