"""Tests for framework-agnostic analysis result and engine contracts."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from services.analysis.base import AnalysisResult


def test_analysis_result_has_data_from_summary():
    result = AnalysisResult(
        analysis_type="test",
        plant_uid="plant-001",
        start=datetime(2026, 1, 1),
        end=datetime(2026, 1, 2),
        summary={"pr": 82.5},
    )
    assert result.has_data is True


def test_analysis_result_has_data_from_table():
    result = AnalysisResult(
        analysis_type="test",
        plant_uid="plant-001",
        start=datetime(2026, 1, 1),
        end=datetime(2026, 1, 2),
        table=pd.DataFrame([{"metric": "pr", "value": 82.5}]),
    )
    assert result.has_data is True


def test_analysis_result_no_data():
    result = AnalysisResult(
        analysis_type="test",
        plant_uid="plant-001",
        start=datetime(2026, 1, 1),
        end=datetime(2026, 1, 2),
    )
    assert result.has_data is False
