"""Tests for Phase 3 analysis engines."""

from __future__ import annotations

from datetime import datetime

from solar_platform.analysis import (
    ClippingEngine,
    ComparativeEngine,
    CurtailmentEngine,
    DegradationEngine,
    FoulingEngine,
    LossWaterfallEngine,
    PRTrendingEngine,
    ShadingEngine,
    ThermalLossEngine,
)


def _window() -> tuple[datetime, datetime]:
    return datetime(2025, 12, 31), datetime(2026, 1, 2)


def test_comparative_engine_runs_on_seeded_engine(seeded_engine):
    start, end = _window()
    result = ComparativeEngine(engine=seeded_engine).run(start=start, end=end)
    assert result.table is not None
    assert "plant_name" in result.table.columns
    assert result.summary["plants_compared"] >= 1


def test_individual_engines_return_summary(seeded_engine):
    start, end = _window()
    plant_uid = "uid-001"

    engines = [
        ClippingEngine(engine=seeded_engine),
        CurtailmentEngine(engine=seeded_engine),
        ShadingEngine(engine=seeded_engine),
        FoulingEngine(engine=seeded_engine),
        ThermalLossEngine(engine=seeded_engine),
        PRTrendingEngine(engine=seeded_engine),
        DegradationEngine(engine=seeded_engine),
        LossWaterfallEngine(engine=seeded_engine),
    ]

    for engine in engines:
        result = engine.run(plant_uid=plant_uid, start=start, end=end)
        assert result.analysis_type
        assert result.start <= result.end
        assert isinstance(result.summary, dict)
