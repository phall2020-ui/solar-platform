"""Thermal loss analysis engine."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import pandas as pd

from solar_platform.analysis.base import AnalysisEngine, AnalysisResult
from solar_platform.analysis.helpers import coerce_datetime, date_bounds_or_default, detect_time_column, find_numeric_column
from solar_platform.db.engine import DatabaseEngine
from solar_platform.db.repository import ReadingsRepository


class ThermalLossEngine(AnalysisEngine):
    """Estimate thermal loss using module/ambient temperature delta."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self._readings = ReadingsRepository(engine=engine)

    @property
    def analysis_type(self) -> str:
        return "thermal"

    def run(self, plant_uid: str, start: datetime | None, end: datetime | None, **params: Any) -> AnalysisResult:
        t0 = time.perf_counter()
        start, end = date_bounds_or_default(start, end, days=30)
        gamma_pct_per_c = float(params.get("gamma_pct_per_c", -0.4))

        df = self._readings.get_readings(plant_uid, start=start, end=end)
        if df.empty:
            return AnalysisResult(self.analysis_type, plant_uid, start, end, warnings=["No readings available."])

        ts_col = detect_time_column(df)
        module_col = find_numeric_column(df, ["moduletemperature", "module_temp", "cell_temp"])
        ambient_col = find_numeric_column(df, ["ambienttemperature", "ambient_temp", "air_temp"])

        if not ts_col or not module_col or not ambient_col:
            return AnalysisResult(
                self.analysis_type,
                plant_uid,
                start,
                end,
                warnings=["Need timestamp, module temperature, and ambient temperature columns."],
            )

        df = coerce_datetime(df, ts_col)
        module = pd.to_numeric(df[module_col], errors="coerce")
        ambient = pd.to_numeric(df[ambient_col], errors="coerce")

        temp_delta = module - ambient
        loss_fraction = (temp_delta * abs(gamma_pct_per_c) / 100.0).clip(lower=0)
        loss_pct = float(loss_fraction.mean() * 100.0)

        out = df[[ts_col]].copy()
        out["module_temp_c"] = module
        out["ambient_temp_c"] = ambient
        out["thermal_loss_pct"] = loss_fraction * 100.0

        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid,
            start=start,
            end=end,
            summary={
                "avg_module_temp_c": round(float(module.mean()), 2),
                "avg_ambient_temp_c": round(float(ambient.mean()), 2),
                "avg_delta_c": round(float(temp_delta.mean()), 2),
                "estimated_thermal_loss_pct": round(loss_pct, 2),
            },
            timeseries=out,
            losses={"thermal": round(loss_pct, 2)},
            calculation_seconds=round(time.perf_counter() - t0, 3),
        )
