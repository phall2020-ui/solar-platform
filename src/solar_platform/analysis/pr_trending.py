"""Performance-ratio trending engine."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import pandas as pd

from solar_platform.analysis.base import AnalysisEngine, AnalysisResult
from solar_platform.analysis.helpers import (
    IRRADIANCE_KEYWORDS,
    POWER_KEYWORDS,
    coerce_datetime,
    date_bounds_or_default,
    detect_time_column,
    find_numeric_column,
    merge_power_and_irradiance,
    normalized_ratio,
)
from solar_platform.db.engine import DatabaseEngine
from solar_platform.db.repository import ReadingsRepository


class PRTrendingEngine(AnalysisEngine):
    """Compute daily PR trends and rolling averages."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self._readings = ReadingsRepository(engine=engine)

    @property
    def analysis_type(self) -> str:
        return "pr_trending"

    def run(self, plant_uid: str, start: datetime | None, end: datetime | None, **params: Any) -> AnalysisResult:
        t0 = time.perf_counter()
        start, end = date_bounds_or_default(start, end, days=120)
        window = int(params.get("rolling_window_days", 7))

        df = self._readings.get_readings(plant_uid, start=start, end=end)
        if df.empty:
            return AnalysisResult(self.analysis_type, plant_uid, start, end, warnings=["No readings available."])

        ts_col = detect_time_column(df)
        # Merge weather irradiance onto inverter rows
        df = merge_power_and_irradiance(df, ts_col)

        pr_col = find_numeric_column(df, ["performance_ratio", "pr"])
        power_col = find_numeric_column(df, POWER_KEYWORDS)
        irr_col = find_numeric_column(df, IRRADIANCE_KEYWORDS)

        if not ts_col:
            return AnalysisResult(self.analysis_type, plant_uid, start, end, warnings=["Timestamp column missing."])

        df = coerce_datetime(df, ts_col)
        if not pr_col and power_col and irr_col:
            df["derived_pr"] = normalized_ratio(df[power_col], df[irr_col]) * 100.0
            pr_col = "derived_pr"

        if not pr_col:
            return AnalysisResult(self.analysis_type, plant_uid, start, end, warnings=["Could not derive PR series."])

        daily = (
            df.assign(date=df[ts_col].dt.date)
            .groupby("date", as_index=False)[pr_col]
            .median()
            .rename(columns={pr_col: "pr_pct"})
        )
        daily["rolling_pr_pct"] = daily["pr_pct"].rolling(window, min_periods=2).mean()
        daily["trend_delta_pct"] = daily["rolling_pr_pct"].diff()

        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid,
            start=start,
            end=end,
            summary={
                "days": int(len(daily)),
                "mean_pr_pct": round(float(daily["pr_pct"].mean()), 2),
                "latest_pr_pct": round(float(daily["pr_pct"].iloc[-1]), 2) if not daily.empty else None,
                "latest_rolling_pr_pct": round(float(daily["rolling_pr_pct"].iloc[-1]), 2)
                if daily["rolling_pr_pct"].notna().any()
                else None,
            },
            timeseries=daily,
            calculation_seconds=round(time.perf_counter() - t0, 3),
        )
