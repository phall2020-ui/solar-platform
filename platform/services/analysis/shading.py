"""Shading analysis engine."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import pandas as pd

from services.analysis.base import AnalysisEngine, AnalysisResult
from services.analysis.helpers import (
    coerce_datetime,
    date_bounds_or_default,
    detect_time_column,
    find_numeric_column,
    normalized_ratio,
)
from services.database.engine import DatabaseEngine
from services.database.repository import ReadingsRepository


class ShadingEngine(AnalysisEngine):
    """Estimate shading via hourly normalized performance profile."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self._readings = ReadingsRepository(engine=engine)

    @property
    def analysis_type(self) -> str:
        return "shading"

    def run(self, plant_uid: str, start: datetime | None, end: datetime | None, **params: Any) -> AnalysisResult:
        t0 = time.perf_counter()
        start, end = date_bounds_or_default(start, end, days=60)
        df = self._readings.get_readings(plant_uid, start=start, end=end)
        if df.empty:
            return AnalysisResult(self.analysis_type, plant_uid, start, end, warnings=["No readings available."])

        ts_col = detect_time_column(df)
        power_col = find_numeric_column(df, ["activepower", "power", "pac", "kw"])
        irr_col = find_numeric_column(df, ["poa", "irradiance", "gti", "ghi"])

        if not ts_col or not power_col or not irr_col:
            return AnalysisResult(self.analysis_type, plant_uid, start, end, warnings=["Need timestamp, power, and irradiance columns."])

        df = coerce_datetime(df, ts_col)
        df["hour"] = df[ts_col].dt.hour
        ratio = normalized_ratio(df[power_col], df[irr_col])
        df["norm_ratio"] = ratio

        hourly = df.groupby("hour", as_index=False)["norm_ratio"].median()
        midday = hourly[hourly["hour"].between(11, 14)]["norm_ratio"].median()
        shoulder = hourly[hourly["hour"].isin([8, 9, 15, 16])]["norm_ratio"].median()

        shading_ratio = float((shoulder / midday) if pd.notna(midday) and midday else 1.0)
        shading_loss_pct = max(0.0, min((1.0 - shading_ratio) * 100.0, 100.0))

        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid,
            start=start,
            end=end,
            summary={
                "hourly_points": int(len(hourly)),
                "shading_ratio": round(shading_ratio, 3),
                "estimated_shading_loss_pct": round(shading_loss_pct, 2),
            },
            table=hourly,
            losses={"shading": round(shading_loss_pct, 2)},
            calculation_seconds=round(time.perf_counter() - t0, 3),
        )
