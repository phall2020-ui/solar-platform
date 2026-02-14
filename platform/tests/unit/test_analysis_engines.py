"""Unit tests for analysis engines."""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# AnalysisResult
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestAnalysisResult:
    def test_has_data_with_summary(self):
        from services.analysis.base import AnalysisResult
        r = AnalysisResult(
            analysis_type="test",
            plant_uid="p1",
            start=datetime(2025, 1, 1),
            end=datetime(2025, 1, 31),
            summary={"key": "value"},
        )
        assert r.has_data is True

    def test_has_data_empty(self):
        from services.analysis.base import AnalysisResult
        r = AnalysisResult(
            analysis_type="test",
            plant_uid="p1",
            start=datetime(2025, 1, 1),
            end=datetime(2025, 1, 31),
        )
        assert r.has_data is False

    def test_has_data_with_timeseries(self):
        from services.analysis.base import AnalysisResult
        r = AnalysisResult(
            analysis_type="test",
            plant_uid="p1",
            start=datetime(2025, 1, 1),
            end=datetime(2025, 1, 31),
            timeseries=pd.DataFrame({"a": [1]}),
        )
        assert r.has_data is True

    def test_has_data_with_empty_timeseries(self):
        from services.analysis.base import AnalysisResult
        r = AnalysisResult(
            analysis_type="test",
            plant_uid="p1",
            start=datetime(2025, 1, 1),
            end=datetime(2025, 1, 31),
            timeseries=pd.DataFrame(),
        )
        assert r.has_data is False

    def test_defaults(self):
        from services.analysis.base import AnalysisResult
        r = AnalysisResult(
            analysis_type="test",
            plant_uid="p1",
            start=datetime(2025, 1, 1),
            end=datetime(2025, 1, 31),
        )
        assert r.warnings == []
        assert r.losses == {}
        assert r.calculation_seconds == 0.0
        assert r.data_quality_score == 1.0


