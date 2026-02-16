"""Curtailment analysis engine.

Detects export-limitation curtailment by:

1. **Primary method** – look for an ``exportLimit_value`` (or similar) column.
   When the export limit is below a threshold (default 99 %), the interval is
   considered curtailed.
2. **Power-plateau fallback** – if no export-limit telemetry is available,
   detect curtailment as a sustained power plateau (flat-top) with high
   irradiance.  This avoids the previous broken logic that arbitrarily flagged
   the bottom 20 % of power readings.
3. **Energy loss** – estimate lost energy from the difference between expected
   un-curtailed power (from the irradiance→power relationship) and actual
   output during curtailed intervals.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from solar_platform.analysis.base import AnalysisEngine, AnalysisResult
from solar_platform.analysis.helpers import (
    EXPORT_LIMIT_KEYWORDS,
    IRRADIANCE_KEYWORDS,
    POWER_KEYWORDS,
    coerce_datetime,
    date_bounds_or_default,
    detect_time_column,
    estimate_interval_hours,
    find_numeric_column,
    merge_power_and_irradiance,
)
from solar_platform.db.engine import DatabaseEngine
from solar_platform.db.repository import ReadingsRepository

_MIN_IRRADIANCE = 200  # W/m²


class CurtailmentEngine(AnalysisEngine):
    """Estimate curtailment from export-limit telemetry or power plateaus."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self._readings = ReadingsRepository(engine=engine)

    @property
    def analysis_type(self) -> str:
        return "curtailment"

    def run(
        self,
        plant_uid: str,
        start: datetime | None,
        end: datetime | None,
        **params: Any,
    ) -> AnalysisResult:
        t0 = time.perf_counter()
        start, end = date_bounds_or_default(start, end, days=30)
        df = self._readings.get_readings(plant_uid, start=start, end=end)
        if df.empty:
            return AnalysisResult(
                self.analysis_type, plant_uid, start, end,
                warnings=["No readings available."],
            )

        ts_col = detect_time_column(df)
        if not ts_col:
            return AnalysisResult(
                self.analysis_type, plant_uid, start, end,
                warnings=["Timestamp column missing."],
            )
        df = coerce_datetime(df, ts_col)

        # ── Merge weather irradiance ─────────────────────────────────
        df = merge_power_and_irradiance(df, ts_col)

        power_col = find_numeric_column(df, POWER_KEYWORDS)
        limit_col = find_numeric_column(df, EXPORT_LIMIT_KEYWORDS)
        irr_col = find_numeric_column(df, IRRADIANCE_KEYWORDS)

        if not power_col and not limit_col:
            return AnalysisResult(
                self.analysis_type, plant_uid, start, end,
                warnings=["No power or export-limit columns found."],
            )

        if power_col:
            df[power_col] = pd.to_numeric(df[power_col], errors="coerce")
        if limit_col:
            df[limit_col] = pd.to_numeric(df[limit_col], errors="coerce")
        if irr_col:
            df[irr_col] = pd.to_numeric(df[irr_col], errors="coerce")

        # Only keep rows with some data
        if power_col:
            df = df[df[power_col].notna()].copy()
        if df.empty:
            return AnalysisResult(
                self.analysis_type, plant_uid, start, end,
                warnings=["No valid readings after filtering."],
            )

        # ── Method 1: Export limit telemetry ─────────────────────────
        method = "none"
        if limit_col and df[limit_col].notna().any():
            limit_threshold = params.get("limit_threshold_pct", 99)
            limit_pct = df[limit_col]
            curtailed = limit_pct < limit_threshold
            method = "export_limit"
        # ── Method 2: Power-plateau detection ────────────────────────
        elif power_col:
            curtailed = self._detect_power_plateau(df, power_col, irr_col)
            method = "power_plateau"
        else:
            curtailed = pd.Series(False, index=df.index)

        # ── Estimate curtailed energy ────────────────────────────────
        curtailed_energy_kwh = 0.0
        interval_h = estimate_interval_hours(df, ts_col)

        # Power unit detection
        power_factor = 1.0
        if power_col:
            unit_col = power_col.replace("_value", "_unit")
            if unit_col in df.columns and df[unit_col].notna().any():
                unit_sample = str(df[unit_col].dropna().iloc[0]).strip().lower()
                if unit_sample in ("w", "watt", "watts"):
                    power_factor = 1000.0

        if (
            power_col
            and irr_col
            and irr_col in df.columns
            and curtailed.any()
            and df[irr_col].notna().any()
        ):
            # Fit linear model on un-curtailed, daylight points
            daylight = df[irr_col].notna() & (df[irr_col] >= _MIN_IRRADIANCE) & (df[power_col] > 0)
            uncurtailed_fit = df[daylight & ~curtailed]
            if len(uncurtailed_fit) >= 10:
                try:
                    slope, intercept = np.polyfit(
                        uncurtailed_fit[irr_col].values.astype(float),
                        (uncurtailed_fit[power_col] / power_factor).values.astype(float),
                        1,
                    )
                except Exception:
                    slope, intercept = 0.0, 0.0

                if slope > 0:
                    curt_df = df[curtailed & daylight]
                    if not curt_df.empty:
                        expected_kw = slope * curt_df[irr_col].values + intercept
                        actual_kw = (curt_df[power_col] / power_factor).values
                        loss_kw = np.clip(expected_kw - actual_kw, 0, None)
                        curtailed_energy_kwh = float((loss_kw * interval_h).sum())

        curtailment_rate = float(curtailed.mean() * 100.0) if len(df) else 0.0

        # ── Output ───────────────────────────────────────────────────
        out_cols = [ts_col]
        if power_col:
            out_cols.append(power_col)
        if limit_col:
            out_cols.append(limit_col)
        out = df[[c for c in out_cols if c in df.columns]].copy()
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
                "detection_method": method,
                "curtailed_energy_kwh": round(curtailed_energy_kwh, 2),
            },
            timeseries=out,
            losses={"curtailment": round(curtailment_rate, 2)},
            calculation_seconds=round(time.perf_counter() - t0, 3),
        )

    # ------------------------------------------------------------------
    # Power-plateau curtailment detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_power_plateau(
        df: pd.DataFrame, power_col: str, irr_col: str | None,
    ) -> pd.Series:
        """Detect curtailment as sustained power plateau under high irradiance.

        Unlike the old logic that flagged power ≤ 20th percentile (which always
        marks ~20 % of data as curtailed), this method looks for intervals where:
        - Power is near a plateau (within 2 % of a repeated cap value)
        - Irradiance is high (suggesting the plant *should* produce more)
        - At least ``min_consecutive`` consecutive readings are at the plateau

        This pattern is characteristic of export-limit curtailment.
        """
        power = df[power_col]
        if power.empty:
            return pd.Series(False, index=df.index)

        # Find the most common "plateau" value using histogram binning
        # Curtailment creates a spike at the export-limit power level
        valid = power.dropna()
        if valid.empty:
            return pd.Series(False, index=df.index)

        # Use the 95th percentile region for plateau detection
        p95 = float(valid.quantile(0.95))
        p99 = float(valid.quantile(0.99))

        if p95 <= 0:
            return pd.Series(False, index=df.index)

        # Plateau tolerance: readings within 2% of each other
        tolerance = p95 * 0.02

        # A reading is "at plateau" if near the 95–99th percentile band
        at_plateau = (power >= p95 - tolerance) & (power <= p99 + tolerance)

        # Require high irradiance when available
        if irr_col and irr_col in df.columns:
            irr = pd.to_numeric(df[irr_col], errors="coerce")
            high_irr = irr.notna() & (irr >= _MIN_IRRADIANCE)
            at_plateau = at_plateau & high_irr

        # Require at least 3 consecutive plateau readings to count
        # (avoids false positives from occasional peaks)
        groups = at_plateau.ne(at_plateau.shift()).cumsum()
        plateau_runs = at_plateau.groupby(groups).transform("sum")
        curtailed = at_plateau & (plateau_runs >= 3)

        return curtailed
