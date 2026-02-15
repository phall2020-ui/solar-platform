"""Unit tests for gap detection."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pandas as pd


@pytest.mark.unit
class TestGapSeverity:
    def test_short_value(self):
        from solar_platform.data_quality.gap_detection import GapSeverity
        assert GapSeverity.SHORT == "short"

    def test_medium_value(self):
        from solar_platform.data_quality.gap_detection import GapSeverity
        assert GapSeverity.MEDIUM == "medium"

    def test_long_value(self):
        from solar_platform.data_quality.gap_detection import GapSeverity
        assert GapSeverity.LONG == "long"


@pytest.mark.unit
class TestClassify:
    def test_short_gap(self):
        from solar_platform.data_quality.gap_detection import _classify, GapSeverity
        assert _classify(30) == GapSeverity.SHORT

    def test_medium_gap(self):
        from solar_platform.data_quality.gap_detection import _classify, GapSeverity
        assert _classify(120) == GapSeverity.MEDIUM

    def test_long_gap(self):
        from solar_platform.data_quality.gap_detection import _classify, GapSeverity
        assert _classify(25 * 60) == GapSeverity.LONG

    def test_boundary_60_is_medium(self):
        from solar_platform.data_quality.gap_detection import _classify, GapSeverity
        assert _classify(60) == GapSeverity.MEDIUM

    def test_boundary_1440_is_long(self):
        from solar_platform.data_quality.gap_detection import _classify, GapSeverity
        assert _classify(24 * 60) == GapSeverity.LONG


@pytest.mark.unit
class TestDataGap:
    def test_duration_property(self):
        from solar_platform.data_quality.gap_detection import DataGap, GapSeverity
        start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 1, 2, 0, tzinfo=timezone.utc)
        gap = DataGap(
            plant_uid="p1",
            start=start,
            end=end,
            severity=GapSeverity.MEDIUM,
            duration_minutes=120.0,
            expected_readings=8,
        )
        assert gap.duration == timedelta(hours=2)


@pytest.mark.unit
class TestGapDetector:
    @patch("solar_platform.data_quality.gap_detection.get_engine")
    def test_detect_gaps_no_readings_table(self, mock_get_engine):
        # Arrange
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = False
        mock_get_engine.return_value = mock_engine

        from solar_platform.data_quality.gap_detection import GapDetector
        detector = GapDetector()

        # Act
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)
        gaps = detector.detect_gaps("plant1", start, end)

        # Assert
        assert gaps == []

    @patch("solar_platform.data_quality.gap_detection.get_engine")
    def test_detect_gaps_empty_result_entire_window_is_gap(self, mock_get_engine):
        # Arrange
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        mock_engine.execute_df.return_value = pd.DataFrame()
        mock_get_engine.return_value = mock_engine

        from solar_platform.data_quality.gap_detection import GapDetector
        detector = GapDetector()

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        # Act
        gaps = detector.detect_gaps("plant1", start, end)

        # Assert
        assert len(gaps) == 1
        assert gaps[0].plant_uid == "plant1"
        assert gaps[0].start == start
        assert gaps[0].end == end

    @patch("solar_platform.data_quality.gap_detection.get_engine")
    def test_detect_gaps_inter_reading_gap(self, mock_get_engine):
        # Arrange
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 1, 6, 0, tzinfo=timezone.utc)
        # Two readings with a 3-hour gap in between (much more than 15m * 1.5)
        timestamps = [
            start + timedelta(minutes=15),
            start + timedelta(hours=4),
        ]
        mock_engine.execute_df.return_value = pd.DataFrame({"timestamp": timestamps})
        mock_get_engine.return_value = mock_engine

        from solar_platform.data_quality.gap_detection import GapDetector
        detector = GapDetector()

        # Act
        gaps = detector.detect_gaps("plant1", start, end)

        # Assert — should detect the inter-reading gap at minimum
        assert len(gaps) >= 1

    @patch("solar_platform.data_quality.gap_detection.get_engine")
    def test_daily_completeness_no_table(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = False
        mock_get_engine.return_value = mock_engine

        from solar_platform.data_quality.gap_detection import GapDetector
        detector = GapDetector()

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        # Act
        df = detector.daily_completeness("plant1", start, end)

        # Assert
        assert df.empty
        assert "completeness_pct" in df.columns

    @patch("solar_platform.data_quality.gap_detection.get_engine")
    def test_daily_completeness_with_data(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        mock_engine.execute_df.return_value = pd.DataFrame({
            "date": [datetime(2025, 1, 1).date()],
            "actual": [48],
        })
        mock_get_engine.return_value = mock_engine

        from solar_platform.data_quality.gap_detection import GapDetector
        detector = GapDetector()

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        # Act
        df = detector.daily_completeness("plant1", start, end)

        # Assert
        assert not df.empty
        assert "completeness_pct" in df.columns
        assert df.iloc[0]["expected"] == 96  # 24*60/15
