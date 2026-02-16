"""Fouling/soiling analysis engine.

Implements a POA-matched clean-baseline approach inspired by the legacy
``Fouling_analysis.py`` toolkit:

1. Auto-select a clean reference period (best N days by daily median PR).
2. Build a POA-binned expected-clean-power lookup from that period.
3. Compute a fouling index = 1 − median(actual / expected) over a recent
   trailing window.
4. Classify severity and estimate energy loss.
5. Detect cleaning events (PR jumps).
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
    normalized_ratio,
)
from solar_platform.db.engine import DatabaseEngine
from solar_platform.db.repository import ReadingsRepository

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_POA_MIN = 200          # W/m² – ignore below
_POA_BIN_WIDTH = 100    # W/m² per bin
_CLEAN_DAYS = 3         # How many top-PR days form the "clean window"
_FOULING_CLEAN = 0.05
_FOULING_LIGHT = 0.10
_FOULING_MODERATE = 0.20


def _classify(idx: float) -> str:
    if np.isnan(idx):
        return "Insufficient Data"
    if idx <= _FOULING_CLEAN:
        return "Clean"
    if idx <= _FOULING_LIGHT:
        return "Light Soiling"
    if idx <= _FOULING_MODERATE:
        return "Moderate Soiling"
    return "Severe Soiling"


class FoulingEngine(AnalysisEngine):
    """Estimate fouling using POA-matched clean-baseline comparison."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self._readings = ReadingsRepository(engine=engine)

    @property
    def analysis_type(self) -> str:
        return "fouling"

    # ------------------------------------------------------------------

    def run(
        self,
        plant_uid: str,
        start: datetime | None,
        end: datetime | None,
        **params: Any,
    ) -> AnalysisResult:
        t0 = time.perf_counter()
        start, end = date_bounds_or_default(start, end, days=90)
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

        # ── Merge irradiance onto inverter rows ─────────────────────
        df = merge_power_and_irradiance(df, ts_col)

        power_col = find_numeric_column(df, POWER_KEYWORDS)
        irr_col = find_numeric_column(df, IRRADIANCE_KEYWORDS)

        if not power_col or not irr_col:
            return AnalysisResult(
                self.analysis_type, plant_uid, start, end,
                warnings=["Need power and irradiance columns for fouling analysis."],
            )

        # Coerce numeric & basic filter
        df[power_col] = pd.to_numeric(df[power_col], errors="coerce")
        df[irr_col] = pd.to_numeric(df[irr_col], errors="coerce")
        df = df[(df[irr_col] >= _POA_MIN) & (df[power_col] > 0)].copy()
        if df.empty:
            return AnalysisResult(
                self.analysis_type, plant_uid, start, end,
                warnings=["Insufficient daylight readings after filtering."],
            )

        # ── Performance Ratio ────────────────────────────────────────
        dc_kw = params.get("dc_size_kw") or load_plant_capacity_kw(plant_uid)

        # Auto-detect W vs kW for power
        unit_col = power_col.replace("_value", "_unit")
        power_in_kw = df[power_col].copy()
        if unit_col in df.columns and df[unit_col].notna().any():
            unit_sample = str(df[unit_col].dropna().iloc[0]).strip().lower()
            if unit_sample in ("w", "watt", "watts"):
                power_in_kw = power_in_kw / 1000.0

        # If no dc_size_kw is known, estimate from data
        if not dc_kw or dc_kw <= 0:
            dc_kw = float(power_in_kw.quantile(0.99)) or 1.0
            if dc_kw <= 0:
                dc_kw = 1.0

        irr_factor = df[irr_col] / 1000.0  # W/m² → kW/m²
        with np.errstate(divide="ignore", invalid="ignore"):
            df["pr"] = power_in_kw / (irr_factor * dc_kw)
        df.loc[df["pr"] > 2.0, "pr"] = np.nan  # sanity cap
        df.loc[df["pr"] < 0, "pr"] = np.nan

        df["date"] = df[ts_col].dt.date

        # ── POA-matched baseline from auto-selected clean days ───────
        clean_days = params.get("clean_days", _CLEAN_DAYS)
        daily_pr = df.groupby("date")["pr"].agg(["median", "count"]).reset_index()
        daily_pr = daily_pr[daily_pr["count"] >= 4]  # need enough readings
        if daily_pr.empty:
            return AnalysisResult(
                self.analysis_type, plant_uid, start, end,
                warnings=["Not enough daily data to compute fouling."],
            )

        top_days = daily_pr.sort_values("median", ascending=False).head(clean_days)
        clean_dates = set(top_days["date"])
        clean_df = df[df["date"].isin(clean_dates)].copy()

        # POA-binned expected clean power
        df["poa_bin"] = (df[irr_col] // _POA_BIN_WIDTH) * _POA_BIN_WIDTH
        clean_df["poa_bin"] = (clean_df[irr_col] // _POA_BIN_WIDTH) * _POA_BIN_WIDTH

        expected_by_bin = (
            clean_df.groupby("poa_bin")[power_col]
            .median()
            .rename("expected_clean_power")
        )
        df = df.merge(expected_by_bin, how="left", left_on="poa_bin", right_index=True)

        # ── Fouling index ────────────────────────────────────────────
        valid = df[(df["expected_clean_power"] > 0) & df[power_col].notna()].copy()
        if valid.empty:
            return AnalysisResult(
                self.analysis_type, plant_uid, start, end,
                warnings=["Could not compute fouling index (no matched POA bins)."],
            )

        valid["actual_ratio"] = valid[power_col] / valid["expected_clean_power"]

        # Daily fouling series
        daily = valid.groupby("date", as_index=False).agg(
            norm_ratio=("actual_ratio", "median"),
            pr_median=("pr", "median"),
            records=("actual_ratio", "count"),
        )
        daily = daily.sort_values("date")

        # Baseline / current
        baseline_ratio = float(daily["norm_ratio"].quantile(0.95))
        trailing_window = params.get("trailing_window_days", 7)
        recent = daily.tail(trailing_window)
        current_ratio = float(recent["norm_ratio"].median())

        fouling_index = max(0.0, min(1.0 - (current_ratio / baseline_ratio if baseline_ratio else 1.0), 1.0))
        fouling_loss_pct = fouling_index * 100.0
        classification = _classify(fouling_index)

        # ── Energy loss estimate ─────────────────────────────────────
        interval_h = estimate_interval_hours(df, ts_col)
        recent_rows = valid[valid["date"].isin(set(recent["date"]))]
        energy_loss_kwh = 0.0
        if not recent_rows.empty:
            loss_per_row = (recent_rows["expected_clean_power"] - recent_rows[power_col]).clip(lower=0)
            if unit_col in recent_rows.columns and recent_rows[unit_col].notna().any():
                unit_sample = str(recent_rows[unit_col].dropna().iloc[0]).strip().lower()
                if unit_sample in ("w", "watt", "watts"):
                    loss_per_row = loss_per_row / 1000.0
            energy_loss_kwh = float((loss_per_row * interval_h).sum())

        # ── Cleaning events ──────────────────────────────────────────
        daily["pr_roll"] = daily["norm_ratio"].rolling(3, min_periods=1).median()
        daily["pr_change"] = daily["pr_roll"].diff()
        pr_med = daily["pr_roll"].median()
        daily["cleaning_event"] = daily["pr_change"] > 0.10 * pr_med
        cleaning_events = int(daily["cleaning_event"].sum())

        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid,
            start=start,
            end=end,
            summary={
                "days_analyzed": int(len(daily)),
                "clean_reference_days": clean_days,
                "baseline_ratio": round(baseline_ratio, 4),
                "current_ratio": round(current_ratio, 4),
                "fouling_index": round(fouling_index, 4),
                "classification": classification,
                "estimated_fouling_loss_pct": round(fouling_loss_pct, 2),
                "energy_loss_kwh": round(energy_loss_kwh, 1),
                "cleaning_events_detected": cleaning_events,
            },
            timeseries=daily,
            losses={"fouling": round(fouling_loss_pct, 2)},
            calculation_seconds=round(time.perf_counter() - t0, 3),
        )
