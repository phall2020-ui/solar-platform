"""Unit tests for quality scoring."""
import pytest
from unittest.mock import patch, MagicMock

import pandas as pd


@pytest.mark.unit
class TestQualityScorer:
    @patch("services.data_quality.quality_scorer.run_validation")
    @patch("services.data_quality.quality_scorer.SOURCE_PRIORITY", {"scada": 10, "manual": 4, "unknown": 1})
    def test_score_reading_perfect(self, mock_run_validation):
        """A perfect reading (all fields present, no errors, SCADA source) scores high."""
        from solar_platform.data_quality.validators import ValidationReport
        mock_report = ValidationReport()
        mock_report.total_checked = 1
        mock_run_validation.return_value = mock_report

        from solar_platform.data_quality.quality_scorer import QualityScorer
        scorer = QualityScorer()

        reading = {
            "power_kw": 100.0,
            "energy_kwh": 25.0,
            "poa_wm2": 800.0,
            "ambient_temp_c": 25.0,
            "source": "scada",
        }
        score = scorer.score_reading(reading, {"capacity_kw": 5000})
        assert score >= 90.0

    @patch("services.data_quality.quality_scorer.run_validation")
    @patch("services.data_quality.quality_scorer.SOURCE_PRIORITY", {"scada": 10, "manual": 4, "unknown": 1})
    def test_score_reading_missing_fields(self, mock_run_validation):
        """Missing key fields reduce completeness sub-score."""
        from solar_platform.data_quality.validators import ValidationReport
        mock_report = ValidationReport()
        mock_run_validation.return_value = mock_report

        from solar_platform.data_quality.quality_scorer import QualityScorer
        scorer = QualityScorer()

        reading = {"power_kw": 100.0, "source": "scada"}  # Only 1 of 4 key fields
        score = scorer.score_reading(reading, {})
        assert score < 100.0

    @patch("services.data_quality.quality_scorer.run_validation")
    @patch("services.data_quality.quality_scorer.SOURCE_PRIORITY", {"scada": 10, "estimated": 2, "unknown": 1})
    def test_score_reading_low_source_priority(self, mock_run_validation):
        """Low-priority source reduces source sub-score."""
        from solar_platform.data_quality.validators import ValidationReport
        mock_report = ValidationReport()
        mock_run_validation.return_value = mock_report

        from solar_platform.data_quality.quality_scorer import QualityScorer
        scorer = QualityScorer()

        reading = {
            "power_kw": 100.0,
            "energy_kwh": 25.0,
            "poa_wm2": 800.0,
            "ambient_temp_c": 25.0,
            "source": "estimated",
        }
        score_low = scorer.score_reading(reading, {})

        reading["source"] = "scada"
        score_high = scorer.score_reading(reading, {})

        assert score_high > score_low

    @patch("services.data_quality.quality_scorer.run_validation")
    @patch("services.data_quality.quality_scorer.SOURCE_PRIORITY", {"scada": 10})
    def test_score_reading_clamped_to_0_100(self, mock_run_validation):
        from solar_platform.data_quality.validators import ValidationReport
        mock_report = ValidationReport()
        mock_run_validation.return_value = mock_report

        from solar_platform.data_quality.quality_scorer import QualityScorer
        scorer = QualityScorer()

        reading = {"power_kw": 100.0, "source": "scada"}
        score = scorer.score_reading(reading, {})
        assert 0.0 <= score <= 100.0

    @patch("services.data_quality.quality_scorer.run_validation")
    @patch("services.data_quality.quality_scorer.SOURCE_PRIORITY", {"scada": 10})
    def test_score_batch(self, mock_run_validation):
        from solar_platform.data_quality.validators import ValidationReport
        mock_report = ValidationReport()
        mock_run_validation.return_value = mock_report

        from solar_platform.data_quality.quality_scorer import QualityScorer
        scorer = QualityScorer()

        df = pd.DataFrame({
            "power_kw": [100.0, 200.0],
            "energy_kwh": [25.0, 50.0],
            "poa_wm2": [800.0, 900.0],
            "ambient_temp_c": [25.0, 30.0],
            "source": ["scada", "scada"],
        })
        result = scorer.score_batch(df, {"capacity_kw": 5000})
        assert "quality_score" in result.columns
        assert len(result) == 2

    def test_completeness_score_all_present(self):
        from solar_platform.data_quality.quality_scorer import QualityScorer
        scorer = QualityScorer()
        reading = {
            "power_kw": 100.0,
            "energy_kwh": 25.0,
            "poa_wm2": 800.0,
            "ambient_temp_c": 25.0,
        }
        assert scorer._completeness_score(reading) == 1.0

    def test_completeness_score_none_present(self):
        from solar_platform.data_quality.quality_scorer import QualityScorer
        scorer = QualityScorer()
        reading = {}
        assert scorer._completeness_score(reading) == 0.0

    def test_completeness_score_partial(self):
        from solar_platform.data_quality.quality_scorer import QualityScorer
        scorer = QualityScorer()
        reading = {"power_kw": 100.0, "energy_kwh": 25.0}
        assert scorer._completeness_score(reading) == 0.5

    def test_source_score_empty(self):
        from solar_platform.data_quality.quality_scorer import QualityScorer
        score = QualityScorer._source_score({})
        assert score == 0.5

    def test_source_score_no_source_key(self):
        from solar_platform.data_quality.quality_scorer import QualityScorer
        score = QualityScorer._source_score({"power_kw": 100})
        assert score == 0.5
