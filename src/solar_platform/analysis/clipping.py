"""Clipping analysis engine.

Detects inverter clipping (power-capping) when output plateaus near the
inverter AC rating under high irradiance.

Improvements over the original stub:
- Uses plant DC capacity to derive expected un-clipped power.
- Estimates *actual* lost energy by fitting a linear irradiance→power model
  to un-clipped points and comparing with clipped points.
- ``estimated_clipping_loss_pct`` is the ratio of clipped energy to total
  expected energy (not an arbitrary multiplier).
- Merges weather-station irradiance onto inverter rows automatically.
"""

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
    estimate_interval_hours,
    find_numeric_column,
    load_plant_capacity_kw,
    merge_power_and_irradiance,
)
from solar_platform.db.engine import DatabaseEngine
from solar_platform.db.repository import ReadingsRepository


class ClippingEngine(AnalysisEngine):
    """Detect inverter clipping from power plateaus under high irradiance."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self._readings = ReadingsRepository(engine=engine)

    @property
    def analysis_type(self) -> str:
        return "clipping"

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

        # ── Merge weather irradiance onto inverter rows ──────────────
        df = merge_power_and_irradiance(df, ts_col)

        power_col = find_numeric_column(df, POWER_KEYWORDS)
        irr_col = find_numeric_column(df, IRRADIANCE_KEYWORDS)

        if not power_col:
            return AnalysisResult(
                self.analysis_type, plant_uid, start, end,
                warnings=["Power column not found."],
            )

        df[power_col] = pd.to_numeric(df[power_col], errors="coerce")
        if irr_col:
            df[irr_col] = pd.to_numeric(df[irr_col], errors="coerce")

        # Drop NaN power
        df = df[df[power_col].notna() & (df[power_col] > 0)].copy()
        if df.empty:
            return AnalysisResult(
                self.analysis_type, plant_uid, start, end,
                warnings=["No valid power readings."],
            )

        # ── Detect plateau ───────────────────────────────────────────
        plateau_quantile = params.get("plateau_quantile", 0.98)
        min_irradiance = params.get("min_irradiance", 600)
        power = df[power_col]
        threshold = float(power.quantile(plateau_quantile))

        high_irr = pd.Series(True, index=df.index)
        if irr_col and irr_col in df.columns:
            high_irr = df[irr_col].notna() & (df[irr_col] >= min_irradiance)

        clipped = (power >= threshold) & high_irr
        clipped_share = float(clipped.mean()) if len(df) else 0.0

        # ── Auto-detect W vs kW ─────────────────────────────────────
        unit_col = power_col.replace("_value", "_unit")
        power_factor = 1.0  # assume kW by default
        if unit_col in df.columns and df[unit_col].notna().any():
            unit_sample = str(df[unit_col].dropna().iloc[0]).strip().lower()
            if unit_sample in ("w", "watt", "watts"):
                power_factor = 1000.0  # W → kW divisor

        # ── Estimate actual energy loss from clipping ────────────────
        interval_h = estimate_interval_hours(df, ts_col)
        power_kw = power / power_factor

        clipping_loss_pct = 0.0
        clipped_energy_kwh = 0.0
        expected_energy_kwh = 0.0
        actual_energy_kwh = float((power_kw * interval_h).sum())

        if irr_col and irr_col in df.columns and df[irr_col].notna().any():
            # Fit a simple linear model on un-clipped high-irradiance points
            unclipped_mask = ~clipped & high_irr & df[irr_col].notna()
            unclipped = df[unclipped_mask]

            if len(unclipped) >= 10:
                # polyfit: power_kw = slope * irradiance + intercept
                x = unclipped[irr_col].values.astype(float)
                y = (unclipped[power_col] / power_factor).values.astype(float)
                try:
                    slope, intercept = np.polyfit(x, y, 1)
                except Exception:
                    slope, intercept = 0.0, 0.0

                if slope > 0:
                    # For clipped intervals, estimate what power *should* have been
                    clipped_df = df[clipped].copy()
                    if not clipped_df.empty and irr_col in clipped_df.columns:
                        expected_kw = slope * clipped_df[irr_col].values + intercept
                        actual_kw = (clipped_df[power_col] / power_factor).values
                        loss_kw = np.clip(expected_kw - actual_kw, 0, None)
                        clipped_energy_kwh = float((loss_kw * interval_h).sum())

                    # Total expected energy (actual + clipped loss)
                    expected_energy_kwh = actual_energy_kwh + clipped_energy_kwh
                    if expected_energy_kwh > 0:
                        clipping_loss_pct = (clipped_energy_kwh / expected_energy_kwh) * 100.0
        else:
            # No irradiance — fallback to simpler estimate
            # Assume clipped power is capped at threshold; excess is unknown
            # Use a conservative estimate: median excess above threshold × count
            dc_kw = load_plant_capacity_kw(plant_uid)
            if dc_kw and dc_kw > 0:
                expected_headroom = (dc_kw - threshold / power_factor)
                if expected_headroom > 0:
                    clipped_energy_kwh = float(clipped.sum() * expected_headroom * 0.5 * interval_h)
                    expected_energy_kwh = actual_energy_kwh + clipped_energy_kwh
                    if expected_energy_kwh > 0:
                        clipping_loss_pct = (clipped_energy_kwh / expected_energy_kwh) * 100.0

        clipping_loss_pct = min(clipping_loss_pct, 100.0)

        # ── Output timeseries ────────────────────────────────────────
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
                "clipped_energy_kwh": round(clipped_energy_kwh, 2),
                "energy_kwh": round(actual_energy_kwh, 2),
            },
            timeseries=out,
            losses={"clipping": round(clipping_loss_pct, 2)},
            calculation_seconds=round(time.perf_counter() - t0, 3),
        )
