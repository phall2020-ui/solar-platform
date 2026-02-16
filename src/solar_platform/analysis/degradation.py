"""Long-term degradation analysis engine."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import numpy as np
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


class DegradationEngine(AnalysisEngine):
    """Estimate annualized PR degradation slope."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self._readings = ReadingsRepository(engine=engine)

    @property
    def analysis_type(self) -> str:
        return "degradation"

    def run(self, plant_uid: str, start: datetime | None, end: datetime | None, **params: Any) -> AnalysisResult:
        t0 = time.perf_counter()
        start, end = date_bounds_or_default(start, end, days=365)

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

        monthly = (
            df.assign(month=df[ts_col].dt.to_period("M").dt.to_timestamp())
            .groupby("month", as_index=False)[pr_col]
            .median()
            .rename(columns={pr_col: "pr_pct"})
        )

        if len(monthly) < 3:
            return AnalysisResult(
                self.analysis_type,
                plant_uid,
                start,
                end,
                timeseries=monthly,
                warnings=["At least 3 months of data are required for degradation estimation."],
            )

        x = np.arange(len(monthly), dtype=float)
        y = monthly["pr_pct"].astype(float).to_numpy()
        slope, intercept = np.polyfit(x, y, 1)
        monthly["trend_pr_pct"] = intercept + slope * x

        annualized_pct = float(slope * 12)

        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid,
            start=start,
            end=end,
            summary={
                "months_analyzed": int(len(monthly)),
                "annualized_pr_change_pct": round(annualized_pct, 3),
                "degradation_detected": bool(annualized_pct < 0),
            },
            timeseries=monthly,
            calculation_seconds=round(time.perf_counter() - t0, 3),
        )