# ---------------------------------------------------------------------------
# ClippingEngine
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestClippingEngine:
    @patch("services.analysis.clipping.ReadingsRepository")
    def test_no_readings(self, MockRepo):
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = pd.DataFrame()
        MockRepo.return_value = mock_repo

        from services.analysis.clipping import ClippingEngine
        engine = ClippingEngine()
        result = engine.run("p1", datetime(2025, 1, 1), datetime(2025, 1, 31))

        assert result.analysis_type == "clipping"
        assert "No readings" in result.warnings[0]

    @patch("services.analysis.clipping.ReadingsRepository")
    def test_with_data(self, MockRepo):
        n = 200
        times = pd.date_range("2025-01-01", periods=n, freq="15min")
        power = np.concatenate([np.random.uniform(50, 100, n - 5), [100.0] * 5])
        irr = np.random.uniform(600, 1000, n)
        df = pd.DataFrame({
            "timestamp": times,
            "activepower": power,
            "poa": irr,
        })
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = df
        MockRepo.return_value = mock_repo

        from services.analysis.clipping import ClippingEngine
        engine = ClippingEngine()
        result = engine.run("p1", datetime(2025, 1, 1), datetime(2025, 1, 31))

        assert result.analysis_type == "clipping"
        assert "clipping_rate_pct" in result.summary
        assert "clipping" in result.losses

    @patch("services.analysis.clipping.ReadingsRepository")
    def test_missing_columns(self, MockRepo):
        df = pd.DataFrame({"unrelated": [1, 2, 3]})
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = df
        MockRepo.return_value = mock_repo

        from services.analysis.clipping import ClippingEngine
        engine = ClippingEngine()
        result = engine.run("p1", datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert len(result.warnings) > 0


# ---------------------------------------------------------------------------
# DegradationEngine
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDegradationEngine:
    @patch("services.analysis.degradation.ReadingsRepository")
    def test_no_readings(self, MockRepo):
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = pd.DataFrame()
        MockRepo.return_value = mock_repo

        from services.analysis.degradation import DegradationEngine
        engine = DegradationEngine()
        result = engine.run("p1", datetime(2024, 1, 1), datetime(2025, 1, 1))

        assert result.analysis_type == "degradation"
        assert "No readings" in result.warnings[0]

    @patch("services.analysis.degradation.ReadingsRepository")
    def test_with_enough_data(self, MockRepo):
        # Generate 6 months of daily data with slight PR decline
        dates = pd.date_range("2024-07-01", periods=180, freq="D")
        pr = np.linspace(85, 82, 180) + np.random.normal(0, 0.5, 180)
        irr = np.random.uniform(400, 1000, 180)
        df = pd.DataFrame({
            "timestamp": dates,
            "performance_ratio": pr,
            "poa": irr,
        })
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = df
        MockRepo.return_value = mock_repo

        from services.analysis.degradation import DegradationEngine
        engine = DegradationEngine()
        result = engine.run("p1", datetime(2024, 7, 1), datetime(2025, 1, 1))

        assert result.analysis_type == "degradation"
        assert "annualized_pr_change_pct" in result.summary


# ---------------------------------------------------------------------------
# ShadingEngine
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestShadingEngine:
    @patch("services.analysis.shading.ReadingsRepository")
    def test_no_readings(self, MockRepo):
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = pd.DataFrame()
        MockRepo.return_value = mock_repo

        from services.analysis.shading import ShadingEngine
        engine = ShadingEngine()
        result = engine.run("p1", datetime(2025, 1, 1), datetime(2025, 3, 1))

        assert result.analysis_type == "shading"
        assert len(result.warnings) > 0

    @patch("services.analysis.shading.ReadingsRepository")
    def test_with_data(self, MockRepo):
        times = pd.date_range("2025-01-01", periods=500, freq="15min")
        power = np.abs(np.sin(np.linspace(0, 20 * np.pi, 500))) * 100
        irr = np.abs(np.sin(np.linspace(0, 20 * np.pi, 500))) * 800 + 100
        df = pd.DataFrame({
            "timestamp": times,
            "activepower": power,
            "poa": irr,
        })
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = df
        MockRepo.return_value = mock_repo

        from services.analysis.shading import ShadingEngine
        engine = ShadingEngine()
        result = engine.run("p1", datetime(2025, 1, 1), datetime(2025, 3, 1))

        assert "shading_ratio" in result.summary
        assert "shading" in result.losses


# ---------------------------------------------------------------------------
# ThermalLossEngine
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestThermalLossEngine:
    @patch("services.analysis.thermal.ReadingsRepository")
    def test_no_readings(self, MockRepo):
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = pd.DataFrame()
        MockRepo.return_value = mock_repo

        from services.analysis.thermal import ThermalLossEngine
        engine = ThermalLossEngine()
        result = engine.run("p1", datetime(2025, 1, 1), datetime(2025, 1, 31))

        assert result.analysis_type == "thermal"
        assert len(result.warnings) > 0

    @patch("services.analysis.thermal.ReadingsRepository")
    def test_with_data(self, MockRepo):
        times = pd.date_range("2025-01-01", periods=100, freq="15min")
        module = np.random.uniform(30, 55, 100)
        ambient = np.random.uniform(20, 30, 100)
        df = pd.DataFrame({
            "timestamp": times,
            "moduletemperature": module,
            "ambienttemperature": ambient,
        })
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = df
        MockRepo.return_value = mock_repo

        from services.analysis.thermal import ThermalLossEngine
        engine = ThermalLossEngine()
        result = engine.run("p1", datetime(2025, 1, 1), datetime(2025, 1, 31))

        assert "estimated_thermal_loss_pct" in result.summary
        assert "thermal" in result.losses
        assert result.losses["thermal"] > 0


# ---------------------------------------------------------------------------
# CurtailmentEngine
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestCurtailmentEngine:
    @patch("services.analysis.curtailment.ReadingsRepository")
    def test_no_readings(self, MockRepo):
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = pd.DataFrame()
        MockRepo.return_value = mock_repo

        from services.analysis.curtailment import CurtailmentEngine
        engine = CurtailmentEngine()
        result = engine.run("p1", datetime(2025, 1, 1), datetime(2025, 1, 31))

        assert result.analysis_type == "curtailment"
        assert len(result.warnings) > 0

    @patch("services.analysis.curtailment.ReadingsRepository")
    def test_with_export_limit(self, MockRepo):
        times = pd.date_range("2025-01-01", periods=100, freq="15min")
        limits = [100.0] * 80 + [50.0] * 20  # 20% curtailed
        df = pd.DataFrame({
            "timestamp": times,
            "export_limit": limits,
        })
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = df
        MockRepo.return_value = mock_repo

        from services.analysis.curtailment import CurtailmentEngine
        engine = CurtailmentEngine()
        result = engine.run("p1", datetime(2025, 1, 1), datetime(2025, 1, 31))

        assert "curtailment_rate_pct" in result.summary
        assert "curtailment" in result.losses


# ---------------------------------------------------------------------------
# FoulingEngine
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestFoulingEngine:
    @patch("services.analysis.fouling.ReadingsRepository")
    def test_no_readings(self, MockRepo):
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = pd.DataFrame()
        MockRepo.return_value = mock_repo

        from services.analysis.fouling import FoulingEngine
        engine = FoulingEngine()
        result = engine.run("p1", datetime(2025, 1, 1), datetime(2025, 4, 1))

        assert result.analysis_type == "fouling"
        assert len(result.warnings) > 0

    @patch("services.analysis.fouling.ReadingsRepository")
    def test_with_data(self, MockRepo):
        # 60 days of data with declining performance
        times = pd.date_range("2025-01-01", periods=60 * 96, freq="15min")
        power = np.tile(np.abs(np.sin(np.linspace(0, np.pi, 96))) * 100, 60)
        # Add daily degradation
        daily_factor = np.repeat(np.linspace(1.0, 0.90, 60), 96)
        power = power * daily_factor
        irr = np.tile(np.abs(np.sin(np.linspace(0, np.pi, 96))) * 800 + 100, 60)
        df = pd.DataFrame({
            "timestamp": times,
            "activepower": power,
            "poa": irr,
        })
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = df
        MockRepo.return_value = mock_repo

        from services.analysis.fouling import FoulingEngine
        engine = FoulingEngine()
        result = engine.run("p1", datetime(2025, 1, 1), datetime(2025, 4, 1))

        assert "estimated_fouling_loss_pct" in result.summary
        assert "fouling" in result.losses


# ---------------------------------------------------------------------------
# LossWaterfallEngine
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestLossWaterfallEngine:
    @patch("services.analysis.waterfall.ThermalLossEngine")
    @patch("services.analysis.waterfall.FoulingEngine")
    @patch("services.analysis.waterfall.ShadingEngine")
    @patch("services.analysis.waterfall.CurtailmentEngine")
    @patch("services.analysis.waterfall.ClippingEngine")
    def test_aggregates_losses(self, MockClip, MockCurt, MockShad, MockFoul, MockTherm):
        from services.analysis.base import AnalysisResult

        start = datetime(2025, 1, 1)
        end = datetime(2025, 1, 31)

        def make_result(analysis_type, losses):
            return AnalysisResult(
                analysis_type=analysis_type,
                plant_uid="p1",
                start=start, end=end,
                losses=losses,
            )

        MockClip.return_value.run.return_value = make_result("clipping", {"clipping": 2.0})
        MockCurt.return_value.run.return_value = make_result("curtailment", {"curtailment": 1.5})
        MockShad.return_value.run.return_value = make_result("shading", {"shading": 3.0})
        MockFoul.return_value.run.return_value = make_result("fouling", {"fouling": 1.0})
        MockTherm.return_value.run.return_value = make_result("thermal", {"thermal": 4.0})

        from services.analysis.waterfall import LossWaterfallEngine
        engine = LossWaterfallEngine()
        result = engine.run("p1", start, end)

        assert result.analysis_type == "loss_waterfall"
        assert result.summary["total_estimated_loss_pct"] == 11.5
        assert result.losses["clipping"] == 2.0
        assert result.losses["thermal"] == 4.0
        assert not result.table.empty

    @patch("services.analysis.waterfall.ThermalLossEngine")
    @patch("services.analysis.waterfall.FoulingEngine")
    @patch("services.analysis.waterfall.ShadingEngine")
    @patch("services.analysis.waterfall.CurtailmentEngine")
    @patch("services.analysis.waterfall.ClippingEngine")
    def test_collects_warnings(self, MockClip, MockCurt, MockShad, MockFoul, MockTherm):
        from services.analysis.base import AnalysisResult
        start = datetime(2025, 1, 1)
        end = datetime(2025, 1, 31)

        def make_result(analysis_type, warnings):
            return AnalysisResult(
                analysis_type=analysis_type,
                plant_uid="p1",
                start=start, end=end,
                warnings=warnings,
            )

        MockClip.return_value.run.return_value = make_result("clipping", ["warn1"])
        MockCurt.return_value.run.return_value = make_result("curtailment", [])
        MockShad.return_value.run.return_value = make_result("shading", ["warn2"])
        MockFoul.return_value.run.return_value = make_result("fouling", [])
        MockTherm.return_value.run.return_value = make_result("thermal", [])

        from services.analysis.waterfall import LossWaterfallEngine
        engine = LossWaterfallEngine()
        result = engine.run("p1", start, end)

        assert "warn1" in result.warnings
        assert "warn2" in result.warnings


# ---------------------------------------------------------------------------
# PRTrendingEngine
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestPRTrendingEngine:
    @patch("services.analysis.pr_trending.ReadingsRepository")
    def test_no_readings(self, MockRepo):
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = pd.DataFrame()
        MockRepo.return_value = mock_repo

        from services.analysis.pr_trending import PRTrendingEngine
        engine = PRTrendingEngine()
        result = engine.run("p1", datetime(2025, 1, 1), datetime(2025, 5, 1))

        assert result.analysis_type == "pr_trending"
        assert len(result.warnings) > 0

    @patch("services.analysis.pr_trending.ReadingsRepository")
    def test_with_pr_data(self, MockRepo):
        times = pd.date_range("2025-01-01", periods=30 * 24, freq="h")
        pr = np.random.uniform(78, 88, 30 * 24)
        df = pd.DataFrame({
            "timestamp": times,
            "performance_ratio": pr,
        })
        mock_repo = MagicMock()
        mock_repo.get_readings.return_value = df
        MockRepo.return_value = mock_repo

        from services.analysis.pr_trending import PRTrendingEngine
        engine = PRTrendingEngine()
        result = engine.run("p1", datetime(2025, 1, 1), datetime(2025, 5, 1))

        assert "mean_pr_pct" in result.summary
        assert result.timeseries is not None
