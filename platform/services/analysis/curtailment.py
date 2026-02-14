"""Curtailment analysis engine."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import pandas as pd

from services.analysis.base import AnalysisEngine, AnalysisResult
from services.analysis.helpers import coerce_datetime, date_bounds_or_default, detect_time_column, find_numeric_column
from services.database.engine import DatabaseEngine
from services.database.repository import ReadingsRepository


class CurtailmentEngine(AnalysisEngine):
    """Estimate curtailment from export-limit style telemetry fields."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self._readings = ReadingsRepository(engine=engine)

    @property
    def analysis_type(self) -> str:
        return "curtailment"

    def run(self, plant_uid: str, start: datetime | None, end: datetime | None, **params: Any) -> AnalysisResult:
        t0 = time.perf_counter()
        start, end = date_bounds_or_default(start, end, days=30)
        df = self._readings.get_readings(plant_uid, start=start, end=end)
        if df.empty:
            return AnalysisResult(self.analysis_type, plant_uid, start, end, warnings=["No readings available."])

        ts_col = detect_time_column(df)
        if not ts_col:
            return AnalysisResult(self.analysis_type, plant_uid, start, end, warnings=["Timestamp column missing."])
        df = coerce_datetime(df, ts_col)

        limit_col = find_numeric_column(df, ["export_limit", "limit_pct", "curtailment"])
        power_col = find_numeric_column(df, ["activepower", "power", "pac", "p_grid", "kw"])

        if limit_col:
            limit_pct = pd.to_numeric(df[limit_col], errors="coerce")
            curtailed = limit_pct < params.get("limit_threshold_pct", 99)
        elif power_col:
            power = pd.to_numeric(df[power_col], errors="coerce")
            threshold = float(power.quantile(0.2))
            curtailed = power <= threshold
        else:
            return AnalysisResult(self.analysis_type, plant_uid, start, end, warnings=["No curtailment-relevant columns found."])

        curtailment_rate = float(curtailed.mean() * 100.0)
        out = df[[ts_col]].copy()
        out["is_curtailed"] = curtailed.astype(bool)

        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid,
            start=start,
            end=end,
            summary={
                "records": int(len(df)),
                "curtailed_records": int(curtailed.sum()),
                "curtailment_rate_pct": round(curtailment_rate, 2),
            },
            timeseries=out,
            losses={"curtailment": round(curtailment_rate, 2)},
            calculation_seconds=round(time.perf_counter() - t0, 3),
        )
