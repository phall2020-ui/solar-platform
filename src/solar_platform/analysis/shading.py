"""Shading analysis engine.

Detects shading by comparing hourly normalised performance profiles.

Two modes:
1. **Seasonal baseline** (preferred) – compare winter/shoulder months against
   a summer baseline.  Summer months (Jun-Aug in NH) are assumed unshaded and
   form the reference profile.  Shoulder-to-midday ratio *within* each season
   is then compared.
2. **Single-period fallback** – when data spans < 4 months, a single-period
   shoulder vs midday analysis is used (original simplified method).

Per-device profiles are computed when multiple inverter IDs are present so
that individual shading can be identified.
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
    find_numeric_column,
    merge_power_and_irradiance,
    normalized_ratio,
)
from solar_platform.db.engine import DatabaseEngine
from solar_platform.db.repository import ReadingsRepository

# Summer / baseline months (Northern Hemisphere)
_SUMMER_MONTHS = {5, 6, 7, 8}
_WINTER_MONTHS = {11, 12, 1, 2}
_SHOULDER_HOURS = [8, 9, 15, 16]
_MIDDAY_HOURS = [11, 12, 13, 14]
_MIN_IRRADIANCE = 50.0  # W/m² – ignore very low light


class ShadingEngine(AnalysisEngine):
    """Estimate shading via hourly normalised performance profiles."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self._readings = ReadingsRepository(engine=engine)

    @property
    def analysis_type(self) -> str:
        return "shading"

    # ------------------------------------------------------------------

    def run(
        self,
        plant_uid: str,
        start: datetime | None,
        end: datetime | None,
        **params: Any,
    ) -> AnalysisResult:
        t0 = time.perf_counter()
        start, end = date_bounds_or_default(start, end, days=60)
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

        # ── Merge weather-station irradiance onto inverter rows ──────
        df = merge_power_and_irradiance(df, ts_col)

        power_col = find_numeric_column(df, POWER_KEYWORDS)
        irr_col = find_numeric_column(df, IRRADIANCE_KEYWORDS)

        if not power_col or not irr_col:
            return AnalysisResult(
                self.analysis_type, plant_uid, start, end,
                warnings=["Need power and irradiance columns for shading analysis."],
            )

        # Coerce to numeric
        df[power_col] = pd.to_numeric(df[power_col], errors="coerce")
        df[irr_col] = pd.to_numeric(df[irr_col], errors="coerce")

        # Filter low-light / zero-power
        df = df[(df[irr_col] >= _MIN_IRRADIANCE) & (df[power_col] > 0)].copy()
        if df.empty:
            return AnalysisResult(
                self.analysis_type, plant_uid, start, end,
                warnings=["Insufficient daylight readings after filtering."],
            )

        df["hour"] = df[ts_col].dt.hour
        df["month"] = df[ts_col].dt.month
        df["norm_ratio"] = normalized_ratio(df[power_col], df[irr_col])

        # ── Decide: seasonal baseline or single-period ───────────────
        months_present = set(df["month"].unique())
        has_summer = bool(months_present & _SUMMER_MONTHS)
        has_winter = bool(months_present & _WINTER_MONTHS)
        use_seasonal = has_summer and has_winter

        if use_seasonal:
            result = self._seasonal_analysis(df, plant_uid, start, end, t0)
        else:
            result = self._single_period_analysis(df, plant_uid, start, end, t0)

        # ── Per-device breakdown ─────────────────────────────────────
        device_col = None
        for cand in ("emig_id", "emigId", "device_id"):
            if cand in df.columns:
                device_col = cand
                break

        if device_col:
            inv_df = df[~df[device_col].astype(str).str.startswith("WETH")]
            devices = inv_df[device_col].unique()
            if len(devices) > 1:
                per_device = self._per_device_profile(inv_df, device_col)
                result.summary["per_device"] = per_device
                if any(d.get("shading_loss_pct", 0) > 5 for d in per_device):
                    result.warnings.append(
                        "Individual inverter shading detected – check per-device breakdown."
                    )

        return result

    # ------------------------------------------------------------------
    # Seasonal baseline analysis
    # ------------------------------------------------------------------

    def _seasonal_analysis(
        self, df: pd.DataFrame, plant_uid: str,
        start: datetime, end: datetime, t0: float,
    ) -> AnalysisResult:
        """Compare summer baseline profile against winter profile."""

        summer = df[df["month"].isin(_SUMMER_MONTHS)]
        winter = df[df["month"].isin(_WINTER_MONTHS)]

        baseline_profile = (
            summer.groupby("hour", as_index=False)["norm_ratio"].median()
            .rename(columns={"norm_ratio": "baseline_ratio"})
        )
        compare_profile = (
            winter.groupby("hour", as_index=False)["norm_ratio"].median()
            .rename(columns={"norm_ratio": "compare_ratio"})
        )

        hourly = baseline_profile.merge(compare_profile, on="hour", how="outer").sort_values("hour")
        hourly["shading_delta"] = hourly["baseline_ratio"] - hourly["compare_ratio"]
        hourly["ratio"] = hourly["compare_ratio"] / hourly["baseline_ratio"].replace(0, np.nan)

        # Core-hours shading ratio (9–15)
        core = hourly[hourly["hour"].between(9, 15)]
        shading_ratio = float(core["ratio"].median()) if not core.empty else 1.0
        shading_ratio = max(0.0, min(shading_ratio, 1.5))
        shading_loss_pct = max(0.0, (1.0 - shading_ratio) * 100.0)

        # Shoulder analysis for additional context
        midday_base = baseline_profile[baseline_profile["hour"].between(11, 14)]["baseline_ratio"].median()
        shoulder_compare = compare_profile[compare_profile["hour"].isin(_SHOULDER_HOURS)]["compare_ratio"].median()
        shoulder_ratio = float((shoulder_compare / midday_base) if pd.notna(midday_base) and midday_base else 1.0)

        # Normalise profiles to 0-1 so chart thresholds are meaningful
        peak = hourly["baseline_ratio"].max()
        if pd.notna(peak) and peak > 0:
            hourly["baseline_ratio"] = hourly["baseline_ratio"] / peak
            hourly["compare_ratio"] = hourly["compare_ratio"] / peak
            hourly["shading_delta"] = hourly["baseline_ratio"] - hourly["compare_ratio"]
            # ratio (compare/baseline) is scale-invariant, no need to redo

        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid,
            start=start,
            end=end,
            summary={
                "mode": "seasonal_baseline",
                "summer_hours": int(len(summer)),
                "winter_hours": int(len(winter)),
                "hourly_points": int(len(hourly)),
                "shading_ratio": round(shading_ratio, 3),
                "shoulder_ratio": round(shoulder_ratio, 3),
                "estimated_shading_loss_pct": round(shading_loss_pct, 2),
            },
            table=hourly,
            losses={"shading": round(shading_loss_pct, 2)},
            calculation_seconds=round(time.perf_counter() - t0, 3),
        )

    # ------------------------------------------------------------------
    # Single-period fallback
    # ------------------------------------------------------------------

    def _single_period_analysis(
        self, df: pd.DataFrame, plant_uid: str,
        start: datetime, end: datetime, t0: float,
    ) -> AnalysisResult:
        """Shoulder vs midday ratio for a single contiguous period."""

        hourly = df.groupby("hour", as_index=False)["norm_ratio"].median()
        midday = hourly[hourly["hour"].between(11, 14)]["norm_ratio"].median()
        shoulder = hourly[hourly["hour"].isin(_SHOULDER_HOURS)]["norm_ratio"].median()

        shading_ratio = float((shoulder / midday) if pd.notna(midday) and midday else 1.0)
        shading_loss_pct = max(0.0, min((1.0 - shading_ratio) * 100.0, 100.0))

        # Normalise hourly profile to 0-1 so chart thresholds are meaningful
        peak = hourly["norm_ratio"].max()
        if pd.notna(peak) and peak > 0:
            hourly["norm_ratio"] = hourly["norm_ratio"] / peak

        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid,
            start=start,
            end=end,
            summary={
                "mode": "single_period",
                "hourly_points": int(len(hourly)),
                "shading_ratio": round(shading_ratio, 3),
                "estimated_shading_loss_pct": round(shading_loss_pct, 2),
            },
            table=hourly,
            losses={"shading": round(shading_loss_pct, 2)},
            calculation_seconds=round(time.perf_counter() - t0, 3),
        )

    # ------------------------------------------------------------------
    # Per-device breakdown
    # ------------------------------------------------------------------

    @staticmethod
    def _per_device_profile(df: pd.DataFrame, device_col: str) -> list[dict]:
        """Compute shading metrics per inverter device."""
        results = []
        for device_id, grp in df.groupby(device_col):
            hourly = grp.groupby("hour")["norm_ratio"].median()
            midday = hourly.loc[hourly.index.isin(range(11, 15))].median()
            shoulder = hourly.loc[hourly.index.isin(_SHOULDER_HOURS)].median()
            ratio = float((shoulder / midday) if pd.notna(midday) and midday else 1.0)
            loss = max(0.0, (1.0 - ratio) * 100.0)
            classification = (
                "No Shading" if ratio >= 0.95
                else "Mild" if ratio >= 0.85
                else "Moderate" if ratio >= 0.70
                else "Severe"
            )
            results.append({
                "device_id": str(device_id),
                "shading_ratio": round(ratio, 3),
                "shading_loss_pct": round(loss, 2),
                "classification": classification,
                "records": int(len(grp)),
            })
        return sorted(results, key=lambda d: d["shading_loss_pct"], reverse=True)
