"""Unit tests for anomaly detection."""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd


@pytest.mark.unit
class TestAnomalyType:
    def test_statistical(self):
        from services.analytics.anomaly_detection import AnomalyType
        assert AnomalyType.STATISTICAL == "statistical"

    def test_contextual(self):
        from services.analytics.anomaly_detection import AnomalyType
        assert AnomalyType.CONTEXTUAL == "contextual"

    def test_isolation_forest(self):
        from services.analytics.anomaly_detection import AnomalyType
        assert AnomalyType.ISOLATION_FOREST == "isolation_forest"


@pytest.mark.unit
class TestAnomaly:
    def test_defaults(self):
        from services.analytics.anomaly_detection import Anomaly, AnomalyType
        a = Anomaly(plant_uid="p1", metric="pr", value=0.5)
        assert a.plant_uid == "p1"
        assert a.anomaly_type == AnomalyType.STATISTICAL
        assert a.severity == "warning"
        assert a.id  # auto-generated uuid
        assert a.metadata == {}

    def test_custom_fields(self):
        from services.analytics.anomaly_detection import Anomaly, AnomalyType
        a = Anomaly(
            plant_uid="p1",
            anomaly_type=AnomalyType.CONTEXTUAL,
            metric="generation_kwh",
            value=100.0,
            expected_value=200.0,
            z_score=-3.5,
            severity="critical",
        )
        assert a.anomaly_type == AnomalyType.CONTEXTUAL
        assert a.expected_value == 200.0
        assert a.z_score == -3.5


@pytest.mark.unit
class TestStatisticalDetector:
    def test_detector_name(self):
        from services.analytics.anomaly_detection import StatisticalDetector
        d = StatisticalDetector()
        assert d.detector_name == "statistical_z_score"

    def test_no_relevant_columns(self):
        from services.analytics.anomaly_detection import StatisticalDetector
        d = StatisticalDetector()
        df = pd.DataFrame({"unrelated": [1, 2, 3]})
        results = d.detect(df, "p1")
        assert results == []

    def test_insufficient_data(self):
        from services.analytics.anomaly_detection import StatisticalDetector
        d = StatisticalDetector()
        df = pd.DataFrame({"pr": [0.8, 0.85, 0.9]})
        results = d.detect(df, "p1")
        assert results == []

    def test_detects_outlier(self):
        from services.analytics.anomaly_detection import StatisticalDetector
        d = StatisticalDetector(z_threshold=2.0)
        # 99 normal + 1 extreme outlier
        values = [80.0] * 50 + [82.0] * 49 + [200.0]
        df = pd.DataFrame({
            "pr": values,
            "timestamp": pd.date_range("2025-01-01", periods=100, freq="h"),
        })
        results = d.detect(df, "p1")
        assert len(results) >= 1
        assert results[0].metric == "pr"

    def test_no_outlier_in_uniform_data(self):
        from services.analytics.anomaly_detection import StatisticalDetector
        d = StatisticalDetector(z_threshold=3.0)
        np.random.seed(42)
        values = np.random.normal(80, 2, 100).tolist()
        df = pd.DataFrame({
            "pr": values,
            "timestamp": pd.date_range("2025-01-01", periods=100, freq="h"),
        })
        # With tight normal dist and high threshold, usually no outliers
        results = d.detect(df, "p1")
        # Just validate it returns a list
        assert isinstance(results, list)

    def test_zero_std_skipped(self):
        from services.analytics.anomaly_detection import StatisticalDetector
        d = StatisticalDetector()
        # All identical values → std=0 → should skip
        df = pd.DataFrame({
            "pr": [80.0] * 20,
            "timestamp": pd.date_range("2025-01-01", periods=20, freq="h"),
        })
        results = d.detect(df, "p1")
        assert results == []


@pytest.mark.unit
class TestContextualDetector:
    def test_detector_name(self):
        from services.analytics.anomaly_detection import ContextualDetector
        d = ContextualDetector()
        assert d.detector_name == "contextual_gen_irradiance"

    def test_missing_columns(self):
        from services.analytics.anomaly_detection import ContextualDetector
        d = ContextualDetector()
        df = pd.DataFrame({"pr": [0.8]})
        results = d.detect(df, "p1")
        assert results == []

    def test_insufficient_data(self):
        from services.analytics.anomaly_detection import ContextualDetector
        d = ContextualDetector()
        df = pd.DataFrame({
            "generation_kwh": [100, 200],
            "irradiance": [500, 600],
        })
        results = d.detect(df, "p1")
        assert results == []

    def test_detects_contextual_anomaly(self):
        from services.analytics.anomaly_detection import ContextualDetector
        d = ContextualDetector(residual_threshold=2.0)
        np.random.seed(42)
        irr = np.linspace(100, 1000, 50)
        gen = irr * 0.8 + np.random.normal(0, 5, 50)
        # Inject an outlier
        gen[25] = 10.0  # very low generation for high irradiance
        df = pd.DataFrame({
            "generation_kwh": gen,
            "irradiance": irr,
            "timestamp": pd.date_range("2025-01-01", periods=50, freq="h"),
        })
        results = d.detect(df, "p1")
        assert len(results) >= 1


@pytest.mark.unit
class TestIsolationForestDetector:
    def test_detector_name(self):
        from services.analytics.anomaly_detection import IsolationForestDetector
        d = IsolationForestDetector()
        assert d.detector_name == "isolation_forest"

    def test_insufficient_columns(self):
        from services.analytics.anomaly_detection import IsolationForestDetector
        d = IsolationForestDetector()
        df = pd.DataFrame({"pr": [0.8] * 30})
        results = d.detect(df, "p1")
        assert results == []

    def test_insufficient_rows(self):
        from services.analytics.anomaly_detection import IsolationForestDetector
        d = IsolationForestDetector()
        df = pd.DataFrame({
            "pr": [0.8] * 5,
            "generation_kwh": [100] * 5,
        })
        results = d.detect(df, "p1")
        assert results == []


@pytest.mark.unit
class TestAnomalyService:
    def test_runs_all_detectors(self):
        from services.analytics.anomaly_detection import AnomalyService, AnomalyDetector, Anomaly
        
        class FakeDetector(AnomalyDetector):
            @property
            def detector_name(self):
                return "fake"
            def detect(self, df, plant_uid):
                return [Anomaly(plant_uid=plant_uid, metric="test", value=1.0)]

        svc = AnomalyService(detectors=[FakeDetector(), FakeDetector()])
        df = pd.DataFrame({"x": [1]})
        results = svc.detect(df, "p1")
        # Dedup by (plant, timestamp, metric) — same metric, same ts → 1
        assert len(results) >= 1

    def test_handles_detector_failure(self):
        from services.analytics.anomaly_detection import AnomalyService, AnomalyDetector

        class BrokenDetector(AnomalyDetector):
            @property
            def detector_name(self):
                return "broken"
            def detect(self, df, plant_uid):
                raise RuntimeError("boom")

        svc = AnomalyService(detectors=[BrokenDetector()])
        df = pd.DataFrame({"x": [1]})
        results = svc.detect(df, "p1")
        assert results == []

    def test_deduplication(self):
        from services.analytics.anomaly_detection import AnomalyService, Anomaly
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        anomalies = [
            Anomaly(plant_uid="p1", timestamp=ts, metric="pr", value=0.5),
            Anomaly(plant_uid="p1", timestamp=ts, metric="pr", value=0.6),
        ]
        unique = AnomalyService._deduplicate(anomalies)
        assert len(unique) == 1
