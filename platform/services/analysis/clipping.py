"""Clipping analysis engine."""

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
    estimate_energy_kwh,
    find_numeric_column,
)
from services.database.engine import DatabaseEngine
from services.database.repository import ReadingsRepository


class ClippingEngine(AnalysisEngine):
    """Detect inverter clipping from power plateaus under high irradiance."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self._readings = ReadingsRepository(engine=engine)

    @property
    def analysis_type(self) -> str:
        return "clipping"

    def run(self, plant_uid: str, start: datetime | None, end: datetime | None, **params: Any) -> AnalysisResult:
        t0 = time.perf_counter()
        start, end = date_bounds_or_default(start, end, days=30)
        df = self._readings.get_readings(plant_uid, start=start, end=end)
        if df.empty:
            return AnalysisResult(self.analysis_type, plant_uid, start, end, warnings=["No readings available."])

        ts_col = detect_time_column(df)
        power_col = find_numeric_column(df, ["activepower", "power", "pac", "p_grid", "kw"])
        irr_col = find_numeric_column(df, ["poa", "irradiance", "gti", "ghi"])

        if not ts_col or not power_col:
            return AnalysisResult(self.analysis_type, plant_uid, start, end, warnings=["Required columns not found."])

        df = coerce_datetime(df, ts_col)
        power = pd.to_numeric(df[power_col], errors="coerce")
        threshold = float(power.quantile(params.get("plateau_quantile", 0.98)))
        high_irr = pd.Series(True, index=df.index)
        if irr_col:
            irr = pd.to_numeric(df[irr_col], errors="coerce")
            high_irr = irr >= params.get("min_irradiance", 600)

        clipped = (power >= threshold) & high_irr
        clipped_share = float(clipped.mean()) if len(df) else 0.0
        energy_kwh = estimate_energy_kwh(df, power_col, ts_col)
        clipping_loss_pct = min(clipped_share * 5.0, 100.0)

        out = df[[ts_col, power_col]].copy()
        out["is_clipped"] = clipped.astype(bool)

        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid,
            start=start,
            end=end,
            summary={
                "records": int(len(df)),
                "clipped_records": int(clipped.sum()),
                "clipping_rate_pct": round(clipped_share * 100.0, 2),
                "estimated_clipping_loss_pct": round(clipping_loss_pct, 2),
                "energy_kwh": round(energy_kwh, 2),
            },
            timeseries=out,
            losses={"clipping": round(clipping_loss_pct, 2)},
            calculation_seconds=round(time.perf_counter() - t0, 3),
        )
