"""Fouling/soiling analysis engine."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import pandas as pd

from solar_platform.analysis.base import AnalysisEngine, AnalysisResult
from solar_platform.analysis.helpers import (
    coerce_datetime,
    date_bounds_or_default,
    detect_time_column,
    find_numeric_column,
    normalized_ratio,
)
from solar_platform.db.engine import DatabaseEngine
from solar_platform.db.repository import ReadingsRepository


class FoulingEngine(AnalysisEngine):
    """Estimate fouling from normalized daily energy trend."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self._readings = ReadingsRepository(engine=engine)

    @property
    def analysis_type(self) -> str:
        return "fouling"

    def run(self, plant_uid: str, start: datetime | None, end: datetime | None, **params: Any) -> AnalysisResult:
        t0 = time.perf_counter()
        start, end = date_bounds_or_default(start, end, days=90)
        df = self._readings.get_readings(plant_uid, start=start, end=end)
        if df.empty:
            return AnalysisResult(self.analysis_type, plant_uid, start, end, warnings=["No readings available."])

        ts_col = detect_time_column(df)
        power_col = find_numeric_column(df, ["activepower", "power", "pac", "kw"])
        irr_col = find_numeric_column(df, ["poa", "irradiance", "gti", "ghi"])

        if not ts_col or not power_col or not irr_col:
            return AnalysisResult(self.analysis_type, plant_uid, start, end, warnings=["Need timestamp, power, and irradiance columns."])

        df = coerce_datetime(df, ts_col)
        df["date"] = df[ts_col].dt.date
        df["norm_ratio"] = normalized_ratio(df[power_col], df[irr_col])

        daily = df.groupby("date", as_index=False)["norm_ratio"].median()
        daily = daily.dropna(subset=["norm_ratio"])
        if daily.empty:
            return AnalysisResult(self.analysis_type, plant_uid, start, end, warnings=["Could not compute normalized fouling ratio."])

        baseline_series = daily["norm_ratio"].rolling(14, min_periods=3).max().dropna()
        baseline = float(baseline_series.iloc[-1]) if not baseline_series.empty else float(daily["norm_ratio"].max())
        current = float(daily["norm_ratio"].tail(1).squeeze())
        fouling_loss_pct = max(0.0, min((1.0 - (current / baseline if baseline else 1.0)) * 100.0, 100.0))

        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid,
            start=start,
            end=end,
            summary={
                "days_analyzed": int(len(daily)),
                "baseline_ratio": round(baseline, 4),
                "current_ratio": round(current, 4),
                "estimated_fouling_loss_pct": round(fouling_loss_pct, 2),
            },
            timeseries=daily,
            losses={"fouling": round(fouling_loss_pct, 2)},
            calculation_seconds=round(time.perf_counter() - t0, 3),
        )
